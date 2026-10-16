"""Read and validate a CAD_READ file (D1). Input files are opened only with mode "rb".

Order: bytes -> JSON -> read_mode guard -> schema -> handle uniqueness -> coverage invariants -> references.
Any failure raises CadAuditError and the run stops before anything is written.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field

from . import _schema
from .errors import CadAuditError
from .model import COMPLETE, GROUPS, INCOMPLETE, MAX_INPUT_BYTES, NOT_EXTRACTED


def read_file_bytes(path: str, max_bytes: int, kind: str) -> bytes:
    """Read a whole input file in binary mode. kind is INPUT or RULES (used in the error code)."""
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes + 1)
    except OSError as e:
        raise CadAuditError(f"{kind}_UNREADABLE", f"cannot read {kind.lower()} file: {type(e).__name__}") from None
    if len(data) > max_bytes:
        raise CadAuditError(f"{kind}_TOO_LARGE", f"{kind.lower()} file is larger than {max_bytes} bytes")
    return data


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r}")
        out[k] = v
    return out


def _reject_constant(name):
    raise ValueError(f"non-finite number {name} is not allowed")


def _parse_float(text):
    """1e400 parses to inf without any error: refuse it, like NaN and Infinity, so every number is finite."""
    value = float(text)
    if value != value or abs(value) == float("inf"):
        raise ValueError(f"non-finite number {text[:20]} is not allowed")
    return value


def _parse_int(text):
    """An integer too large for a float would raise OverflowError later in a comparison: refuse it here."""
    value = int(text)
    float(value)     # OverflowError when the value is outside the float range
    return value


def parse_json(data: bytes, kind: str = "INPUT"):
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
                          parse_float=_parse_float, parse_int=_parse_int)
    except (UnicodeDecodeError, ValueError, OverflowError, RecursionError) as e:
        raise CadAuditError(f"{kind}_NOT_JSON", f"not valid JSON: {type(e).__name__}: {e}") from None


@dataclass
class Drawing:
    file_id: str
    dwg_sha256: str
    input_sha256: str
    groups: dict
    coverage: dict
    block_refs_by_handle: dict = field(default_factory=dict)
    attributes_by_parent: dict = field(default_factory=dict)


def check_coverage(group: str, cov: dict, items: list) -> None:
    """D1 invariant table. Raises COVERAGE_INCONSISTENT on any violation."""
    status, expected, enumerated, reason = cov["status"], cov["expected"], cov["enumerated"], cov["reason"]
    n = len(items)

    def bad(why: str):
        raise CadAuditError("COVERAGE_INCONSISTENT", f"group {group}: {why}")

    if status == COMPLETE:
        if expected is None:
            bad("COMPLETE needs an integer expected")
        if enumerated != expected:
            bad(f"COMPLETE but enumerated {enumerated} != expected {expected}")
        if reason is not None:
            bad("COMPLETE must have reason null")
    elif status == INCOMPLETE:
        if expected is not None and not enumerated < expected:
            bad(f"INCOMPLETE needs enumerated < expected (got {enumerated} >= {expected})")
        if reason is None:
            bad("INCOMPLETE needs a reason")
    elif status == NOT_EXTRACTED:
        if expected is not None:
            bad("NOT_EXTRACTED needs expected null")
        if enumerated != 0:
            bad("NOT_EXTRACTED needs enumerated 0")
        if reason is None:
            bad("NOT_EXTRACTED needs a reason")
    else:  # unreachable after the schema check, kept fail-closed
        bad(f"unknown status {status!r}")
    if n != enumerated:
        bad(f"array has {n} elements but enumerated is {enumerated}")


def load_cad_read(data: bytes) -> Drawing:
    doc = parse_json(data, "INPUT")
    drawing_part = doc.get("drawing") if isinstance(doc, dict) else None
    if isinstance(drawing_part, dict) and "read_mode" in drawing_part and drawing_part["read_mode"] != "READ_ONLY":
        raise CadAuditError("READ_MODE_NOT_READ_ONLY",
                            f"drawing.read_mode must be 'READ_ONLY', got {drawing_part['read_mode']!r}")
    errs = _schema.check(doc, "cad_read.v1.json")
    if errs:
        raise CadAuditError("INPUT_SCHEMA_INVALID", f"{len(errs)} problem(s), first: {errs[0]}")
    file_id = doc["drawing"]["file_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", file_id):  # '$' in the schema pattern also matches before a trailing newline
        raise CadAuditError("INPUT_SCHEMA_INVALID", "drawing.file_id has characters outside [A-Za-z0-9_-]")

    if not re.fullmatch(r"[0-9a-f]{64}", doc["drawing"]["sha256"]):  # same trailing-newline gap as above
        raise CadAuditError("INPUT_SCHEMA_INVALID", "drawing.sha256 is not 64 lower-case hex characters")

    groups = {g: doc.get(g, []) for g in GROUPS}
    seen = {}
    for g in GROUPS:
        if g == "units":
            continue
        for obj in groups[g]:
            h = obj["handle"]
            if not re.fullmatch(r"[0-9A-F]{1,16}", h):
                raise CadAuditError("INPUT_SCHEMA_INVALID", f"{g}: handle {h!r} is not upper-case hex")
            if h in seen:
                raise CadAuditError("DUPLICATE_HANDLE", f"handle {h} appears in {seen[h]} and {g}")
            seen[h] = g

    coverage = doc["coverage"]
    for g in GROUPS:
        if g not in coverage:
            raise CadAuditError("COVERAGE_INCONSISTENT", f"group {g}: no coverage entry")
        check_coverage(g, coverage[g], groups[g])

    block_refs = {o["handle"]: o for o in groups["block_refs"]}
    block_refs_complete = coverage["block_refs"]["status"] == COMPLETE
    attributes_by_parent: dict = {}
    for a in groups["attributes"]:
        if a["parent_handle"] not in block_refs and block_refs_complete:
            raise CadAuditError("DANGLING_REFERENCE",
                                f"attribute {a['handle']}: parent {a['parent_handle']} is not in block_refs "
                                "and block_refs is COMPLETE")
        attributes_by_parent.setdefault(a["parent_handle"], []).append(a)
    for parent, attrs in attributes_by_parent.items():
        tags = [a["tag"] for a in attrs]
        if len(tags) != len(set(tags)):
            raise CadAuditError("DUPLICATE_ATTRIBUTE_TAG", f"block_ref {parent} has the same attribute tag twice")

    return Drawing(file_id=file_id, dwg_sha256=doc["drawing"]["sha256"],
                   input_sha256=hashlib.sha256(data).hexdigest(), groups=groups, coverage=coverage,
                   block_refs_by_handle=block_refs, attributes_by_parent=attributes_by_parent)
