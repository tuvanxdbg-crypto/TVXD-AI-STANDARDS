"""D2/D7: every evidence ID in every fixture report resolves to exactly one value in the input; reports are
deterministic (byte-identical except the separated time field)."""
import itertools
import os
import re
import shutil
import tempfile
import unittest

import m04_helpers  # noqa: F401
from cadaudit.audit import run_audit
from cadaudit.report import report_bytes
from m04_helpers import World, check_args, fx, read_bytes, read_json, resolve_evidence, run_cli

INPUTS = ("cad_read_pass.json", "cad_read_fail.json", "cad_read_unknown.json")
RULES = ("rules_internal.yaml", "rules_standard.yaml")
TS = "2026-10-12T10:00:00+07:00"


class Traceability(unittest.TestCase):
    def test_every_evidence_id_resolves_to_exactly_one_input_value(self):
        total = 0
        for inp, rules in itertools.product(INPUTS, RULES):
            doc = read_json(fx(inp))
            rep = run_audit(read_bytes(fx(inp)), read_bytes(fx(rules)), TS)
            items = rep["rules"] + rep["results"]
            for item in items:
                if item["verdict"] in ("FAIL", "UNKNOWN"):
                    self.assertTrue(item["evidence_ids"], f"{inp} {rules} {item['rule_id']}: {item['verdict']} without evidence")
                for ev in item["evidence_ids"]:
                    total += 1
                    with self.subTest(inp=inp, rules=rules, rule=item["rule_id"], ev=ev):
                        self.assertRegex(ev, r"^CADEV:F01:([0-9A-F]+|FILE):[A-Za-z0-9_.]+$")
                        self.assertEqual(len(resolve_evidence(doc, ev)), 1)
        self.assertGreater(total, 100)
    def test_absent_tag_fail_carries_the_proof_of_absence(self):
        """R2: 'block reference has no such attribute' is only a FAIL because attributes is COMPLETE; the FAIL must carry
        the evidence of that coverage (status, enumerated, expected), and those IDs must resolve and say what they prove."""
        proof = ["CADEV:F01:FILE:coverage.attributes.status", "CADEV:F01:FILE:coverage.attributes.enumerated",
                 "CADEV:F01:FILE:coverage.attributes.expected"]
        doc = read_json(fx("cad_read_fail.json"))
        rep = run_audit(read_bytes(fx("cad_read_fail.json")), read_bytes(fx("rules_internal.yaml")), TS)
        rows = [r for r in rep["results"] if r["rule_id"] == "R-TITLE-ATTR" and r["verdict"] == "FAIL"]
        self.assertTrue(rows)
        rule = next(x for x in rep["rules"] if x["rule_id"] == "R-TITLE-ATTR")
        for item in rows + [rule]:
            for ev in proof:
                self.assertIn(ev, item["evidence_ids"])
            self.assertTrue(any(ev.endswith(":block_name") for ev in item["evidence_ids"]))   # the parent block reference too
        for row in rows:
            status, enumerated, expected = (resolve_evidence(doc, ev) for ev in proof)
            self.assertEqual((status, enumerated == expected and len(enumerated) == 1), (["COMPLETE"], True))
            self.assertEqual(enumerated, [len(doc["attributes"])])
            tag = "DRAWING_NO"
            self.assertNotIn((row["handle"], tag), {(a["parent_handle"], a["tag"]) for a in doc["attributes"]})   # really absent

    def test_ids_are_deterministic_and_follow_the_documented_form(self):
        rep = run_audit(read_bytes(fx("cad_read_fail.json")), read_bytes(fx("rules_internal.yaml")), TS)
        ids = {ev for x in rep["results"] for ev in x["evidence_ids"]}
        self.assertIn("CADEV:F01:14:name", ids)                       # CADEV:<file_id>:<handle>:<field>
        self.assertIn("CADEV:F01:FILE:units.insunits", ids)           # file-level form
        rep2 = run_audit(read_bytes(fx("cad_read_fail.json")), read_bytes(fx("rules_internal.yaml")), TS)
        self.assertEqual(rep, rep2)

    def test_evidence_values_match_the_reported_actual_value(self):
        for inp, rules in itertools.product(INPUTS, RULES):
            doc = read_json(fx(inp))
            rep = run_audit(read_bytes(fx(inp)), read_bytes(fx(rules)), TS)
            for row in rep["results"]:
                if row["verdict"] in ("PASS", "FAIL") and row["actual"] is not None:
                    values = [v for ev in row["evidence_ids"] for v in resolve_evidence(doc, ev)]
                    with self.subTest(inp=inp, rules=rules, rule=row["rule_id"], handle=row["handle"]):
                        self.assertIn(row["actual"], values)


class Determinism(unittest.TestCase):
    def test_same_input_same_bytes_with_fixed_time(self):
        for inp, rules in itertools.product(INPUTS, RULES):
            a = report_bytes(run_audit(read_bytes(fx(inp)), read_bytes(fx(rules)), TS))
            b = report_bytes(run_audit(read_bytes(fx(inp)), read_bytes(fx(rules)), TS))
            with self.subTest(inp=inp, rules=rules):
                self.assertEqual(a, b)

    def test_two_cli_runs_are_byte_identical_except_generated_at(self):
        for inp, rules in itertools.product(INPUTS, RULES):
            w = World(inp, rules)
            self.addCleanup(w.cleanup)
            first, second = w.out("a.json"), w.out("b.json")
            self.assertEqual(run_cli(*check_args(w.input, w.rules, first))[0], 0)
            self.assertEqual(run_cli(*check_args(w.input, w.rules, second))[0], 0)
            a, b = read_bytes(first), read_bytes(second)
            strip = lambda data: re.sub(rb'"generated_at": "[^"]*"', b'"generated_at": "-"', data)
            with self.subTest(inp=inp, rules=rules):
                self.assertEqual(strip(a), strip(b))
                self.assertEqual(len(re.findall(rb'"generated_at"', a)), 1)

    def test_the_time_field_is_the_only_clock_value(self):
        rep = run_audit(read_bytes(fx("cad_read_pass.json")), read_bytes(fx("rules_internal.yaml")))
        self.assertRegex(rep["generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$")
        fixed = run_audit(read_bytes(fx("cad_read_pass.json")), read_bytes(fx("rules_internal.yaml")), TS)
        rep.pop("generated_at")
        fixed.pop("generated_at")
        self.assertEqual(rep, fixed)

    def test_reordering_nothing_changes_rule_and_object_order(self):
        rep = run_audit(read_bytes(fx("cad_read_fail.json")), read_bytes(fx("rules_internal.yaml")), TS)
        self.assertEqual([r["rule_id"] for r in rep["rules"]],
                         ["R-LAYER-NAME", "R-BLOCK-NAME", "R-TEXT-FONT", "R-TEXT-HEIGHT", "R-TITLE-ATTR",
                          "R-DIM-OVERRIDE", "R-DIM-SCALE", "R-XREF-RESOLVED", "R-UNITS"])


if __name__ == "__main__":
    unittest.main()
