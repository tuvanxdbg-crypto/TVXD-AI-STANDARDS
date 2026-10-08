"""INDEX.yaml: load, validate (schema + semantic checks), version selection and applicability.

INDEX is machine metadata only. Applicability comes only from owner-reviewed INDEX entries
plus the request context; the Gateway never infers that a standard applies because it exists.
Since contract v2 (M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE) INDEX also defines the NotebookLM
scope (whitelisted notebook + source per version) that limits every query; local file
path/hash and sync identity are optional provenance and are never checked.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import schema
from .errors import GatewayError
from .paths import relpath_problems
from .textnorm import fold

APPLICABLE, NOT_APPLICABLE, UNKNOWN = "APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"


@dataclass(frozen=True)
class Mapping:
    notebook_id: str
    source_id: str
    sync_sha256: str | None
    synced_at: str | None


@dataclass(frozen=True)
class Version:
    doc_id: str
    version: str
    status: str
    effective_from: dt.date | None
    effective_to: dt.date | None
    path: str | None       # authoritative file metadata; optional and never checked since contract v2
    format: str
    sha256: str | None
    clause_scheme: str
    mapping: Mapping | None  # NotebookLM scope: the only notebook/source queried for this version

    @property
    def source_key(self) -> str:
        return f"{self.doc_id}@{self.version}"

    def in_force(self, day: dt.date) -> bool | None:
        """True/False when dates decide it, None when effective_from is unknown."""
        if self.effective_from is None:
            return None
        return self.effective_from <= day and (self.effective_to is None or day < self.effective_to)


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    doc_type: str
    codes: tuple[str, ...]
    topics: tuple[str, ...]
    reviewed: bool
    reviewed_by: str | None
    work_codes: tuple[str, ...]
    conditions: tuple[tuple[str, str], ...]
    versions: tuple[Version, ...]


@dataclass
class Applicability:
    status: str
    basis: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": self.status, "basis": self.basis, "missing": self.missing}


@dataclass(frozen=True)
class Index:
    index_version: str
    rules_version: str
    fixture: bool
    sha256: str
    work_codes: frozenset[str]
    documents: dict[str, Document]
    whitelist_documents: frozenset[str]
    whitelist_notebooks: frozenset[str]

    def ref(self) -> dict:
        return {"index_version": self.index_version, "rules_version": self.rules_version,
                "index_sha256": self.sha256, "fixture": self.fixture}

    def is_whitelisted(self, doc_id: str) -> bool:
        return doc_id in self.whitelist_documents

    def by_mapping(self, notebook_id: str, source_id: str) -> Version | None:
        for doc in self.documents.values():
            for v in doc.versions:
                if v.mapping and v.mapping.notebook_id == notebook_id and v.mapping.source_id == source_id:
                    return v
        return None

    def resolve_codes(self, query: str) -> list[Document]:
        """Documents whose code/alias appears in the query as a whole phrase (diacritic-insensitive)."""
        q = fold(query)
        hits = []
        for doc in self.documents.values():
            for code in doc.codes:
                if re.search(r"(?<![0-9a-z])" + re.escape(fold(code)) + r"(?![0-9a-z])", q):
                    hits.append(doc)
                    break
        return hits


def _date(value) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def load_index(path: Path) -> Index:
    try:
        raw = Path(path).read_bytes()
    except OSError as e:
        raise GatewayError("INDEX_INVALID", f"INDEX not readable: {type(e).__name__}") from None
    return parse_index(raw)


def parse_index(raw: bytes) -> Index:
    try:
        # YAML 1.1 would turn unquoted dates into date objects; keep everything as text.
        data = yaml.load(raw.decode("utf-8-sig"), Loader=_StringDateLoader)  # noqa: S506 - SafeLoader subclass
    except (UnicodeDecodeError, yaml.YAMLError) as e:
        raise GatewayError("INDEX_INVALID", f"INDEX is not valid UTF-8 YAML: {type(e).__name__}") from None
    problems = schema.check(data, "index.v1.json")
    if problems:
        raise GatewayError("INDEX_INVALID", "INDEX does not match index.v1.json", details={"problems": problems[:50]})
    problems = []
    work_codes = [w["code"] for w in data["work_codes"]]
    if len(set(work_codes)) != len(work_codes):
        problems.append("duplicate work_code")
    docs: dict[str, Document] = {}
    mappings: set[tuple[str, str]] = set()
    for d in data["documents"]:
        if d["id"] in docs:
            problems.append(f"duplicate document id {d['id']}")
        labels = [v["version"] for v in d["versions"]]
        if len(set(labels)) != len(labels):
            problems.append(f"{d['id']}: duplicate version label")
        for wc in d["applicability"]["work_codes"]:
            if wc not in work_codes:
                problems.append(f"{d['id']}: applicability work_code {wc} not defined in work_codes")
        if d["applicability"]["reviewed"] and not d["applicability"]["reviewed_by"]:
            problems.append(f"{d['id']}: reviewed applicability needs reviewed_by")
        versions = []
        for v in d["versions"]:
            where = f"{d['id']}@{v['version']}"
            path = v["source"].get("path")
            for p in relpath_problems(path) if path is not None else []:
                problems.append(f"{where}: source.path {p}")
            ef, et = _date(v["effective_from"]), _date(v["effective_to"])
            if ef and et and et <= ef:
                problems.append(f"{where}: effective_to must be after effective_from")
            m = v.get("notebooklm")
            mapping = None
            if m:
                key = (m["notebook_id"], m["source_id"])
                if key in mappings:
                    problems.append(f"{where}: NotebookLM source mapped twice")
                mappings.add(key)
                sync = m.get("sync")
                mapping = Mapping(m["notebook_id"], m["source_id"], sync["sha256"] if sync else None,
                                  sync["synced_at"] if sync else None)
            versions.append(Version(d["id"], v["version"], v["status"], ef, et, path,
                                    v["source"]["format"], v["source"].get("sha256"), v["source"]["clause_scheme"],
                                    mapping))
        app = d["applicability"]
        docs[d["id"]] = Document(d["id"], d["title"], d["doc_type"], tuple(d["codes"]), tuple(d["topics"]),
                                 app["reviewed"], app["reviewed_by"], tuple(app["work_codes"]),
                                 tuple((c["id"], c["text"]) for c in app["conditions"]), tuple(versions))
    for doc_id in data["whitelist"]["documents"]:
        if doc_id not in docs:
            problems.append(f"whitelist names unknown document {doc_id}")
    if problems:
        raise GatewayError("INDEX_INVALID", "INDEX failed semantic validation", details={"problems": problems[:50]})
    return Index(data["index_version"], data["rules_version"], data["fixture"], hashlib.sha256(raw).hexdigest(),
                 frozenset(work_codes), docs, frozenset(data["whitelist"]["documents"]),
                 frozenset(data["whitelist"]["notebooklm_notebooks"]))


class _StringDateLoader(yaml.SafeLoader):
    """SafeLoader that leaves timestamps as strings, so the schema validates the text form."""


for _first, _resolvers in list(_StringDateLoader.yaml_implicit_resolvers.items()):
    _StringDateLoader.yaml_implicit_resolvers[_first] = [
        (tag, rx) for tag, rx in _resolvers if tag != "tag:yaml.org,2002:timestamp"]


def select_version(doc: Document, day: dt.date | None, requested: str | None) -> tuple[Version, list[str]]:
    """Pick the version to read. Returns (version, notes). Raises on not-found or ambiguity.

    An explicitly requested version only says which file to read. It does not make the
    version eligible or unambiguous: callers must gate a trusted/verified result on version_check().
    """
    usable = [v for v in doc.versions if v.status not in ("draft", "withdrawn")]
    if requested is not None:
        for v in doc.versions:
            if v.version == requested:
                return v, [f"version {requested} requested explicitly"]
        raise GatewayError("SOURCE_NOT_FOUND", f"{doc.id} has no version {requested!r} in INDEX")
    if day is None:
        active = [v for v in usable if v.status == "active"]
        if len(active) == 1:
            return active[0], ["no assessment_date: using the single active version"]
        raise GatewayError("VERSION_AMBIGUOUS", f"{doc.id}: no assessment_date and {len(active)} active versions",
                           details={"versions": [v.version for v in active]})
    in_force = [v for v in usable if v.in_force(day)]
    unknown = [v for v in usable if v.in_force(day) is None]
    if len(in_force) == 1 and not unknown:
        return in_force[0], [f"version {in_force[0].version} in force on {day.isoformat()}"]
    if len(in_force) > 1 or (in_force and unknown):
        raise GatewayError("VERSION_AMBIGUOUS", f"{doc.id}: several versions may apply on {day.isoformat()}",
                           details={"versions": [v.version for v in in_force + unknown]})
    if unknown:
        raise GatewayError("VERSION_AMBIGUOUS", f"{doc.id}: effective dates unknown in INDEX",
                           details={"versions": [v.version for v in unknown]})
    raise GatewayError("SOURCE_NOT_FOUND", f"{doc.id}: no version in force on {day.isoformat()}")


def version_check(doc: Document, version: Version, day: dt.date | None) -> tuple[str, str]:
    """Is `version` the eligible, unambiguous version for `day`? -> (PASS | FAIL | UNKNOWN, detail).

    Same rules as date-based select_version: draft/withdrawn versions are never eligible,
    overlapping or unknown effectivity is ambiguous, and the version must be the one in force.
    """
    if version.status in ("draft", "withdrawn"):
        return "FAIL", f"{version.source_key} has status {version.status} in INDEX"
    if day is None:
        return "UNKNOWN", "no assessment_date; cannot confirm the version in force"
    try:
        chosen, _ = select_version(doc, day, None)
    except GatewayError as e:
        return ("UNKNOWN" if e.code == "VERSION_AMBIGUOUS" else "FAIL"), f"{e.code}: {e.message}"
    if chosen.version != version.version:
        return "FAIL", f"version in force on {day.isoformat()} is {chosen.version}"
    return "PASS", f"{version.source_key} in force on {day.isoformat()}"


def applicability(index: Index, doc: Document, version: Version, work_code: str | None,
                  day: dt.date | None, conditions: dict[str, bool] | None) -> Applicability:
    """APPLICABLE only when every input is present and INDEX (owner-reviewed) says so."""
    missing, basis = [], []
    if not work_code:
        missing.append("work_code")
    if day is None:
        missing.append("assessment_date")
    if not doc.reviewed:
        return Applicability(UNKNOWN, ["INDEX applicability for this document is not owner-reviewed"],
                             missing + ["owner review of applicability metadata"])
    if work_code and work_code not in index.work_codes:
        return Applicability(UNKNOWN, [f"work_code {work_code} is not defined in INDEX"],
                             missing + ["a work_code defined in INDEX"])
    if work_code and work_code not in doc.work_codes:
        return Applicability(NOT_APPLICABLE, [f"INDEX does not list work_code {work_code} for {doc.id}"
                                              f" (reviewed_by: {doc.reviewed_by})"], [])
    if day is not None:
        force = version.in_force(day)
        if force is False:
            return Applicability(NOT_APPLICABLE, [f"{version.source_key} is not in force on {day.isoformat()}"], [])
        if force is None:
            missing.append("effective dates for this version in INDEX")
    if missing:
        return Applicability(UNKNOWN, basis, missing)
    conditions = conditions or {}
    for cid, text in doc.conditions:
        if cid not in conditions:
            missing.append(f"project_context.conditions.{cid} ({text})")
        elif conditions[cid] is False:
            return Applicability(NOT_APPLICABLE, [f"condition {cid} answered false: {text}"], [])
        else:
            basis.append(f"condition {cid} confirmed in project_context")
    if missing:
        return Applicability(UNKNOWN, basis, missing)
    basis.insert(0, f"INDEX lists work_code {work_code} for {doc.id} (reviewed_by: {doc.reviewed_by})")
    basis.insert(1, f"{version.source_key} in force on {day.isoformat()}")
    return Applicability(APPLICABLE, basis, [])
