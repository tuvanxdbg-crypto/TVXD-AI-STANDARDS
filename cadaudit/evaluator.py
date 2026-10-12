"""Apply rules to a loaded drawing (D4, D5). Pure computation: no file access, no network, no randomness.

Per object, first match wins:   1. STANDARD_REQUIRED -> UNKNOWN(STANDARD_LOOKUP_NOT_ENABLED)
                                2. field null / referenced object missing because its group is not COMPLETE
                                   -> UNKNOWN(FIELD_MISSING | COVERAGE_INCOMPLETE)
                                3. check -> FAIL if violated, else PASS
Per rule, first match wins:     1. STANDARD_REQUIRED -> UNKNOWN(STANDARD_LOOKUP_NOT_ENABLED)
                                2. any object FAIL -> FAIL (kept even when coverage is incomplete)
                                3. a group in reads_groups is not COMPLETE -> UNKNOWN(COVERAGE_INCOMPLETE)
                                4. no object in scope -> UNKNOWN(NO_OBJECTS_IN_SCOPE)
                                5. any object UNKNOWN -> UNKNOWN (all object reasons)
                                6. otherwise PASS
There is no inferred FAIL: a missing object never becomes a FAIL unless its group is COMPLETE.
"""
import json
from dataclasses import dataclass, field

from .loader import Drawing
from .model import (COMPLETE, DEFAULT_MAX_LENGTH, NAME_FIELD, PRIMARY_FIELD, UNKNOWN_REASONS, evidence_id,
                    file_evidence_id)
from .rules import STANDARD_REQUIRED, Rule

SLNE = "STANDARD_LOOKUP_NOT_ENABLED"


@dataclass
class Row:
    rule_id: str
    rule_status: str
    classification: str
    handle: str
    verdict: str
    reason: str | None
    evidence_ids: list
    actual: object
    expected: object
    standard_hint: str | None


@dataclass
class RuleResult:
    rule: Rule
    verdict: str
    reasons: list
    coverage_complete: bool
    rows: list
    counts: dict
    evidence_ids: list = field(default_factory=list)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same(a, b) -> bool:
    """Equality that never treats True as 1 or a string as a number."""
    if _is_num(a) and _is_num(b):
        return a == b
    return type(a) is type(b) and a == b


def _dedupe(ids: list) -> list:
    out = []
    for i in ids:
        if i not in out:
            out.append(i)
    return out


def check_fields(rule: Rule) -> list:
    """Fields of the object the check reads (used as evidence, also for STANDARD_REQUIRED rows)."""
    c = rule.check
    t = c["type"]
    if t in ("name_pattern", "allowed_values", "numeric_range"):
        return [c["field"]]
    if t == "required_field":
        return [c["field"]] if "field" in c else [PRIMARY_FIELD[rule.applies_to]]
    if t == "equals_field":
        return [c["field_a"], c["field_b"]]
    return ["path_status"]  # xref_resolved


def describe_expected(rule: Rule) -> str:
    c = rule.check
    t = c["type"]
    if t == "name_pattern":
        return f"fullmatch {c['pattern']}, length <= {c.get('max_length', DEFAULT_MAX_LENGTH)}"
    if t == "allowed_values":
        return "one of " + json.dumps(c["values"], ensure_ascii=False)
    if t == "numeric_range":
        lo, hi = c.get("min"), c.get("max")
        return f"range min={'none' if lo is None else lo} max={'none' if hi is None else hi} tolerance={c.get('tolerance', 0)}"
    if t == "required_field":
        return f"attribute {c['attribute_tag']} present and non-empty" if "attribute_tag" in c else "present and non-empty"
    if t == "equals_field":
        return f"{c['field_a']} equals {c['field_b']}" + (f" (tolerance {c['tolerance']})" if "tolerance" in c else "")
    return "path_status is RESOLVED"


def _select(rule: Rule, obj: dict, drawing: Drawing) -> tuple:
    """Return (in_scope, parent_unknown). parent_unknown: the object is not excluded by what is known, but a
    selector key needs the parent block reference, which is absent because block_refs is not COMPLETE."""
    group = rule.applies_to
    parent_unknown = False
    for key, want in rule.selector.items():
        if key == "space":
            ok = obj["space"] == want
        elif key == "tag":
            ok = obj["tag"] == want
        elif key == "name_pattern":
            ok = rule.name_regex.fullmatch(obj[NAME_FIELD[group]]) is not None
        else:  # layer, block_name
            if group == "attributes":
                parent = drawing.block_refs_by_handle.get(obj["parent_handle"])
                if parent is None:
                    parent_unknown = True
                    continue
                ok = parent["layer" if key == "layer" else "block_name"] == want
            else:
                ok = obj["layer" if key == "layer" else "block_name"] == want
        if not ok:
            return False, False
    return True, parent_unknown


def _eval_object(rule: Rule, drawing: Drawing, obj: dict, parent_unknown: bool) -> Row:
    group, chk = rule.applies_to, rule.check
    ctype = chk["type"]
    fid = drawing.file_id
    handle = obj.get("handle", "FILE")

    def ev(f):
        return evidence_id(fid, group, obj, f)

    def row(verdict, reason, evs, actual, expected):
        return Row(rule.id, rule.status, rule.classification, handle, verdict, reason, _dedupe(evs), actual,
                   expected, rule.standard_hint)

    expected = describe_expected(rule)
    # 1. STANDARD_REQUIRED: never PASS or FAIL in M04-A, whatever the data says.
    if rule.classification == STANDARD_REQUIRED:
        fields = check_fields(rule)
        return row("UNKNOWN", SLNE, [ev(f) for f in fields], obj.get(fields[0]), None)
    # 2. missing reference or null field.
    if parent_unknown:
        return row("UNKNOWN", "COVERAGE_INCOMPLETE",
                   [ev("parent_handle"), file_evidence_id(fid, "coverage.block_refs.status")], None, expected)
    if ctype == "required_field" and "attribute_tag" in chk:
        tag = chk["attribute_tag"]
        found = [a for a in drawing.attributes_by_parent.get(obj["handle"], []) if a["tag"] == tag]
        if not found:
            if drawing.coverage["attributes"]["status"] == COMPLETE:
                return row("FAIL", None, [ev("block_name")], None, expected)  # the block reference lacks the tag
            return row("UNKNOWN", "COVERAGE_INCOMPLETE",
                       [ev("block_name"), file_evidence_id(fid, "coverage.attributes.status")], None, expected)
        attr = found[0]
        aev = evidence_id(fid, "attributes", attr, "value")
        if attr["value"] is None:
            return row("UNKNOWN", "FIELD_MISSING", [aev], None, expected)
        if attr["value"].strip() == "":
            return row("FAIL", None, [aev], attr["value"], expected)
        return row("PASS", None, [aev], attr["value"], expected)

    fields = check_fields(rule)
    nulls = [f for f in fields if obj[f] is None]
    if nulls:
        return row("UNKNOWN", "FIELD_MISSING", [ev(f) for f in fields], None, expected)
    # 3. apply the check.
    evs = [ev(f) for f in fields]
    if ctype == "equals_field":
        a, b = obj[chk["field_a"]], obj[chk["field_b"]]
        ok = abs(a - b) <= chk.get("tolerance", 0) if _is_num(a) else _same(a, b)
        return row("PASS" if ok else "FAIL", None, evs, b, a)
    v = obj[fields[0]]
    if ctype == "name_pattern":
        limit = chk.get("max_length", DEFAULT_MAX_LENGTH)
        ok = len(v) <= limit and rule.check_regex.fullmatch(v) is not None
    elif ctype == "allowed_values":
        ok = any(_same(v, x) for x in chk["values"])
    elif ctype == "numeric_range":
        tol = chk.get("tolerance", 0)
        ok = ("min" not in chk or v >= chk["min"] - tol) and ("max" not in chk or v <= chk["max"] + tol)
    elif ctype == "required_field":
        ok = not (isinstance(v, str) and v.strip() == "")
    else:  # xref_resolved
        ok = v == "RESOLVED"
    return row("PASS" if ok else "FAIL", None, evs, v, expected)


def evaluate_rule(rule: Rule, drawing: Drawing) -> RuleResult:
    group = rule.applies_to
    rows = []
    for obj in drawing.groups[group]:
        in_scope, parent_unknown = _select(rule, obj, drawing)
        if in_scope:
            rows.append(_eval_object(rule, drawing, obj, parent_unknown))
    counts = {v: sum(1 for r in rows if r.verdict == v) for v in ("PASS", "FAIL", "UNKNOWN")}
    incomplete = [g for g in rule.reads_groups if drawing.coverage[g]["status"] != COMPLETE]
    coverage_complete = not incomplete
    fid = drawing.file_id

    def union(sel):
        return _dedupe([i for r in rows if r.verdict == sel for i in r.evidence_ids])

    if rule.classification == STANDARD_REQUIRED:
        verdict, reasons = "UNKNOWN", [SLNE]
        evs = _dedupe([i for r in rows for i in r.evidence_ids]) or [file_evidence_id(fid, f"coverage.{group}.status")]
    elif counts["FAIL"]:
        verdict, reasons, evs = "FAIL", [], union("FAIL")
    elif incomplete:
        verdict, reasons = "UNKNOWN", ["COVERAGE_INCOMPLETE"]
        evs = [file_evidence_id(fid, f"coverage.{g}.status") for g in incomplete]
    elif not rows:
        verdict, reasons = "UNKNOWN", ["NO_OBJECTS_IN_SCOPE"]
        evs = [file_evidence_id(fid, f"coverage.{group}.status")]
    elif counts["UNKNOWN"]:
        found = {r.reason for r in rows if r.verdict == "UNKNOWN"}
        verdict, reasons, evs = "UNKNOWN", [x for x in UNKNOWN_REASONS if x in found], union("UNKNOWN")
    else:
        verdict, reasons, evs = "PASS", [], []
    return RuleResult(rule=rule, verdict=verdict, reasons=reasons, coverage_complete=coverage_complete, rows=rows,
                      counts=counts, evidence_ids=evs)
