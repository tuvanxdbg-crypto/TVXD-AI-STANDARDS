"""D1 coverage invariants, table driven over status x expected x enumerated x reason x number of array elements.

The oracle below restates the table of docs/M04_CAD_AUDIT_READONLY.md D1 independently of cadaudit/loader.py.
Valid combinations load; every other combination is COVERAGE_INCONSISTENT.
"""
import copy
import itertools
import json
import unittest

import m04_helpers  # noqa: F401
from cadaudit.errors import CadAuditError
from cadaudit.loader import load_cad_read
from m04_helpers import fx, read_json


def oracle_valid(status, expected, enumerated, reason, n):
    if status == "COMPLETE":
        return expected is not None and enumerated == expected and reason is None and n == enumerated
    if status == "INCOMPLETE":
        return (expected is None or enumerated < expected) and reason is not None and n == enumerated
    if status == "NOT_EXTRACTED":
        return expected is None and enumerated == 0 and reason is not None and n == 0
    raise AssertionError(status)


def load_doc(doc):
    return load_cad_read(json.dumps(doc).encode("utf-8"))


def texts(n):
    base = read_json(fx("cad_read_pass.json"))["texts"][0]
    out = []
    for i in range(n):
        t = copy.deepcopy(base)
        t["handle"] = f"A{i:02X}"
        out.append(t)
    return out


class CoverageTable(unittest.TestCase):
    def doc(self, status, expected, enumerated, reason, n, group="texts"):
        d = read_json(fx("cad_read_pass.json"))
        d[group] = texts(n) if group == "texts" else d[group][:n]
        d["coverage"][group] = {"status": status, "expected": expected, "enumerated": enumerated, "reason": reason}
        return d

    def test_every_combination(self):
        valid = invalid = 0
        combos = itertools.product(("COMPLETE", "INCOMPLETE", "NOT_EXTRACTED"), (None, 0, 3, 5), (0, 2, 3, 4, 5),
                                   (None, "READ_ERROR"), (0, 2, 3, 4, 5))
        for status, expected, enumerated, reason, n in combos:
            want = oracle_valid(status, expected, enumerated, reason, n)
            d = self.doc(status, expected, enumerated, reason, n)
            label = f"{status} expected={expected} enumerated={enumerated} reason={reason} n={n}"
            if want:
                valid += 1
                with self.subTest(label):
                    self.assertEqual(len(load_doc(d).groups["texts"]), n)
            else:
                invalid += 1
                with self.subTest(label):
                    with self.assertRaises(CadAuditError) as cm:
                        load_doc(d)
                    self.assertEqual(cm.exception.code, "COVERAGE_INCONSISTENT")
        self.assertEqual(valid, 15)   # 3 COMPLETE + 11 INCOMPLETE + 1 NOT_EXTRACTED
        self.assertGreater(invalid, 400)

    def test_every_reason_code_is_accepted(self):
        for reason in ("XREF_DEPENDENT", "READ_ERROR", "TIMEOUT", "PARTIAL_ENUMERATION", "NOT_REQUESTED"):
            with self.subTest(reason):
                load_doc(self.doc("INCOMPLETE", 5, 2, reason, 2))

    def test_unknown_reason_is_a_schema_error(self):
        d = self.doc("INCOMPLETE", 5, 2, "BECAUSE", 2)
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "INPUT_SCHEMA_INVALID")

    def test_named_cases(self):
        cases = {
            "COMPLETE with enumerated != expected": self.doc("COMPLETE", 3, 2, None, 2),
            "COMPLETE with missing array elements": self.doc("COMPLETE", 3, 3, None, 2),
            "COMPLETE with extra array elements": self.doc("COMPLETE", 2, 2, None, 3),
            "COMPLETE with a reason": self.doc("COMPLETE", 2, 2, "TIMEOUT", 2),
            "COMPLETE with expected null": self.doc("COMPLETE", None, 2, None, 2),
            "INCOMPLETE without a reason": self.doc("INCOMPLETE", 5, 2, None, 2),
            "INCOMPLETE with enumerated == expected": self.doc("INCOMPLETE", 2, 2, "TIMEOUT", 2),
            "INCOMPLETE with enumerated > expected": self.doc("INCOMPLETE", 2, 3, "TIMEOUT", 3),
            "NOT_EXTRACTED with elements": self.doc("NOT_EXTRACTED", None, 0, "NOT_REQUESTED", 1),
            "NOT_EXTRACTED with expected": self.doc("NOT_EXTRACTED", 4, 0, "NOT_REQUESTED", 0),
            "NOT_EXTRACTED with enumerated": self.doc("NOT_EXTRACTED", None, 2, "NOT_REQUESTED", 2),
        }
        for name, d in cases.items():
            with self.subTest(name):
                with self.assertRaises(CadAuditError) as cm:
                    load_doc(d)
                self.assertEqual(cm.exception.code, "COVERAGE_INCONSISTENT")

    def test_coverage_entry_missing_for_a_group(self):
        for group in ("layers", "blocks", "block_refs", "attributes", "texts", "dimensions", "xrefs", "units"):
            d = read_json(fx("cad_read_pass.json"))
            del d["coverage"][group]
            with self.subTest(group):
                with self.assertRaises(CadAuditError) as cm:
                    load_doc(d)
                self.assertEqual(cm.exception.code, "COVERAGE_INCONSISTENT")

    def test_array_with_elements_but_no_coverage_entry(self):
        d = read_json(fx("cad_read_pass.json"))
        d["coverage"].pop("texts")
        self.assertTrue(d["texts"])
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "COVERAGE_INCONSISTENT")

    def test_coverage_says_elements_exist_but_array_missing(self):
        d = read_json(fx("cad_read_pass.json"))
        del d["texts"]
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "COVERAGE_INCONSISTENT")

    def test_not_extracted_group_may_omit_its_array(self):
        d = read_json(fx("cad_read_pass.json"))
        del d["dimensions"]
        d["coverage"]["dimensions"] = {"status": "NOT_EXTRACTED", "expected": None, "enumerated": 0, "reason": "NOT_REQUESTED"}
        self.assertEqual(load_doc(d).groups["dimensions"], [])

    def test_units_group_uses_the_same_table(self):
        for n, status, expected, enumerated, reason in itertools.product(
                (0, 1), ("COMPLETE", "INCOMPLETE", "NOT_EXTRACTED"), (None, 0, 1), (0, 1), (None, "READ_ERROR")):
            d = read_json(fx("cad_read_pass.json"))
            d["units"] = d["units"][:n]
            d["coverage"]["units"] = {"status": status, "expected": expected, "enumerated": enumerated, "reason": reason}
            want = oracle_valid(status, expected, enumerated, reason, n)
            with self.subTest(n=n, status=status, expected=expected, enumerated=enumerated, reason=reason):
                if want:
                    load_doc(d)
                else:
                    with self.assertRaises(CadAuditError) as cm:
                        load_doc(d)
                    self.assertEqual(cm.exception.code, "COVERAGE_INCONSISTENT")

    def test_units_with_two_entries_is_a_schema_error(self):
        d = read_json(fx("cad_read_pass.json"))
        d["units"] = d["units"] * 2
        d["coverage"]["units"] = {"status": "COMPLETE", "expected": 2, "enumerated": 2, "reason": None}
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "INPUT_SCHEMA_INVALID")


class CrossReferences(unittest.TestCase):
    def test_dangling_parent_with_complete_block_refs_is_an_error(self):
        d = read_json(fx("cad_read_pass.json"))
        d["attributes"][0]["parent_handle"] = "FF"
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "DANGLING_REFERENCE")

    def test_dangling_parent_is_accepted_when_block_refs_not_complete(self):
        for status, expected, reason in (("INCOMPLETE", None, "TIMEOUT"), ("INCOMPLETE", 5, "READ_ERROR")):
            d = read_json(fx("cad_read_pass.json"))
            d["attributes"][0]["parent_handle"] = "FF"
            d["coverage"]["block_refs"] = {"status": status, "expected": expected, "enumerated": 2, "reason": reason}
            with self.subTest(expected=expected):
                load_doc(d)

    def test_dangling_parent_with_block_refs_not_extracted(self):
        d = read_json(fx("cad_read_pass.json"))
        d["block_refs"] = []
        d["coverage"]["block_refs"] = {"status": "NOT_EXTRACTED", "expected": None, "enumerated": 0, "reason": "NOT_REQUESTED"}
        load_doc(d)

    def test_duplicate_handle_within_and_across_groups(self):
        d = read_json(fx("cad_read_pass.json"))
        d["layers"][1]["handle"] = d["layers"][0]["handle"]
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "DUPLICATE_HANDLE")
        d = read_json(fx("cad_read_pass.json"))
        d["xrefs"][0]["handle"] = d["texts"][0]["handle"]
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "DUPLICATE_HANDLE")

    def test_lower_case_handle_is_rejected(self):
        d = read_json(fx("cad_read_pass.json"))
        d["layers"][0]["handle"] = "2a"
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "INPUT_SCHEMA_INVALID")

    def test_same_attribute_tag_twice_on_one_block_reference_is_rejected(self):
        d = read_json(fx("cad_read_pass.json"))
        d["attributes"][1]["tag"] = d["attributes"][0]["tag"]
        with self.assertRaises(CadAuditError) as cm:
            load_doc(d)
        self.assertEqual(cm.exception.code, "DUPLICATE_ATTRIBUTE_TAG")


if __name__ == "__main__":
    unittest.main()
