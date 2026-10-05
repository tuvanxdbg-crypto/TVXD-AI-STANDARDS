"""Versioned JSON schemas (gateway/schemas/*.json) and a small validator for the subset they use.

Supported keywords: type, enum, const, required, properties, additionalProperties,
items, minItems, maxItems, minLength, maxLength, pattern, format (date, date-time),
minimum, maximum, anyOf, oneOf, $ref (to "#/$defs/..." or "<file>.json[#/$defs/...]").
Unsupported keywords in a schema file are rejected at load time, so a schema can
never silently claim a check the validator does not perform.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
KNOWN = {"$schema", "$id", "$defs", "title", "description", "type", "enum", "const", "required",
         "properties", "additionalProperties", "items", "minItems", "maxItems", "minLength",
         "maxLength", "pattern", "format", "minimum", "maximum", "anyOf", "oneOf", "$ref",
         "default", "examples"}
TYPES = {"string": str, "boolean": bool, "object": dict, "array": list, "null": type(None)}


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    _check_keywords(schema, name)
    return schema


def _check_keywords(node, where: str) -> None:
    if isinstance(node, dict):
        if "type" in node or "properties" in node or "$ref" in node or "anyOf" in node:
            unknown = set(node) - KNOWN
            if unknown:
                raise ValueError(f"{where}: unsupported schema keywords {sorted(unknown)}")
            if node.get("format") not in (None, "date", "date-time"):
                raise ValueError(f"{where}: unsupported format {node['format']!r}")
        for k, v in node.items():
            if k in ("properties", "$defs"):
                for name, sub in v.items():
                    _check_keywords(sub, f"{where}/{k}/{name}")
            elif k in ("items", "additionalProperties") and isinstance(v, dict):
                _check_keywords(v, f"{where}/{k}")
            elif k in ("anyOf", "oneOf"):
                for i, sub in enumerate(v):
                    _check_keywords(sub, f"{where}/{k}/{i}")


def _resolve(ref: str, root: dict) -> tuple[dict, dict]:
    file, _, pointer = ref.partition("#")
    doc = load(file) if file else root
    node = doc
    for part in [p for p in pointer.split("/") if p]:
        node = node[part]
    return node, doc


def _is_type(value, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, TYPES[t])


def _check_format(value: str, fmt: str) -> bool:
    try:
        if fmt == "date":
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and bool(dt.date.fromisoformat(value))
        if fmt == "date-time":
            return bool(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo)
    except ValueError:
        return False
    return True


def validate(value, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Return a list of 'path: problem' strings; empty means valid."""
    root = root if root is not None else schema
    if "$ref" in schema:
        target, doc = _resolve(schema["$ref"], root)
        return validate(value, target, doc, path)
    errs: list[str] = []
    for key in ("anyOf", "oneOf"):
        if key in schema:
            passing = [o for o in schema[key] if not validate(value, o, root, path)]
            if not passing or (key == "oneOf" and len(passing) != 1):
                errs.append(f"{path}: does not match {'exactly one' if key == 'oneOf' else 'any'} allowed form")
    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, t) for t in allowed):
            return [f"{path}: expected {'/'.join(allowed)}"]
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: must be one of {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: does not match pattern")
        if "format" in schema and not _check_format(value, schema["format"]):
            errs.append(f"{path}: not a valid {schema['format']}")
    if _is_type(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                errs += validate(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errs.append(f"{path}: missing required '{req}'")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
            elif extra is False:
                errs.append(f"{path}: unexpected property '{k}'")
            elif isinstance(extra, dict):
                errs += validate(v, extra, root, f"{path}.{k}")
    return errs


def check(value, name: str) -> list[str]:
    return validate(value, load(name))
