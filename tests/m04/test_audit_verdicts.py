"""D4/D5/D7: verdicts and reasons on the fixtures, the two precedence lists, classification, and input errors."""
import copy
import json
import os
import unittest

import m04_helpers  # noqa: F401
from cadaudit.audit import run_audit
from cadaudit.errors import CadAuditError
from m04_helpers import World, check_args, fx, read_bytes, read_json, run_cli, tmp_files_under

TS = "2026-10-12T10:00:00+07:00"


def audit_fixture(inp, rules):
    return run_audit(read_bytes(fx(inp)), read_bytes(fx(rules)), TS)


def audit_mem(doc, rules, ts=TS):
    """doc: CAD_READ dict; rules: list of rule dicts. JSON is valid YAML, so safe_load reads it."""
    rules_doc = {"schema": "tvxd.cadaudit.rules/v1", "rules_version": "t.1", "rules": rules}
    return run_audit(json.dumps(doc).encode(), json.dumps(rules_doc).encode(), ts)


def rule(rid="R-T", applies_to="texts", selector=None, check=None, std=False, source="FIXTURE (fake)", hint=None, status="FIXTURE"):
    r = {"id": rid, "title": "t", "status": status, "source": source, "applies_to": applies_to,
         "selector": selector or {}, "check": check, "standard_required": std}
    if hint:
        r["standard_hint"] = hint
    return r


def base():
    return read_json(fx("cad_read_pass.json"))


def set_cov(doc, group, status, expected, enumerated, reason):
    doc["coverage"][group] = {"status": status, "expected": expected, "enumerated": enumerated, "reason": reason}


HEIGHT = {"type": "numeric_range", "field": "height", "min": 2.5, "max": 3.5}
FONT = {"type": "allowed_values", "field": "font", "values": ["arial.ttf"]}


def by_id(report):
    return {x["rule_id"]: x for x in report["rules"]}


def rows_of(report, rid):
    return [r for r in report["results"] if r["rule_id"] == rid]


class FixtureVerdicts(unittest.TestCase):
    PASS_ALL = {"R-LAYER-NAME", "R-BLOCK-NAME", "R-TEXT-FONT", "R-TEXT-HEIGHT", "R-TITLE-ATTR", "R-DIM-OVERRIDE",
                "R-DIM-SCALE", "R-XREF-RESOLVED", "R-UNITS"}

    def test_pass_fixture(self):
        rep = audit_fixture("cad_read_pass.json", "rules_internal.yaml")
        self.assertEqual({k: v["verdict"] for k, v in by_id(rep).items()}, {r: "PASS" for r in self.PASS_ALL})
        self.assertEqual(rep["summary"]["overall"], "ALL_RULES_PASS")
        self.assertEqual({r["rule_status"] for r in rep["results"]}, {"FIXTURE"})
        self.assertTrue(all(x["coverage_complete"] for x in rep["rules"]))
        self.assertEqual(rep["summary"]["results_by_verdict"], {"PASS": len(rep["results"]), "FAIL": 0, "UNKNOWN": 0})

    def test_fail_fixture_verdicts_and_evidence(self):
        rep = audit_fixture("cad_read_fail.json", "rules_internal.yaml")
        want = {"R-LAYER-NAME": "FAIL", "R-BLOCK-NAME": "PASS", "R-TEXT-FONT": "FAIL", "R-TEXT-HEIGHT": "FAIL",
                "R-TITLE-ATTR": "FAIL", "R-DIM-OVERRIDE": "FAIL", "R-DIM-SCALE": "PASS", "R-XREF-RESOLVED": "FAIL",
                "R-UNITS": "PASS"}
        self.assertEqual({k: v["verdict"] for k, v in by_id(rep).items()}, want)
        self.assertEqual(rep["summary"]["overall"], "HAS_FAIL")
        fails = {r["rule_id"]: r for r in rep["results"] if r["verdict"] == "FAIL"}
        self.assertEqual(fails["R-LAYER-NAME"]["handle"], "14")
        self.assertEqual(fails["R-LAYER-NAME"]["evidence_ids"], ["CADEV:F01:14:name"])
        self.assertEqual(fails["R-LAYER-NAME"]["actual"], "wall_01")
        self.assertEqual((fails["R-TEXT-FONT"]["handle"], fails["R-TEXT-FONT"]["evidence_ids"], fails["R-TEXT-FONT"]["actual"]),
                         ("50", ["CADEV:F01:50:font"], "comic.ttf"))
        self.assertEqual((fails["R-TEXT-HEIGHT"]["handle"], fails["R-TEXT-HEIGHT"]["evidence_ids"], fails["R-TEXT-HEIGHT"]["actual"]),
                         ("51", ["CADEV:F01:51:height"], 1.0))
        self.assertEqual((fails["R-TITLE-ATTR"]["handle"], fails["R-TITLE-ATTR"]["evidence_ids"], fails["R-TITLE-ATTR"]["actual"]),
                         ("31", ["CADEV:F01:31:block_name"], None))
        self.assertEqual(fails["R-DIM-OVERRIDE"]["evidence_ids"], ["CADEV:F01:60:measured_value", "CADEV:F01:60:display_value"])
        self.assertEqual((fails["R-DIM-OVERRIDE"]["actual"], fails["R-DIM-OVERRIDE"]["expected"]), (2500.0, 2400.0))
        self.assertEqual((fails["R-XREF-RESOLVED"]["handle"], fails["R-XREF-RESOLVED"]["evidence_ids"], fails["R-XREF-RESOLVED"]["actual"]),
                         ("70", ["CADEV:F01:70:path_status"], "NOT_FOUND"))
        # only the violating objects fail: the other layers and text still pass
        layer_rows = {r["handle"]: r["verdict"] for r in rows_of(rep, "R-LAYER-NAME")}
        self.assertEqual(layer_rows, {"10": "PASS", "11": "PASS", "12": "PASS", "13": "PASS", "14": "FAIL"})
        self.assertTrue(all(x["coverage_complete"] for x in rep["rules"]))

    def test_unknown_fixture(self):
        rep = audit_fixture("cad_read_unknown.json", "rules_internal.yaml")
        rules = by_id(rep)
        for rid in ("R-LAYER-NAME", "R-TEXT-FONT", "R-TEXT-HEIGHT", "R-TITLE-ATTR", "R-DIM-OVERRIDE", "R-DIM-SCALE"):
            self.assertEqual((rules[rid]["verdict"], rules[rid]["reasons"]), ("UNKNOWN", ["COVERAGE_INCOMPLETE"]), rid)
            self.assertFalse(rules[rid]["coverage_complete"], rid)
            self.assertTrue(rules[rid]["evidence_ids"], rid)
        # FAIL kept although the xref group is INCOMPLETE; coverage_complete false next to it
        self.assertEqual(rules["R-XREF-RESOLVED"]["verdict"], "FAIL")
        self.assertIs(rules["R-XREF-RESOLVED"]["coverage_complete"], False)
        self.assertEqual(rules["R-BLOCK-NAME"]["verdict"], "PASS")
        self.assertEqual(rules["R-UNITS"]["verdict"], "PASS")
        self.assertEqual(rep["summary"]["overall"], "HAS_FAIL")
        # null font: object-level FIELD_MISSING with the evidence pointing at the null
        font_rows = {r["handle"]: r for r in rows_of(rep, "R-TEXT-FONT")}
        self.assertEqual((font_rows["50"]["verdict"], font_rows["50"]["reason"]), ("UNKNOWN", "FIELD_MISSING"))
        self.assertEqual(font_rows["50"]["evidence_ids"], ["CADEV:F01:50:font"])
        self.assertEqual(font_rows["51"]["verdict"], "PASS")
        # attribute tag absent while the attributes group is INCOMPLETE: not a FAIL
        title = rows_of(rep, "R-TITLE-ATTR")
        self.assertEqual([(r["verdict"], r["reason"]) for r in title], [("UNKNOWN", "COVERAGE_INCOMPLETE")])
        # no PASS anywhere for a rule whose reads_groups has a non-COMPLETE group
        for x in rep["rules"]:
            if not x["coverage_complete"]:
                self.assertNotEqual(x["verdict"], "PASS", x["rule_id"])

    def test_standard_and_empty_selector_rules(self):
        for inp in ("cad_read_pass.json", "cad_read_fail.json", "cad_read_unknown.json"):
            rep = audit_fixture(inp, "rules_standard.yaml")
            rules = by_id(rep)
            with self.subTest(inp):
                for rid in ("R-STD-LAYER-LW", "R-STD-TEXT-HEIGHT", "R-DIM-RANGE-NOSRC"):
                    self.assertEqual((rules[rid]["verdict"], rules[rid]["reasons"]), ("UNKNOWN", ["STANDARD_LOOKUP_NOT_ENABLED"]))
                    self.assertEqual(rules[rid]["classification"], "STANDARD_REQUIRED")
                    for row in rows_of(rep, rid):
                        self.assertEqual((row["verdict"], row["reason"]), ("UNKNOWN", "STANDARD_LOOKUP_NOT_ENABLED"))
                        self.assertTrue(row["evidence_ids"])
                self.assertEqual((rules["R-EMPTY-SELECTOR"]["verdict"], rules["R-EMPTY-SELECTOR"]["reasons"]),
                                 ("UNKNOWN", ["NO_OBJECTS_IN_SCOPE"]))
                self.assertEqual(rules["R-EMPTY-SELECTOR"]["objects_in_scope"], 0)
                self.assertEqual(rules["R-EMPTY-SELECTOR"]["evidence_ids"], ["CADEV:F01:FILE:coverage.block_refs.status"])
                # the rule-status label rides next to each result
                self.assertEqual(rules["R-DIM-RANGE-NOSRC"]["rule_status"], "PROPOSED")
                for row in rows_of(rep, "R-DIM-RANGE-NOSRC"):
                    self.assertEqual(row["rule_status"], "PROPOSED")

    def test_standard_hint_is_reported_not_cited(self):
        rep = audit_fixture("cad_read_pass.json", "rules_standard.yaml")
        self.assertEqual(by_id(rep)["R-STD-LAYER-LW"]["standard_hint"], "TCVN-FAKE-01")
        self.assertTrue(all(r["standard_hint"] == "TCVN-FAKE-01" for r in rows_of(rep, "R-STD-LAYER-LW")))
        self.assertIsNone(by_id(rep)["R-STD-TEXT-HEIGHT"]["standard_hint"])
        self.assertTrue(all(r["expected"] is None for r in rows_of(rep, "R-STD-LAYER-LW")))


class Classification(unittest.TestCase):
    def test_dimension_range_without_source_is_raised(self):
        rep = audit_fixture("cad_read_pass.json", "rules_standard.yaml")
        r = by_id(rep)
        self.assertEqual((r["R-DIM-RANGE-NOSRC"]["classification"], r["R-DIM-RANGE-NOSRC"]["classification_reason"]),
                         ("STANDARD_REQUIRED", "UPGRADED_DIMENSION_RANGE_NO_INTERNAL_SOURCE"))
        self.assertEqual((r["R-DIM-RANGE-SRC"]["classification"], r["R-DIM-RANGE-SRC"]["classification_reason"]),
                         ("INTERNAL_ONLY", "DECLARED"))
        self.assertEqual(r["R-DIM-RANGE-SRC"]["verdict"], "PASS")
        self.assertEqual(r["R-STD-LAYER-LW"]["classification_reason"], "DECLARED")

    def test_only_dimension_numeric_range_is_raised(self):
        doc = base()
        rules = [rule("R-A", "texts", check=HEIGHT, source=None),                      # texts: not raised
                 rule("R-B", "dimensions", check={"type": "equals_field", "field_a": "measured_value", "field_b": "display_value"}, source=None),
                 rule("R-C", "dimensions", check={"type": "numeric_range", "field": "dimscale", "min": 1, "max": 1}, source=None)]
        r = by_id(audit_mem(doc, rules))
        self.assertEqual([r[k]["classification"] for k in ("R-A", "R-B", "R-C")],
                         ["INTERNAL_ONLY", "INTERNAL_ONLY", "STANDARD_REQUIRED"])

    def test_never_lowered(self):
        doc = base()
        for group, check in (("texts", HEIGHT), ("dimensions", {"type": "numeric_range", "field": "dimscale", "min": 1}),
                             ("layers", {"type": "name_pattern", "field": "name", "pattern": ".*"})):
            for source in (None, "FIXTURE (fake)"):
                r = by_id(audit_mem(doc, [rule("R-X", group, check=check, std=True, source=source)]))["R-X"]
                with self.subTest(group=group, source=source):
                    self.assertEqual((r["classification"], r["verdict"]), ("STANDARD_REQUIRED", "UNKNOWN"))

    def test_hint_with_standard_required_false_is_rejected(self):
        with self.assertRaises(CadAuditError) as cm:
            audit_mem(base(), [rule(check=HEIGHT, hint="TCVN-FAKE-01", std=False)])
        self.assertEqual(cm.exception.code, "RULE_CONFIG_CONTRADICTORY")
        audit_mem(base(), [rule(check=HEIGHT, hint="TCVN-FAKE-01", std=True)])   # accepted

    def test_standard_required_never_pass_or_fail(self):
        """Whatever the data: complete or not, good or bad, null fields, empty groups."""
        docs = {"pass": base(), "fail": read_json(fx("cad_read_fail.json")), "unknown": read_json(fx("cad_read_unknown.json"))}
        nulls = base()
        for t in nulls["texts"]:
            t["height"] = None
            t["font"] = None
        docs["null-fields"] = nulls
        empty = base()
        empty["texts"] = []
        set_cov(empty, "texts", "COMPLETE", 0, 0, None)
        docs["empty-complete"] = empty
        checks = {"texts": [HEIGHT, FONT, {"type": "required_field", "field": "value"}],
                  "block_refs": [{"type": "required_field", "attribute_tag": "DRAWING_NO"}],
                  "xrefs": [{"type": "xref_resolved"}],
                  "dimensions": [{"type": "equals_field", "field_a": "measured_value", "field_b": "display_value"}]}
        for name, doc in docs.items():
            for group, group_checks in checks.items():
                for chk in group_checks:
                    rep = audit_mem(doc, [rule("R-S", group, check=chk, std=True)])
                    with self.subTest(doc=name, group=group, check=chk["type"]):
                        r = rep["rules"][0]
                        self.assertEqual((r["verdict"], r["reasons"]), ("UNKNOWN", ["STANDARD_LOOKUP_NOT_ENABLED"]))
                        self.assertTrue(r["evidence_ids"])
                        for row in rep["results"]:
                            self.assertEqual((row["verdict"], row["reason"]), ("UNKNOWN", "STANDARD_LOOKUP_NOT_ENABLED"))
                            self.assertTrue(row["evidence_ids"])
                        self.assertNotIn(rep["summary"]["overall"], ("HAS_FAIL", "ALL_RULES_PASS"))


class ObjectPrecedence(unittest.TestCase):
    """D5, per object: 1 STANDARD_REQUIRED, 2 null field or missing reference, 3 check."""

    def test_line1_standard_required_beats_everything(self):
        doc = base()
        doc["texts"][0]["height"] = None
        set_cov(doc, "texts", "INCOMPLETE", 5, 2, "TIMEOUT")
        rep = audit_mem(doc, [rule(check=HEIGHT, std=True)])
        self.assertEqual({(r["verdict"], r["reason"]) for r in rep["results"]}, {("UNKNOWN", "STANDARD_LOOKUP_NOT_ENABLED")})

    def test_line2_null_field_is_field_missing(self):
        doc = base()
        doc["texts"][0]["height"] = None
        rep = audit_mem(doc, [rule(check=HEIGHT)])
        row = {r["handle"]: r for r in rep["results"]}["50"]
        self.assertEqual((row["verdict"], row["reason"], row["evidence_ids"], row["actual"]),
                         ("UNKNOWN", "FIELD_MISSING", ["CADEV:F01:50:height"], None))

    def test_line2_null_beats_a_violation_elsewhere_in_the_same_object(self):
        doc = base()
        doc["dimensions"][0]["measured_value"] = None
        doc["dimensions"][0]["display_value"] = 5.0
        rep = audit_mem(doc, [rule("R-D", "dimensions", check={"type": "equals_field", "field_a": "measured_value", "field_b": "display_value"})])
        self.assertEqual((rep["results"][0]["verdict"], rep["results"][0]["reason"]), ("UNKNOWN", "FIELD_MISSING"))

    def test_line2_missing_attribute_with_incomplete_attributes_is_coverage_incomplete(self):
        doc = base()
        doc["attributes"] = [doc["attributes"][1]]
        set_cov(doc, "attributes", "INCOMPLETE", 2, 1, "TIMEOUT")
        rep = audit_mem(doc, [rule("R-A", "block_refs", {"block_name": "TITLEBLOCK"}, {"type": "required_field", "attribute_tag": "DRAWING_NO"})])
        row = rep["results"][0]
        self.assertEqual((row["verdict"], row["reason"]), ("UNKNOWN", "COVERAGE_INCOMPLETE"))
        self.assertIn("CADEV:F01:FILE:coverage.attributes.status", row["evidence_ids"])

    def test_line3_missing_attribute_with_complete_attributes_is_a_fail(self):
        doc = base()
        doc["attributes"] = [doc["attributes"][1]]
        set_cov(doc, "attributes", "COMPLETE", 1, 1, None)
        rep = audit_mem(doc, [rule("R-A", "block_refs", {"block_name": "TITLEBLOCK"}, {"type": "required_field", "attribute_tag": "DRAWING_NO"})])
        self.assertEqual((rep["results"][0]["verdict"], rep["results"][0]["evidence_ids"]), ("FAIL", ["CADEV:F01:31:block_name"]))

    def test_attribute_value_null_empty_and_blank(self):
        chk = {"type": "required_field", "attribute_tag": "DRAWING_NO"}
        for value, want in ((None, ("UNKNOWN", "FIELD_MISSING")), ("", ("FAIL", None)), ("   ", ("FAIL", None)), ("FX-9", ("PASS", None))):
            doc = base()
            doc["attributes"][0]["value"] = value
            rep = audit_mem(doc, [rule("R-A", "block_refs", {"block_name": "TITLEBLOCK"}, chk)])
            with self.subTest(value=value):
                row = rep["results"][0]
                self.assertEqual((row["verdict"], row["reason"]), want)
                self.assertEqual(row["evidence_ids"], ["CADEV:F01:40:value"])

    def test_line2_missing_parent_with_incomplete_block_refs(self):
        doc = base()
        doc["attributes"][0]["parent_handle"] = "FF"
        set_cov(doc, "block_refs", "INCOMPLETE", 5, 2, "READ_ERROR")
        rep = audit_mem(doc, [rule("R-P", "attributes", {"layer": "A-ANNO-TEXT"}, {"type": "required_field", "field": "value"})])
        rows = {r["handle"]: r for r in rep["results"]}
        self.assertEqual((rows["40"]["verdict"], rows["40"]["reason"]), ("UNKNOWN", "COVERAGE_INCOMPLETE"))
        self.assertEqual(rows["40"]["evidence_ids"], ["CADEV:F01:40:parent_handle", "CADEV:F01:FILE:coverage.block_refs.status"])
        self.assertEqual(rows["41"]["verdict"], "PASS")           # its parent exists and sits on A-ANNO-TEXT
        r = rep["rules"][0]
        self.assertEqual((r["verdict"], r["reasons"]), ("UNKNOWN", ["COVERAGE_INCOMPLETE"]))
        self.assertEqual(r["reads_groups"], ["layers", "block_refs", "attributes"])

    def test_rule_that_does_not_need_the_parent_still_evaluates_the_attribute(self):
        doc = base()
        doc["attributes"][0]["parent_handle"] = "FF"
        doc["attributes"][0]["value"] = ""
        set_cov(doc, "block_refs", "INCOMPLETE", 5, 2, "READ_ERROR")
        rep = audit_mem(doc, [rule("R-P", "attributes", {"tag": "DRAWING_NO"}, {"type": "required_field", "field": "value"})])
        self.assertEqual((rep["results"][0]["verdict"], rep["rules"][0]["reads_groups"]), ("FAIL", ["attributes"]))

    def test_line3_pass_and_fail(self):
        doc = base()
        rep = audit_mem(doc, [rule(check=HEIGHT)])
        self.assertEqual({r["verdict"] for r in rep["results"]}, {"PASS"})
        doc["texts"][0]["height"] = 9.0
        rep = audit_mem(doc, [rule(check=HEIGHT)])
        self.assertEqual({r["handle"]: r["verdict"] for r in rep["results"]}, {"50": "FAIL", "51": "PASS"})


class RulePrecedence(unittest.TestCase):
    """D5, per rule: 1 STANDARD_REQUIRED, 2 FAIL, 3 non-COMPLETE group, 4 no objects, 5 UNKNOWN object, 6 PASS."""

    def one(self, doc, r):
        return audit_mem(doc, [r])["rules"][0]

    def test_line1_standard_required_even_with_no_objects_and_incomplete_coverage(self):
        doc = base()
        doc["texts"] = []
        set_cov(doc, "texts", "NOT_EXTRACTED", None, 0, "NOT_REQUESTED")
        r = self.one(doc, rule(check=HEIGHT, std=True))
        self.assertEqual((r["verdict"], r["reasons"]), ("UNKNOWN", ["STANDARD_LOOKUP_NOT_ENABLED"]))
        self.assertEqual(r["evidence_ids"], ["CADEV:F01:FILE:coverage.texts.status"])

    def test_line2_fail_with_complete_coverage(self):
        doc = base()
        doc["texts"][0]["height"] = 9.0
        r = self.one(doc, rule(check=HEIGHT))
        self.assertEqual((r["verdict"], r["reasons"], r["coverage_complete"]), ("FAIL", [], True))
        self.assertEqual(r["evidence_ids"], ["CADEV:F01:50:height"])

    def test_line2_fail_is_kept_when_coverage_is_incomplete(self):
        doc = base()
        doc["texts"][0]["height"] = 9.0
        set_cov(doc, "texts", "INCOMPLETE", 5, 2, "PARTIAL_ENUMERATION")
        r = self.one(doc, rule(check=HEIGHT))
        self.assertEqual((r["verdict"], r["coverage_complete"]), ("FAIL", False))
        # the same when the incomplete group is only read through the selector
        doc = base()
        doc["texts"][0]["height"] = 9.0
        set_cov(doc, "layers", "INCOMPLETE", 9, 4, "READ_ERROR")
        r = self.one(doc, rule(selector={"layer": "A-ANNO-TEXT"}, check=HEIGHT))
        self.assertEqual((r["verdict"], r["coverage_complete"], r["reads_groups"]), ("FAIL", False, ["layers", "texts"]))

    def test_line2_fail_beats_unknown_objects(self):
        doc = base()
        doc["texts"][0]["height"] = 9.0
        doc["texts"][1]["height"] = None
        r = self.one(doc, rule(check=HEIGHT))
        self.assertEqual(r["verdict"], "FAIL")

    def test_line3_no_fail_and_incomplete_group_is_unknown_never_pass(self):
        for status, expected, enumerated, reason in (("INCOMPLETE", 5, 2, "TIMEOUT"), ("INCOMPLETE", None, 2, "XREF_DEPENDENT")):
            doc = base()
            set_cov(doc, "texts", status, expected, enumerated, reason)
            r = self.one(doc, rule(check=HEIGHT))          # both texts pass
            with self.subTest(expected=expected):
                self.assertEqual((r["verdict"], r["reasons"], r["coverage_complete"]), ("UNKNOWN", ["COVERAGE_INCOMPLETE"], False))
                self.assertEqual(r["evidence_ids"], ["CADEV:F01:FILE:coverage.texts.status"])

    def test_line3_selector_reads_another_group_that_is_not_complete(self):
        doc = base()
        set_cov(doc, "layers", "INCOMPLETE", 9, 4, "READ_ERROR")
        r = self.one(doc, rule(selector={"layer": "A-ANNO-TEXT"}, check=HEIGHT))   # texts COMPLETE, layers not
        self.assertEqual((r["verdict"], r["reasons"], r["reads_groups"]), ("UNKNOWN", ["COVERAGE_INCOMPLETE"], ["layers", "texts"]))
        self.assertEqual(r["evidence_ids"], ["CADEV:F01:FILE:coverage.layers.status"])
        # same rule without the layer selector reads only texts and passes
        self.assertEqual(self.one(doc, rule(check=HEIGHT))["verdict"], "PASS")

    def test_line3_check_reads_another_group_that_is_not_complete(self):
        doc = base()
        set_cov(doc, "attributes", "NOT_EXTRACTED", None, 0, "NOT_REQUESTED")
        doc["attributes"] = []
        r = self.one(doc, rule("R-A", "block_refs", {"block_name": "TITLEBLOCK"}, {"type": "required_field", "attribute_tag": "DRAWING_NO"}))
        self.assertEqual((r["verdict"], r["reasons"], r["reads_groups"]), ("UNKNOWN", ["COVERAGE_INCOMPLETE"], ["block_refs", "attributes"]))

    def test_line3_comes_before_line4(self):
        doc = base()
        doc["texts"] = []
        set_cov(doc, "texts", "NOT_EXTRACTED", None, 0, "NOT_REQUESTED")
        r = self.one(doc, rule(check=HEIGHT))
        self.assertEqual((r["verdict"], r["reasons"], r["objects_in_scope"]), ("UNKNOWN", ["COVERAGE_INCOMPLETE"], 0))

    def test_line4_no_objects_in_scope(self):
        doc = base()
        r = self.one(doc, rule(selector={"layer": "NO-SUCH-LAYER"}, check=HEIGHT))
        self.assertEqual((r["verdict"], r["reasons"], r["objects_in_scope"], r["coverage_complete"]), ("UNKNOWN", ["NO_OBJECTS_IN_SCOPE"], 0, True))
        doc["texts"] = []
        set_cov(doc, "texts", "COMPLETE", 0, 0, None)
        r = self.one(doc, rule(check=HEIGHT))
        self.assertEqual((r["verdict"], r["reasons"]), ("UNKNOWN", ["NO_OBJECTS_IN_SCOPE"]))

    def test_line5_unknown_object_gives_unknown_with_its_reason(self):
        doc = base()
        doc["texts"][0]["height"] = None
        r = self.one(doc, rule(check=HEIGHT))
        self.assertEqual((r["verdict"], r["reasons"], r["coverage_complete"]), ("UNKNOWN", ["FIELD_MISSING"], True))
        self.assertEqual(r["evidence_ids"], ["CADEV:F01:50:height"])

    def test_line6_pass(self):
        r = self.one(base(), rule(check=HEIGHT))
        self.assertEqual((r["verdict"], r["reasons"], r["coverage_complete"], r["counts"]), ("PASS", [], True, {"PASS": 2, "FAIL": 0, "UNKNOWN": 0}))


class WholeReport(unittest.TestCase):
    def test_overall_values(self):
        doc = base()
        ok = rule("R-OK", check=HEIGHT)
        bad = rule("R-BAD", check={"type": "numeric_range", "field": "height", "min": 10})
        unk = rule("R-UNK", check=HEIGHT, std=True)
        self.assertEqual(audit_mem(doc, [ok])["summary"]["overall"], "ALL_RULES_PASS")
        self.assertEqual(audit_mem(doc, [ok, unk])["summary"]["overall"], "HAS_UNKNOWN")
        self.assertEqual(audit_mem(doc, [ok, unk, bad])["summary"]["overall"], "HAS_FAIL")
        self.assertEqual(audit_mem(doc, [bad])["summary"]["overall"], "HAS_FAIL")

    def test_no_field_means_the_drawing_passes(self):
        rep = audit_fixture("cad_read_pass.json", "rules_internal.yaml")
        rule_keys = {"rule_id", "title", "rule_status", "classification", "classification_reason", "standard_hint", "applies_to",
                     "reads_groups", "verdict", "reasons", "coverage_complete", "objects_in_scope", "counts", "evidence_ids"}
        row_keys = {"rule_id", "rule_status", "classification", "handle", "verdict", "reason", "evidence_ids", "actual",
                    "expected", "standard_hint"}
        for x in rep["rules"]:
            self.assertEqual(set(x), rule_keys)
        for x in rep["results"]:
            self.assertEqual(set(x), row_keys)
        self.assertEqual(set(rep), {"schema", "cadaudit_version", "generated_at", "notice", "input", "rules_file", "rules", "results", "summary"})
        self.assertEqual(set(rep["summary"]), {"rules_by_verdict", "results_by_verdict", "rules_by_status", "overall"})
        self.assertIn("không kết luận", rep["notice"])

    def test_report_identity_fields(self):
        rep = audit_fixture("cad_read_pass.json", "rules_internal.yaml")
        self.assertEqual(rep["input"]["file_id"], "F01")
        self.assertEqual(rep["input"]["input_sha256"], __import__("hashlib").sha256(read_bytes(fx("cad_read_pass.json"))).hexdigest())
        self.assertEqual(rep["input"]["dwg_sha256"], read_json(fx("cad_read_pass.json"))["drawing"]["sha256"])
        self.assertEqual(rep["rules_file"]["sha256"], __import__("hashlib").sha256(read_bytes(fx("rules_internal.yaml"))).hexdigest())

    def test_rule_status_label_is_carried(self):
        rep = audit_mem(base(), [rule("R-P", check=HEIGHT, status="PROPOSED"), rule("R-A", check=HEIGHT, status="APPROVED")])
        self.assertEqual({r["rule_id"]: r["rule_status"] for r in rep["rules"]}, {"R-P": "PROPOSED", "R-A": "APPROVED"})
        self.assertEqual({(r["rule_id"], r["rule_status"]) for r in rep["results"]}, {("R-P", "PROPOSED"), ("R-A", "APPROVED")})
        self.assertEqual(rep["summary"]["rules_by_status"], {"FIXTURE": 0, "PROPOSED": 1, "APPROVED": 1})


class CheckSemantics(unittest.TestCase):
    def verdict(self, doc, group, check, selector=None):
        rep = audit_mem(doc, [rule("R-C", group, selector, check)])
        return [r["verdict"] for r in rep["results"]]

    def test_name_pattern_uses_fullmatch_and_length_limit(self):
        doc = base()
        self.assertEqual(self.verdict(doc, "layers", {"type": "name_pattern", "field": "name", "pattern": "A-W"}), ["FAIL", "FAIL", "FAIL", "FAIL"])
        self.assertEqual(self.verdict(doc, "layers", {"type": "name_pattern", "field": "name", "pattern": "A-.*"}), ["PASS"] * 4)
        self.assertEqual(self.verdict(doc, "layers", {"type": "name_pattern", "field": "name", "pattern": "A-.*", "max_length": 6}),
                         ["PASS", "PASS", "FAIL", "FAIL"])

    def test_allowed_values_does_not_confuse_types(self):
        doc = base()
        doc["units"][0]["insunits"] = 1
        self.assertEqual(self.verdict(doc, "units", {"type": "allowed_values", "field": "insunits", "values": [1.0, 4]}), ["PASS"])
        self.assertEqual(self.verdict(doc, "units", {"type": "allowed_values", "field": "insunits", "values": [4]}), ["FAIL"])
        self.assertEqual(self.verdict(doc, "layers", {"type": "allowed_values", "field": "plot", "values": [True]}), ["PASS"] * 4)
        self.assertEqual(self.verdict(doc, "layers", {"type": "allowed_values", "field": "frozen", "values": [True]}), ["FAIL"] * 4)

    def test_numeric_range_bounds_and_tolerance(self):
        doc = base()
        doc["texts"][0]["height"] = 2.45
        base_check = {"type": "numeric_range", "field": "height", "min": 2.5, "max": 3.5}
        self.assertEqual(self.verdict(doc, "texts", base_check), ["FAIL", "PASS"])
        self.assertEqual(self.verdict(doc, "texts", dict(base_check, tolerance=0.1)), ["PASS", "PASS"])
        self.assertEqual(self.verdict(doc, "texts", {"type": "numeric_range", "field": "height", "max": 3.0}), ["PASS", "FAIL"])
        self.assertEqual(self.verdict(doc, "texts", {"type": "numeric_range", "field": "height", "min": 3.5}), ["FAIL", "PASS"])

    def test_required_field_blank_string(self):
        doc = base()
        doc["texts"][0]["value"] = "  "
        doc["texts"][1]["value"] = "x"
        self.assertEqual(self.verdict(doc, "texts", {"type": "required_field", "field": "value"}), ["FAIL", "PASS"])

    def test_equals_field_with_tolerance_and_strings(self):
        doc = base()
        doc["dimensions"][0]["display_value"] = 2400.4
        eq = {"type": "equals_field", "field_a": "measured_value", "field_b": "display_value"}
        self.assertEqual(self.verdict(doc, "dimensions", eq), ["FAIL"])
        self.assertEqual(self.verdict(doc, "dimensions", dict(eq, tolerance=0.5)), ["PASS"])
        self.assertEqual(self.verdict(doc, "texts", {"type": "equals_field", "field_a": "style", "field_b": "text_type"}), ["FAIL", "FAIL"])
        self.assertEqual(self.verdict(doc, "layers", {"type": "equals_field", "field_a": "name", "field_b": "linetype"}), ["FAIL"] * 4)

    def test_xref_states(self):
        doc = base()
        for status, want in (("RESOLVED", "PASS"), ("NOT_FOUND", "FAIL"), ("UNRESOLVED", "FAIL"), (None, "UNKNOWN")):
            doc["xrefs"][0]["path_status"] = status
            with self.subTest(status):
                self.assertEqual(self.verdict(doc, "xrefs", {"type": "xref_resolved"}), [want])

    def test_selector_keys(self):
        doc = base()
        n = lambda sel: len(audit_mem(doc, [rule("R-S", "texts", sel, HEIGHT)])["results"])
        self.assertEqual((n({}), n({"layer": "A-ANNO-TEXT"}), n({"layer": "A-WALL"}), n({"space": "MODEL"}), n({"space": "Layout1"})), (2, 2, 0, 2, 0))
        blocks = audit_mem(doc, [rule("R-B", "blocks", {"name_pattern": "DOOR-.*"}, {"type": "name_pattern", "field": "name", "pattern": ".*"})])
        self.assertEqual([r["handle"] for r in blocks["results"]], ["20"])
        attrs = audit_mem(doc, [rule("R-T", "attributes", {"block_name": "TITLEBLOCK", "tag": "REVISION"}, {"type": "required_field", "field": "value"})])
        self.assertEqual([r["handle"] for r in attrs["results"]], ["41"])
        self.assertEqual(attrs["rules"][0]["reads_groups"], ["block_refs", "attributes"])


class InputAndRuleErrors(unittest.TestCase):
    """Every error stops the run, exits non-zero with a code, and writes nothing."""

    def setUp(self):
        self.w = World()
        self.addCleanup(self.w.cleanup)

    def run_check(self, input_path=None, rules_path=None):
        out = self.w.out()
        code, err = run_cli(*check_args(input_path or self.w.input, rules_path or self.w.rules, out))
        self.assertNotEqual(code, 0)
        self.assertFalse(os.path.lexists(out), "an error must not leave a report")
        self.assertEqual(os.listdir(self.w.outdir), [])
        self.assertEqual(tmp_files_under(self.w.root), [])
        return code, err

    def test_input_fixtures(self):
        table = {"error_bad_schema.json": "INPUT_SCHEMA_INVALID", "error_read_mode_read_write.json": "READ_MODE_NOT_READ_ONLY",
                 "error_duplicate_handle.json": "DUPLICATE_HANDLE", "error_coverage_inconsistent.json": "COVERAGE_INCONSISTENT",
                 "error_dangling_reference.json": "DANGLING_REFERENCE"}
        for name, code in table.items():
            with self.subTest(name):
                got, err = self.run_check(input_path=fx(name))
                self.assertEqual(got, 2)
                self.assertIn(f"ERROR {code}", err)

    def test_rules_fixtures(self):
        table = {"rules_error_unknown_check.yaml": "RULES_SCHEMA_INVALID", "rules_error_hint_not_required.yaml": "RULE_CONFIG_CONTRADICTORY",
                 "rules_error_bad_schema.yaml": "RULES_SCHEMA_INVALID", "rules_error_not_yaml_object.yaml": "RULES_NOT_YAML"}
        for name, code in table.items():
            with self.subTest(name):
                got, err = self.run_check(rules_path=fx(os.path.join("errors", name)))
                self.assertEqual(got, 2)
                self.assertIn(f"ERROR {code}", err)

    def test_unreadable_or_unparsable_input(self):
        got, err = self.run_check(input_path=os.path.join(self.w.indir, "missing.json"))
        self.assertIn("INPUT_UNREADABLE", err)
        for label, data in (("garbage", b"\xff\xfe not json"), ("empty", b""), ("nan", b'{"a": NaN}'),
                            ("dup-key", b'{"schema": 1, "schema": 2}'), ("array", b"[]"), ("scalar", b"3")):
            with open(self.w.input, "wb") as f:
                f.write(data)
            with self.subTest(label):
                got, err = self.run_check()
                self.assertTrue("INPUT_NOT_JSON" in err or "INPUT_SCHEMA_INVALID" in err, err)

    def test_other_schema_violations_of_input(self):
        for label, mutate in (("dwg_modified true", lambda d: d["drawing"].update(dwg_modified=True)),
                              ("missing drawing", lambda d: d.pop("drawing")),
                              ("missing field in object", lambda d: d["texts"][0].pop("font")),
                              ("wrong type", lambda d: d["texts"][0].update(height="2.5")),
                              ("xref absolute path", lambda d: d["xrefs"][0].update(name="C:\\Users\\x\\a.dwg")),
                              ("bad schema id", lambda d: d.update(schema="other")),
                              ("unknown group", lambda d: d.update(polylines=[]))):
            d = base()
            mutate(d)
            with open(self.w.input, "w", encoding="utf-8", newline="\n") as f:
                json.dump(d, f)
            with self.subTest(label):
                got, err = self.run_check()
                self.assertTrue("INPUT_SCHEMA_INVALID" in err or "READ_MODE" in err, err)

    def test_rules_semantic_errors(self):
        good = {"id": "R-X", "title": "t", "status": "FIXTURE", "source": "s", "applies_to": "texts", "selector": {},
                "check": HEIGHT, "standard_required": False}
        def variant(**kw):
            r = copy.deepcopy(good)
            for k, v in kw.items():
                if k == "check":
                    r["check"] = v
                elif k == "selector":
                    r["selector"] = v
                else:
                    r[k] = v
            return r
        cases = {
            "unknown field": (variant(check={"type": "numeric_range", "field": "weight", "min": 1}), "RULE_INVALID"),
            "numeric on text field": (variant(check={"type": "numeric_range", "field": "font", "min": 1}), "RULE_INVALID"),
            "no min or max": (variant(check={"type": "numeric_range", "field": "height"}), "RULE_INVALID"),
            "min above max": (variant(check={"type": "numeric_range", "field": "height", "min": 5, "max": 1}), "RULE_INVALID"),
            "pattern on number": (variant(check={"type": "name_pattern", "field": "height", "pattern": "x"}), "RULE_INVALID"),
            "bad regex": (variant(check={"type": "name_pattern", "field": "font", "pattern": "("}), "RULE_INVALID"),
            "values of wrong type": (variant(check={"type": "allowed_values", "field": "font", "values": [1]}), "RULE_INVALID"),
            "required both": (variant(check={"type": "required_field", "field": "font", "attribute_tag": "X"}), "RULE_INVALID"),
            "required none": (variant(check={"type": "required_field"}), "RULE_INVALID"),
            "attribute_tag outside block_refs": (variant(check={"type": "required_field", "attribute_tag": "X"}), "RULE_INVALID"),
            "equals same field": (variant(check={"type": "equals_field", "field_a": "font", "field_b": "font"}), "RULE_INVALID"),
            "equals mixed kinds": (variant(check={"type": "equals_field", "field_a": "font", "field_b": "height"}), "RULE_INVALID"),
            "tolerance on text equals": (variant(check={"type": "equals_field", "field_a": "font", "field_b": "style", "tolerance": 1}), "RULE_INVALID"),
            "xref_resolved on texts": (variant(check={"type": "xref_resolved"}), "RULE_INVALID"),
            "selector key not for group": (variant(selector={"tag": "X"}), "RULE_INVALID"),
            "selector bad regex": (variant(applies_to="layers", selector={"name_pattern": "("}, check={"type": "name_pattern", "field": "name", "pattern": "x"}), "RULE_INVALID"),
            "unknown selector key": (variant(selector={"colour": "red"}), "RULES_SCHEMA_INVALID"),
            "python expression check": (variant(check={"type": "python_expression", "expr": "1"}), "RULES_SCHEMA_INVALID"),
            "bad status": (variant(status="DONE"), "RULES_SCHEMA_INVALID"),
            "hint without requirement": (variant(standard_hint="TCVN-X"), "RULE_CONFIG_CONTRADICTORY"),
            "id with newline": (variant(id="R-X\n"), "RULES_SCHEMA_INVALID"),
        }
        for label, (r, code) in cases.items():
            with self.subTest(label):
                with self.assertRaises(CadAuditError) as cm:
                    audit_mem(base(), [r])
                self.assertEqual(cm.exception.code, code)
        with self.assertRaises(CadAuditError) as cm:
            audit_mem(base(), [good, good])
        self.assertEqual(cm.exception.code, "RULES_DUPLICATE_ID")

    def test_yaml_is_read_with_safe_load_only(self):
        bad = b"schema: tvxd.cadaudit.rules/v1\nrules_version: !!python/object/apply:os.getcwd []\nrules: []\n"
        with self.assertRaises(CadAuditError) as cm:
            run_audit(read_bytes(fx("cad_read_pass.json")), bad)
        self.assertEqual(cm.exception.code, "RULES_NOT_YAML")

    def test_missing_arguments(self):
        for args in ((), ("check",), ("check", "--input", self.w.input), ("explode",)):
            code, _ = run_cli(*args)
            self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
