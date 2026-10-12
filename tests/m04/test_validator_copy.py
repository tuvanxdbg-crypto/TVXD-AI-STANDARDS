"""D5/§5: the validator copy in cadaudit/_schema.py accepts and rejects what gateway/schema.py accepts and rejects.

The tests pin the keyword set and run valid and invalid instances for every supported keyword, so the copy cannot
silently become looser than the original. gateway/ is not imported (M04 §5, decision 3).
"""
import ast
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import m04_helpers  # noqa: F401  (puts the repo root on sys.path)
from cadaudit import _schema
from m04_helpers import REPO, read_bytes


def ok(value, schema):
    return _schema.validate(value, schema) == []


class KeywordSet(unittest.TestCase):
    def test_header_names_the_source(self):
        src = read_bytes(os.path.join(REPO, "cadaudit", "_schema.py")).decode("utf-8")
        self.assertIn("COPIED from gateway/schema.py at commit d35b574", src)

    def test_supported_keywords_are_those_of_the_original(self):
        self.assertEqual(_schema.KNOWN, {
            "$schema", "$id", "$defs", "title", "description", "type", "enum", "const", "required", "properties",
            "additionalProperties", "items", "minItems", "maxItems", "minLength", "maxLength", "pattern", "format",
            "minimum", "maximum", "anyOf", "oneOf", "$ref", "default", "examples"})
        self.assertEqual(set(_schema.TYPES), {"string", "boolean", "object", "array", "null"})

    def test_schema_dir_is_cadaudit_schemas(self):
        self.assertEqual(os.path.realpath(_schema.SCHEMA_DIR), os.path.realpath(os.path.join(REPO, "cadaudit", "schemas")))

    def test_package_has_no_import_of_gateway(self):
        for name in os.listdir(os.path.join(REPO, "cadaudit")):
            if name.endswith(".py"):
                tree = ast.parse(read_bytes(os.path.join(REPO, "cadaudit", name)).decode("utf-8"))
                for node in ast.walk(tree):
                    mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                            else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
                    for m in mods:
                        self.assertNotEqual(m.split(".")[0], "gateway", f"{name} imports {m}")


class UnknownKeywordRejectedAtLoad(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="m04-schema-")
        patcher = mock.patch.object(_schema, "SCHEMA_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        _schema.load.cache_clear()
        self.addCleanup(_schema.load.cache_clear)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def put(self, name, doc):
        with open(os.path.join(self.dir, name), "wb") as f:
            f.write(json.dumps(doc).encode("utf-8"))

    def test_unknown_keyword_top_level(self):
        self.put("a.json", {"type": "array", "uniqueItems": True})
        with self.assertRaisesRegex(ValueError, "unsupported schema keywords"):
            _schema.load("a.json")

    def test_unknown_keyword_nested_everywhere(self):
        cases = {
            "props": {"type": "object", "properties": {"x": {"type": "string", "pattern_properties": {}}}},
            "items": {"type": "array", "items": {"type": "string", "uniqueItems": True}},
            "any_of": {"anyOf": [{"type": "string"}, {"type": "number", "multipleOf": 2}]},
            "defs": {"$defs": {"d": {"type": "string", "contentEncoding": "base64"}}, "type": "object"},
            "additional": {"type": "object", "additionalProperties": {"type": "string", "if": {}}},
            "one_of": {"oneOf": [{"type": "string", "not": {}}]},
        }
        for name, doc in cases.items():
            with self.subTest(name):
                self.put(f"{name}.json", doc)
                with self.assertRaisesRegex(ValueError, "unsupported schema keywords"):
                    _schema.load(f"{name}.json")

    def test_unknown_keyword_on_nodes_without_type_properties_ref_or_anyof(self):
        """R4: the original skipped any node that held only oneOf (or items, enum, ...). Every schema node is checked here."""
        cases = {
            "oneof_wrapper": {"type": "object", "properties": {"x": {"oneOf": [{"type": "string"}], "uniqueItems": True}}},
            "oneof_wrapper_top": {"oneOf": [{"type": "string"}], "not": {}},
            "oneof_wrapper_in_items": {"type": "array", "items": {"oneOf": [{"type": "string"}], "if": {}}},
            "oneof_wrapper_in_oneof": {"oneOf": [{"oneOf": [{"type": "string"}], "contentEncoding": "x"}]},
            "enum_only": {"type": "object", "properties": {"x": {"enum": ["a"], "multipleOf": 2}}},
            "empty_with_extra": {"type": "object", "properties": {"x": {"minLength": 1, "dependentRequired": {}}}},
            "oneof_wrapper_bad_format": {"type": "object", "properties": {"x": {"oneOf": [{"type": "string"}], "format": "email"}}},
        }
        for name, doc in cases.items():
            with self.subTest(name):
                self.put(f"{name}.json", doc)
                with self.assertRaisesRegex(ValueError, "unsupported (schema keywords|format)"):
                    _schema.load(f"{name}.json")

    def test_a_oneof_only_wrapper_with_known_keywords_still_loads(self):
        self.put("w.json", {"type": "object", "properties": {"x": {"oneOf": [{"type": "string"}, {"type": "null"}], "description": "d"}}})
        self.assertIn("x", _schema.load("w.json")["properties"])

    def test_header_says_the_tightening_is_deliberate(self):
        src = read_bytes(os.path.join(REPO, "cadaudit", "_schema.py")).decode("utf-8")
        self.assertIn("DELIBERATE TIGHTENING", src)

    def test_unsupported_format_rejected(self):
        self.put("f.json", {"type": "string", "format": "email"})
        with self.assertRaisesRegex(ValueError, "unsupported format"):
            _schema.load("f.json")

    def test_supported_keywords_load(self):
        self.put("g.json", {"$schema": "x", "$id": "g.json", "title": "t", "type": "object", "required": [],
                            "properties": {"a": {"type": "string", "format": "date"}}, "additionalProperties": False})
        self.assertEqual(_schema.load("g.json")["title"], "t")


class ValidatorBehaviour(unittest.TestCase):
    def test_types(self):
        cases = [("string", "a", True), ("string", 1, False), ("boolean", True, True), ("boolean", 1, False),
                 ("integer", 3, True), ("integer", 3.0, False), ("integer", True, False), ("number", 3.5, True),
                 ("number", True, False), ("null", None, True), ("null", 0, False), ("object", {}, True),
                 ("object", [], False), ("array", [], True), ("array", {}, False)]
        for t, v, want in cases:
            with self.subTest(t=t, v=v):
                self.assertEqual(ok(v, {"type": t}), want)
        self.assertTrue(ok(None, {"type": ["string", "null"]}))
        self.assertFalse(ok(1, {"type": ["string", "null"]}))

    def test_enum_const(self):
        self.assertTrue(ok("A", {"type": "string", "enum": ["A", "B"]}))
        self.assertFalse(ok("C", {"type": "string", "enum": ["A", "B"]}))
        self.assertTrue(ok(None, {"type": ["string", "null"], "enum": ["A", None]}))
        self.assertTrue(ok("READ_ONLY", {"type": "string", "const": "READ_ONLY"}))
        self.assertFalse(ok("READ_WRITE", {"type": "string", "const": "READ_ONLY"}))
        self.assertFalse(ok(True, {"type": "boolean", "const": False}))
        self.assertTrue(ok(False, {"type": "boolean", "const": False}))
        self.assertFalse(ok(0, {"type": "boolean", "const": False}))   # 0 is not a boolean

    def test_required_properties_additional(self):
        s = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}, "additionalProperties": False}
        self.assertTrue(ok({"a": "x"}, s))
        self.assertFalse(ok({}, s))
        self.assertFalse(ok({"a": "x", "b": 1}, s))
        self.assertFalse(ok({"a": 1}, s))
        typed = {"type": "object", "additionalProperties": {"type": "number"}}
        self.assertTrue(ok({"x": 1}, typed))
        self.assertFalse(ok({"x": "1"}, typed))

    def test_arrays(self):
        s = {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string"}}
        self.assertTrue(ok(["a"], s))
        self.assertFalse(ok([], s))
        self.assertFalse(ok(["a", "b", "c"], s))
        self.assertFalse(ok(["a", 1], s))

    def test_strings(self):
        s = {"type": "string", "minLength": 2, "maxLength": 3, "pattern": "^[a-z]+$"}
        self.assertTrue(ok("ab", s))
        self.assertFalse(ok("a", s))
        self.assertFalse(ok("abcd", s))
        self.assertFalse(ok("A1", s))

    def test_formats(self):
        self.assertTrue(ok("2026-10-12", {"type": "string", "format": "date"}))
        self.assertFalse(ok("2026-13-12", {"type": "string", "format": "date"}))
        self.assertTrue(ok("2026-10-12T10:00:00+07:00", {"type": "string", "format": "date-time"}))
        self.assertTrue(ok("2026-10-12T10:00:00Z", {"type": "string", "format": "date-time"}))
        self.assertFalse(ok("2026-10-12T10:00:00", {"type": "string", "format": "date-time"}))   # no timezone
        self.assertFalse(ok("yesterday", {"type": "string", "format": "date-time"}))

    def test_numbers(self):
        s = {"type": "number", "minimum": 0, "maximum": 10}
        self.assertTrue(ok(5, s))
        self.assertFalse(ok(-1, s))
        self.assertFalse(ok(11, s))

    def test_any_of_one_of(self):
        any_s = {"anyOf": [{"type": "string"}, {"type": "number"}]}
        self.assertTrue(ok("a", any_s))
        self.assertFalse(ok(None, any_s))
        one_s = {"oneOf": [{"type": "number"}, {"type": "integer"}]}
        self.assertTrue(ok(1.5, one_s))
        self.assertFalse(ok(1, one_s))     # matches both
        self.assertFalse(ok("x", one_s))   # matches none

    def test_refs(self):
        root = {"$defs": {"h": {"type": "string", "pattern": "^[0-9A-F]+$"}}, "type": "object",
                "properties": {"x": {"$ref": "#/$defs/h"}}}
        self.assertTrue(ok({"x": "2A"}, root))
        self.assertFalse(ok({"x": "zz"}, root))
        cross = {"$ref": "cad_read.v1.json#/$defs/handle"}
        self.assertTrue(ok("2A3F", cross))
        self.assertFalse(ok("2a3f", cross))


class RealSchemas(unittest.TestCase):
    NAMES = ("cad_read.v1.json", "cad_rules.v1.json", "cad_audit_report.v1.json")

    def walk(self, node, where, found):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                found.append((where, node.get("additionalProperties")))
            for k, v in node.items():
                self.walk(v, f"{where}/{k}", found)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                self.walk(v, f"{where}[{i}]", found)

    def test_schemas_load_and_have_id_and_title(self):
        for n in self.NAMES:
            with self.subTest(n):
                s = _schema.load(n)
                self.assertEqual(s["$id"], n)
                self.assertTrue(s["title"])
                self.assertEqual(s["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_additional_properties_false_everywhere(self):
        for n in self.NAMES:
            found: list = []
            self.walk(_schema.load(n), n, found)
            self.assertTrue(found)
            for where, value in found:
                with self.subTest(where):
                    self.assertIs(value, False)

    def test_cad_read_instances(self):
        good = json.loads(read_bytes(os.path.join(REPO, "tests", "m04", "fixtures", "cad_read_pass.json")))
        self.assertEqual(_schema.check(good, "cad_read.v1.json"), [])
        bad_extra = json.loads(json.dumps(good))
        bad_extra["layers"][0]["extra"] = 1
        self.assertTrue(_schema.check(bad_extra, "cad_read.v1.json"))
        for path, value in (("read_mode", "READ_WRITE"), ("dwg_modified", True), ("dwg_modified", 0),
                            ("sha256", "XYZ"), ("file_name", "C:\\x\\a.dwg"), ("file_name", "a/b.dwg"),
                            ("extracted_at", "2026-10-12 10:00")):
            bad = json.loads(json.dumps(good))
            bad["drawing"][path] = value
            with self.subTest(path=path, value=value):
                self.assertTrue(_schema.check(bad, "cad_read.v1.json"))
        for g in ("layers", "blocks", "block_refs", "attributes", "texts", "dimensions", "xrefs"):
            bad = json.loads(json.dumps(good))
            del bad[g][0]["handle"]
            with self.subTest(missing_handle=g):
                self.assertTrue(_schema.check(bad, "cad_read.v1.json"))
        bad = json.loads(json.dumps(good))
        bad["xrefs"][0]["name"] = "C:\\Users\\someone\\site.dwg"
        self.assertTrue(_schema.check(bad, "cad_read.v1.json"))
        bad = json.loads(json.dumps(good))
        bad["xrefs"][0]["path_status"] = "MAYBE"
        self.assertTrue(_schema.check(bad, "cad_read.v1.json"))

    def test_rules_schema_rejects_unknown_check_and_extras(self):
        rule = {"id": "R-X", "title": "t", "status": "FIXTURE", "source": None, "applies_to": "layers",
                "selector": {}, "check": {"type": "name_pattern", "field": "name", "pattern": "A-.*"},
                "standard_required": False}
        doc = {"schema": "tvxd.cadaudit.rules/v1", "rules_version": "1", "rules": [rule]}
        self.assertEqual(_schema.check(doc, "cad_rules.v1.json"), [])
        for mutate in (lambda r: r["check"].update(type="python_expression"),
                       lambda r: r["check"].update(extra=1),
                       lambda r: r.update(status="DONE"),
                       lambda r: r.update(applies_to="polylines"),
                       lambda r: r["selector"].update(unknown_key="x"),
                       lambda r: r.update(unexpected=1)):
            bad = json.loads(json.dumps(doc))
            mutate(bad["rules"][0])
            self.assertTrue(_schema.check(bad, "cad_rules.v1.json"))


if __name__ == "__main__":
    unittest.main()
