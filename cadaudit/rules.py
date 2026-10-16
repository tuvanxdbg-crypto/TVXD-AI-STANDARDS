"""Load, validate and classify the rule file (D3, D4). YAML is read only with yaml.safe_load, then checked against
cad_rules.v1.json. Contradictory or unknown configuration is rejected at load time.
"""
import hashlib
import re
from dataclasses import dataclass

import yaml

from . import _schema
from .errors import CadAuditError
from .model import (CHECK_TYPES, DEFAULT_MAX_LENGTH, FIELDS, GROUPS, SELECTOR_GROUPS)

INTERNAL_ONLY = "INTERNAL_ONLY"
STANDARD_REQUIRED = "STANDARD_REQUIRED"
DECLARED = "DECLARED"
UPGRADED = "UPGRADED_DIMENSION_RANGE_NO_INTERNAL_SOURCE"


@dataclass
class Rule:
    id: str
    title: str
    status: str
    source: str | None
    applies_to: str
    selector: dict
    check: dict
    standard_required: bool
    standard_hint: str | None
    classification: str
    classification_reason: str
    reads_groups: tuple
    name_regex: object = None          # compiled selector name_pattern
    check_regex: object = None         # compiled check pattern


@dataclass
class RuleSet:
    rules_version: str
    sha256: str
    rules: list


def _bad(rule_id: str, why: str):
    raise CadAuditError("RULE_INVALID", f"rule {rule_id}: {why}")


def _kind_of(rule_id: str, group: str, field: str) -> str:
    kinds = FIELDS[group]
    if field not in kinds:
        _bad(rule_id, f"field {field!r} does not exist in group {group}")
    return kinds[field]


def _compile(rule_id: str, pattern: str):
    try:
        return re.compile(pattern)
    except re.error as e:
        _bad(rule_id, f"pattern does not compile: {e}")


def _same_kind_values(kind: str, values: list) -> bool:
    for v in values:
        if kind == "str" and not isinstance(v, str):
            return False
        if kind == "num" and (isinstance(v, bool) or not isinstance(v, (int, float))):
            return False
        if kind == "bool" and not isinstance(v, bool):
            return False
    return True


def _check_uses_block_name(check: dict) -> bool:
    """True when the check reads the block name of a block reference (a value that belongs to the blocks group)."""
    fields = (check.get("field"), check.get("field_a"), check.get("field_b"))
    return "block_name" in fields


def compute_reads_groups(applies_to: str, selector: dict, check: dict) -> tuple:
    """applies_to plus every group the selector or the check refers to, in canonical group order (D5)."""
    reads = {applies_to}
    # Any reference to a block name (selector block_name, selector name_pattern on block_refs, or a check on the
    # block_name field) is a reference to the blocks group: an unreadable blocks table must never give a PASS.
    if applies_to in ("block_refs", "attributes") and "block_name" in selector:
        reads.add("blocks")
    if applies_to == "block_refs" and ("name_pattern" in selector or _check_uses_block_name(check)):
        reads.add("blocks")
    if "layer" in selector and applies_to != "layers":
        reads.add("layers")
        if applies_to == "attributes":
            reads.add("block_refs")          # the layer belongs to the parent block reference
    if "block_name" in selector and applies_to == "attributes":
        reads.add("block_refs")              # the block name belongs to the parent block reference
    if check.get("type") == "required_field" and "attribute_tag" in check:
        reads.add("attributes")
    return tuple(g for g in GROUPS if g in reads)


def _finite(x) -> bool:
    """A finite number that also converts to float (a huge integer would overflow in later comparisons)."""
    try:
        f = float(x)
    except OverflowError:
        return False
    return f == f and abs(f) != float("inf")


def _validate_rule(raw: dict) -> Rule:
    rid, group, sel, chk = raw["id"], raw["applies_to"], raw["selector"], raw["check"]
    # '$' in a schema pattern also matches before a trailing newline, so the closed identifiers are re-checked.
    if not re.fullmatch(r"[A-Z][A-Z0-9_-]{1,63}", rid):
        raise CadAuditError("RULES_SCHEMA_INVALID", f"rule id {rid!r} is not [A-Z][A-Z0-9_-]{{1,63}}")
    hint = raw.get("standard_hint")
    if hint is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,63}", hint):
        raise CadAuditError("RULES_SCHEMA_INVALID", f"rule {rid}: standard_hint has characters outside the allowed set")
    for key in ("min", "max", "tolerance"):
        if key in chk and not _finite(chk[key]):
            _bad(rid, f"{key} must be a finite number")
    if raw.get("standard_hint") is not None and raw["standard_required"] is False:
        raise CadAuditError("RULE_CONFIG_CONTRADICTORY",
                            f"rule {rid}: standard_hint is set but standard_required is false")
    for key in sel:
        if group not in SELECTOR_GROUPS[key]:
            _bad(rid, f"selector key {key!r} is not allowed for group {group}")
    name_regex = _compile(rid, sel["name_pattern"]) if "name_pattern" in sel else None

    ctype = chk["type"]
    if ctype not in CHECK_TYPES:  # the schema already rejects this; kept fail-closed
        _bad(rid, f"unknown check type {ctype!r}")
    check_regex = None
    if ctype == "name_pattern":
        if _kind_of(rid, group, chk["field"]) != "str":
            _bad(rid, "name_pattern needs a text field")
        check_regex = _compile(rid, chk["pattern"])
    elif ctype == "allowed_values":
        kind = _kind_of(rid, group, chk["field"])
        if not _same_kind_values(kind, chk["values"]):
            _bad(rid, f"allowed_values entries must all be of the field's type ({kind})")
    elif ctype == "numeric_range":
        if _kind_of(rid, group, chk["field"]) != "num":
            _bad(rid, "numeric_range needs a numeric field")
        if "min" not in chk and "max" not in chk:
            _bad(rid, "numeric_range needs min, max or both")
        if "min" in chk and "max" in chk and chk["min"] > chk["max"]:
            _bad(rid, "numeric_range min is greater than max")
    elif ctype == "required_field":
        if ("field" in chk) == ("attribute_tag" in chk):
            _bad(rid, "required_field needs exactly one of field and attribute_tag")
        if "field" in chk:
            _kind_of(rid, group, chk["field"])
        elif group != "block_refs":
            _bad(rid, "attribute_tag is only allowed for group block_refs")
    elif ctype == "equals_field":
        ka, kb = _kind_of(rid, group, chk["field_a"]), _kind_of(rid, group, chk["field_b"])
        if chk["field_a"] == chk["field_b"]:
            _bad(rid, "equals_field needs two different fields")
        if ka != kb:
            _bad(rid, f"equals_field compares fields of different types ({ka} vs {kb})")
        if "tolerance" in chk and ka != "num":
            _bad(rid, "tolerance is only allowed when the fields are numeric")
    elif ctype == "xref_resolved":
        if group != "xrefs":
            _bad(rid, "xref_resolved only applies to group xrefs")

    # D4: the classifier can raise a rule to STANDARD_REQUIRED, never lower it.
    classification, reason = (STANDARD_REQUIRED, DECLARED) if raw["standard_required"] else (INTERNAL_ONLY, DECLARED)
    has_source = isinstance(raw["source"], str) and raw["source"].strip() != ""    # a blank source is no source
    if classification == INTERNAL_ONLY and group == "dimensions" and ctype == "numeric_range" and not has_source:
        classification, reason = STANDARD_REQUIRED, UPGRADED
    return Rule(id=rid, title=raw["title"], status=raw["status"], source=raw["source"], applies_to=group,
                selector=dict(sel), check=dict(chk), standard_required=raw["standard_required"],
                standard_hint=raw.get("standard_hint"), classification=classification,
                classification_reason=reason, reads_groups=compute_reads_groups(group, sel, chk),
                name_regex=name_regex, check_regex=check_regex)


def _reject_duplicate_keys(text: str) -> None:
    """Fail closed on every YAML construct that lets a later or shared value silently decide a key (D4):
    - a mapping that repeats a key (yaml.safe_load keeps the LAST one, so `standard_required: false` could undo `true`);
    - a merge key `<<` (REVIEW_V1 5489351827: an inherited `standard_required: true` could be overridden, or two merged
      anchors could conflict, without any key appearing twice in one mapping);
    - any alias `*x` (the same node reached twice): rules must spell every value out where it applies;
    - a key that is not a plain scalar.
    The node graph is composed with the safe loader class (no Loader= argument anywhere); nothing is constructed and no
    tag is interpreted. The walk is iterative and stops at the first node reached a second time, so aliases cannot
    make it loop or blow up. Values used afterwards still come from yaml.safe_load."""
    loader = yaml.SafeLoader(text)
    try:
        root = loader.get_single_node()
    finally:
        loader.dispose()
    seen = set()
    todo = [root]
    while todo:
        node = todo.pop()
        if node is None:
            continue
        if id(node) in seen:
            raise CadAuditError("RULES_YAML_ALIAS_OR_MERGE", "YAML aliases (*name) are not allowed in rules")
        seen.add(id(node))
        if isinstance(node, yaml.MappingNode):
            keys = set()
            for key, value in node.value:
                if not isinstance(key, yaml.ScalarNode):
                    raise CadAuditError("RULES_SCHEMA_INVALID", "a mapping key is not a plain scalar")
                if key.tag == "tag:yaml.org,2002:merge" or key.value == "<<":
                    raise CadAuditError("RULES_YAML_ALIAS_OR_MERGE", "YAML merge keys (<<) are not allowed in rules")
                if key.value in keys:
                    raise CadAuditError("RULES_DUPLICATE_KEY", f"mapping key {key.value[:40]!r} appears twice in the same mapping")
                keys.add(key.value)
                todo.append(key)
                todo.append(value)
        elif isinstance(node, yaml.SequenceNode):
            todo.extend(node.value)


def load_rules(data: bytes) -> RuleSet:
    try:
        text = data.decode("utf-8-sig")
        _reject_duplicate_keys(text)
        doc = yaml.safe_load(text)
    except (UnicodeDecodeError, yaml.YAMLError, RecursionError) as e:
        raise CadAuditError("RULES_NOT_YAML", f"not valid YAML for safe_load: {type(e).__name__}") from None
    errs = _schema.check(doc, "cad_rules.v1.json")
    if errs:
        raise CadAuditError("RULES_SCHEMA_INVALID", f"{len(errs)} problem(s), first: {errs[0]}")
    ids = set()
    rules = []
    for raw in doc["rules"]:
        if raw["id"] in ids:
            raise CadAuditError("RULES_DUPLICATE_ID", f"rule id {raw['id']} appears twice")
        ids.add(raw["id"])
        rules.append(_validate_rule(raw))
    return RuleSet(rules_version=doc["rules_version"], sha256=hashlib.sha256(data).hexdigest(), rules=rules)
