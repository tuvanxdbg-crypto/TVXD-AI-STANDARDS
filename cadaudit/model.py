"""Closed vocabularies shared by the loader, the rules loader and the evaluator."""
GROUPS = ("layers", "blocks", "block_refs", "attributes", "texts", "dimensions", "xrefs", "units")

# Field kinds: "str", "num" (int or float, never bool), "bool". Enumerated strings (text_type, path_status) are "str".
FIELDS = {
    "layers": {"name": "str", "color": "num", "linetype": "str", "lineweight": "num", "plot": "bool",
               "frozen": "bool", "off": "bool", "locked": "bool", "space": "str"},
    "blocks": {"name": "str", "is_xref_dependent": "bool", "entity_count": "num", "space": "str"},
    "block_refs": {"block_name": "str", "layer": "str", "insert_x": "num", "insert_y": "num", "insert_z": "num",
                   "scale_x": "num", "scale_y": "num", "scale_z": "num", "rotation": "num", "space": "str"},
    "attributes": {"parent_handle": "str", "tag": "str", "value": "str", "space": "str"},
    "texts": {"text_type": "str", "value": "str", "style": "str", "font": "str", "height": "num",
              "layer": "str", "space": "str"},
    "dimensions": {"dim_type": "str", "measured_value": "num", "display_value": "num", "dimscale": "num",
                   "layer": "str", "space": "str"},
    "xrefs": {"name": "str", "path_status": "str", "space": "str"},
    "units": {"insunits": "num", "measurement": "num"},
}

# Field used as the identifying evidence when a rule has no field of its own to point at.
PRIMARY_FIELD = {"layers": "name", "blocks": "name", "block_refs": "block_name", "attributes": "tag",
                 "texts": "text_type", "dimensions": "dim_type", "xrefs": "name", "units": "insunits"}

# Selector keys allowed per group (closed list).
SELECTOR_GROUPS = {
    "space": ("layers", "blocks", "block_refs", "attributes", "texts", "dimensions", "xrefs"),
    "layer": ("block_refs", "attributes", "texts", "dimensions"),
    "block_name": ("block_refs", "attributes"),
    "name_pattern": ("layers", "blocks", "block_refs", "xrefs"),
    "tag": ("attributes",),
}
NAME_FIELD = {"layers": "name", "blocks": "name", "block_refs": "block_name", "xrefs": "name"}

VERDICTS = ("PASS", "FAIL", "UNKNOWN")
UNKNOWN_REASONS = ("COVERAGE_INCOMPLETE", "FIELD_MISSING", "STANDARD_LOOKUP_NOT_ENABLED", "NO_OBJECTS_IN_SCOPE")
CHECK_TYPES = ("name_pattern", "allowed_values", "numeric_range", "required_field", "equals_field", "xref_resolved")

COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"
NOT_EXTRACTED = "NOT_EXTRACTED"

DEFAULT_MAX_LENGTH = 255
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_RULES_BYTES = 1024 * 1024


def evidence_id(file_id: str, group: str, obj: dict, field: str) -> str:
    """CADEV:<file_id>:<handle>:<field>. units has no handle: CADEV:<file_id>:FILE:units.<field>."""
    if group == "units":
        return f"CADEV:{file_id}:FILE:units.{field}"
    return f"CADEV:{file_id}:{obj['handle']}:{field}"


def file_evidence_id(file_id: str, path: str) -> str:
    """File-level value, e.g. coverage.texts.status or drawing.read_mode."""
    return f"CADEV:{file_id}:FILE:{path}"
