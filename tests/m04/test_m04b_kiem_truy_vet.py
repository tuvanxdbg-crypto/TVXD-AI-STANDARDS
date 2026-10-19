"""M04-B G7: tests của scripts/m04b/kiem_truy_vet.py (docs/M04_B_PLAN.md mục 5.1). Chỉ dữ liệu giả (fixture), offline.

Mỗi ca KHONG_DAT sửa MỘT chỗ trên báo cáo hoặc đầu vào, tính lại sha256 cho khớp (trừ ca sai hash) và kiểm đúng mã
lý do. Các tệp tạm nằm trong thư mục tạm và bị xóa sau mỗi ca.
"""
import ast
import contextlib
import copy
import hashlib
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import m04_helpers  # noqa: F401  (đặt thư mục gốc repo lên sys.path)
from cadaudit.audit import run_audit
from cadaudit.report import report_bytes
from m04_helpers import REPO, check_args, fx, read_bytes, read_json, resolve_evidence, run_cli

SCRIPT_DIR = os.path.join(REPO, "scripts", "m04b")
SCRIPT = os.path.join(SCRIPT_DIR, "kiem_truy_vet.py")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import kiem_truy_vet as kv  # noqa: E402

TS = "2026-10-19T10:00:00+07:00"
INPUTS = ("cad_read_pass.json", "cad_read_fail.json", "cad_read_unknown.json")
RULES = ("rules_internal.yaml", "rules_standard.yaml")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dumps(doc) -> bytes:
    return json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8")


def invoke(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = kv.main([str(a) for a in args])
    return code, out.getvalue(), err.getvalue()


class Result:
    def __init__(self, code, stdout, stderr, out, out_text, run_dir):
        self.code, self.stdout, self.stderr, self.out, self.text, self.dir = code, stdout, stderr, out, out_text, run_dir

    @property
    def reasons(self):
        return self.out["ly_do_khong_dat"]


class Case:
    """Một bộ ba (CAD_READ, quy tắc, báo cáo do cadaudit tạo) trong thư mục tạm, chạy được nhiều lần với sửa đổi."""

    def __init__(self, tc: unittest.TestCase, cad_doc: dict, rules_bytes: bytes):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="m04b-"))
        tc.addCleanup(shutil.rmtree, self.root, True)
        self.cad, self.rules_bytes, self.runs = cad_doc, rules_bytes, 0
        self.report = run_audit(dumps(cad_doc), rules_bytes, TS)

    @classmethod
    def fixture(cls, tc, inp="cad_read_pass.json", rules="rules_internal.yaml"):
        return cls(tc, read_json(fx(inp)), read_bytes(fx(rules)))

    def run(self, mut_report=None, mut_cad=None, rules_bytes=None, pin=None, fix_links=True, raw=None, extra=()):
        self.runs += 1
        d = os.path.join(self.root, f"run{self.runs}")
        os.mkdir(d)
        cad = copy.deepcopy(self.cad)
        if mut_cad:
            mut_cad(cad)
        cad_bytes = dumps(cad)
        rules = self.rules_bytes if rules_bytes is None else rules_bytes
        report = copy.deepcopy(self.report)
        if fix_links:
            report["input"]["input_sha256"] = sha(cad_bytes)
            report["input"]["dwg_sha256"] = cad["drawing"]["sha256"]
            report["rules_file"]["sha256"] = sha(rules)
        if mut_report:
            mut_report(report)
        files = {"cad_read": cad_bytes, "quy_tac": rules, "bao_cao": dumps(report)}
        files.update(raw or {})
        paths = {"cad_read": os.path.join(d, "cad_read.json"), "quy_tac": os.path.join(d, "rules.yaml"),
                 "bao_cao": os.path.join(d, "report.json")}
        for k, p in paths.items():
            with open(p, "wb") as f:
                f.write(files[k])
        pins = {k: sha(files[k]) for k in files}
        pins.update(pin or {})
        out_path = os.path.join(d, "out.json")
        code, stdout, stderr = invoke(["--cad-read", paths["cad_read"], "--rules", paths["quy_tac"],
                                       "--report", paths["bao_cao"], "--sha256-cad-read", pins["cad_read"],
                                       "--sha256-rules", pins["quy_tac"], "--sha256-report", pins["bao_cao"],
                                       "--out", out_path, *extra])
        text = out = None
        if os.path.exists(out_path):
            text = read_bytes(out_path).decode("utf-8")
            out = json.loads(text)
        return Result(code, stdout, stderr, out, text, d)


def rule_entry(report, rule_id):
    return next(r for r in report["rules"] if r["rule_id"] == rule_id)


def result_row(report, rule_id, handle):
    return next(r for r in report["results"] if r["rule_id"] == rule_id and r["handle"] == handle)


def resync(report):
    """Làm báo cáo tự nhất quán sau khi sửa dòng (dữ liệu COMPLETE, quy tắc INTERNAL_ONLY): tính lại counts,
    objects_in_scope, verdict, reasons, evidence cấp quy tắc và phần summary từ danh sách dòng."""
    rows = {}
    for r in report["results"]:
        rows.setdefault(r["rule_id"], []).append(r)
    for rule in report["rules"]:
        mine = rows.get(rule["rule_id"], [])
        counts = {v: sum(1 for r in mine if r["verdict"] == v) for v in ("PASS", "FAIL", "UNKNOWN")}
        rule["counts"], rule["objects_in_scope"] = counts, len(mine)
        pick = lambda v: list(dict.fromkeys(i for r in mine if r["verdict"] == v for i in r["evidence_ids"]))  # noqa: E731
        if counts["FAIL"]:
            rule.update(verdict="FAIL", reasons=[], evidence_ids=pick("FAIL"))
        elif not mine:
            rule.update(verdict="UNKNOWN", reasons=["NO_OBJECTS_IN_SCOPE"],
                        evidence_ids=[f"CADEV:F01:FILE:coverage.{rule['applies_to']}.status"])
        elif counts["UNKNOWN"]:
            found = {r["reason"] for r in mine if r["verdict"] == "UNKNOWN"}
            rule.update(verdict="UNKNOWN", evidence_ids=pick("UNKNOWN"),
                        reasons=[x for x in ("COVERAGE_INCOMPLETE", "FIELD_MISSING", "NO_OBJECTS_IN_SCOPE") if x in found])
        else:
            rule.update(verdict="PASS", reasons=[], evidence_ids=[])
    sm = report["summary"]
    sm["rules_by_verdict"] = {v: sum(1 for x in report["rules"] if x["verdict"] == v) for v in ("PASS", "FAIL", "UNKNOWN")}
    sm["results_by_verdict"] = {v: sum(1 for x in report["results"] if x["verdict"] == v) for v in ("PASS", "FAIL", "UNKNOWN")}
    sm["overall"] = "HAS_FAIL" if sm["rules_by_verdict"]["FAIL"] else "HAS_UNKNOWN" if sm["rules_by_verdict"]["UNKNOWN"] else "ALL_RULES_PASS"
    sm.pop("overall_note", None)
    if sm["overall"] == "ALL_RULES_PASS" and not sm["all_rules_approved"]:
        sm["overall_note"] = "RULES_NOT_APPROVED"


def flip(rule_id, handle, verdict):
    def mut(report):
        result_row(report, rule_id, handle)["verdict"] = verdict
        resync(report)
    return mut


def drop(rule_id, handle):
    def mut(report):
        report["results"].remove(result_row(report, rule_id, handle))
        resync(report)
    return mut


class BaseTest(unittest.TestCase):
    def assertDat(self, res, msg=""):
        self.assertEqual((res.code, res.out["ket_luan"], res.reasons), (0, "DAT", []), msg)

    def assertKhongDat(self, res, reasons, exact=True):
        self.assertEqual(res.code, 1, res.stderr)
        self.assertEqual(res.out["ket_luan"], "KHONG_DAT")
        if exact:
            self.assertEqual(res.reasons, list(reasons))
        else:
            for r in reasons:
                self.assertIn(r, res.reasons)


# ---------------------------------------------------------------------------------------------------- DAT
class Dat(BaseTest):
    def test_every_fixture_pair_is_dat_with_zero_mismatch(self):
        kinds = set()
        for inp, rules in itertools.product(INPUTS, RULES):
            with self.subTest(inp=inp, rules=rules):
                res = Case.fixture(self, inp, rules).run()
                self.assertDat(res)
                o = res.out
                self.assertEqual(o["buoc_da_chay"], ["1", "2", "3", "4", "5", "6", "7"])
                self.assertTrue(all(v["khop"] for v in o["sha256"].values()))
                self.assertTrue(o["buoc2_schema"]["bao_cao"]["hop_le"] and o["buoc2_schema"]["cad_read"]["hop_le"])
                self.assertTrue(all(o["lien_ket_bao_cao"].values()))
                c3 = o["buoc3_evidence_id"]
                self.assertEqual(c3["tong"], c3["giai_dung_mot"])
                self.assertEqual(c3["tong"], c3["tong_cap_quy_tac"] + c3["tong_cap_dong"])
                self.assertEqual((c3["khong_giai_duoc"], c3["nhieu_gia_tri"], c3["sai_dang"], c3["sai_file_id"]), (0, 0, 0, 0))
                c4 = o["buoc4_actual"]
                self.assertEqual((c4["actual_lech"], c4["dong_da_kiem"] - c4["actual_khop"]), (0, 0))
                self.assertEqual(c4["dong_da_kiem"], c4["so_dong"])
                self.assertEqual(sum(c4["theo_loai"].values()), c4["so_dong"])
                kinds |= set(c4["theo_loai"])
                self.assertEqual(o["buoc7_thieu_evidence"], {"quy_tac_thieu_evidence": 0, "dong_thieu_evidence": 0})
                self.assertTrue(o["tong_hop_khop"])
                for rule in o["buoc5_6_quy_tac"]:
                    self.assertEqual(rule["so_muc_lech"], 0, rule["rule_id"])
                    self.assertTrue(all(rule[k] for k in ("counts_khop", "objects_in_scope_khop", "coverage_complete_khop",
                                                          "verdict_khop", "reasons_khop", "meta_khop")))
        self.assertEqual(kinds, {"truong_kiem", "standard_required", "attribute_tag", "attribute_tag_vang"})

    def test_the_real_cli_and_report_writer_output_is_dat(self):
        """Đường thật: `cadaudit check` ghi báo cáo bằng bộ ghi của nó, rồi script kiểm đúng tệp đó."""
        w = m04_helpers.World("cad_read_unknown.json", "rules_internal.yaml")
        self.addCleanup(w.cleanup)
        self.assertEqual(run_cli(*check_args(w.input, w.rules, w.out("report.json")))[0], 0)
        out = w.out("kiem-truy-vet.json")
        code, stdout, _ = invoke(["--cad-read", w.input, "--rules", w.rules, "--report", w.out("report.json"),
                                  "--sha256-cad-read", sha(read_bytes(w.input)), "--sha256-rules", sha(read_bytes(w.rules)),
                                  "--sha256-report", sha(read_bytes(w.out("report.json"))), "--out", out])
        self.assertEqual((code, stdout.strip()), (0, "kiem_truy_vet: ket_luan=DAT"))
        self.assertEqual(json.loads(read_bytes(out))["ket_luan"], "DAT")

    def test_null_actual_is_right_when_the_source_value_is_null(self):
        case = Case.fixture(self, "cad_read_unknown.json")
        row = result_row(case.report, "R-TEXT-FONT", "50")
        self.assertEqual((row["verdict"], row["reason"], row["actual"]), ("UNKNOWN", "FIELD_MISSING", None))
        self.assertIsNone(next(t for t in case.cad["texts"] if t["handle"] == "50")["font"])
        self.assertDat(case.run())

    def test_attribute_with_a_missing_parent_is_traced(self):
        """Dòng `cha_thieu` (attributes có parent không có trong block_refs vì block_refs chưa COMPLETE)."""
        cad = read_json(fx("cad_read_pass.json"))
        cad["attributes"][0]["parent_handle"] = "FF"
        cad["coverage"]["block_refs"] = {"status": "INCOMPLETE", "expected": None, "enumerated": 2, "reason": "READ_ERROR"}
        rules = (b"schema: tvxd.cadaudit.rules/v1\nrules_version: x.1\nrules:\n"
                 b"  - {id: R-P, title: t, status: FIXTURE, source: s, applies_to: attributes,\n"
                 b"     selector: {layer: A-ANNO-TEXT}, check: {type: required_field, field: value}, standard_required: false}\n")
        case = Case(self, cad, rules)
        self.assertEqual([(r["verdict"], r["reason"]) for r in case.report["results"]],
                         [("UNKNOWN", "COVERAGE_INCOMPLETE"), ("PASS", None)])
        res = case.run()
        self.assertDat(res)
        self.assertEqual(res.out["buoc4_actual"]["theo_loai"], {"cha_thieu": 1, "truong_kiem": 1})

    def test_coverage_incomplete_claimed_for_a_parent_that_is_not_missing(self):
        """Dòng nói cha thiếu (COVERAGE_INCOMPLETE) nhưng block_refs COMPLETE, hoặc cha có trong dữ liệu: không hợp lệ."""
        rules = (b"schema: tvxd.cadaudit.rules/v1\nrules_version: x.1\nrules:\n"
                 b"  - {id: R-P, title: t, status: FIXTURE, source: s, applies_to: attributes,\n"
                 b"     selector: {layer: A-ANNO-TEXT}, check: {type: required_field, field: value}, standard_required: false}\n")

        def claim(report):
            row = report["results"][0]
            row.update(verdict="UNKNOWN", reason="COVERAGE_INCOMPLETE", actual=None,
                       evidence_ids=[f"CADEV:F01:{row['handle']}:parent_handle", "CADEV:F01:FILE:coverage.block_refs.status"])
        cad = read_json(fx("cad_read_pass.json"))
        self.assertKhongDat(Case(self, cad, rules).run(mut_report=claim), ["DONG_LY_DO_LECH"], exact=False)   # block_refs COMPLETE
        cad["coverage"]["block_refs"] = {"status": "INCOMPLETE", "expected": None, "enumerated": 2, "reason": "READ_ERROR"}
        self.assertKhongDat(Case(self, cad, rules).run(mut_report=claim), ["DONG_LY_DO_LECH"], exact=False)   # cha 31 có trong block_refs

    def test_the_dimension_range_without_source_is_standard_required(self):
        """Nâng lên STANDARD_REQUIRED (D4) được tính lại độc lập: meta_khop và dòng standard_required."""
        res = Case.fixture(self, "cad_read_pass.json", "rules_standard.yaml").run()
        self.assertDat(res)
        rule = next(r for r in res.out["buoc5_6_quy_tac"] if r["rule_id"] == "R-DIM-RANGE-NOSRC")
        self.assertEqual((rule["verdict"], rule["reasons"], rule["meta_khop"]), ("UNKNOWN", ["STANDARD_LOOKUP_NOT_ENABLED"], True))


# ---------------------------------------------------------------------------------------------------- dạng CHC
def chc_like_cad(layer_names, xref_status, layers_status="INCOMPLETE"):
    """CAD_READ giả giống dạng bộ xuất CHC: layers chỉ có handle/space/name (trường khác null), coverage layers
    INCOMPLETE với expected null, nhóm không trích xuất là NOT_EXTRACTED, xrefs có path_status RESOLVED hoặc null."""
    layers = [{"handle": f"A{i}", "space": "MODEL", "name": n, "color": None, "linetype": None, "lineweight": None,
               "plot": None, "frozen": None, "off": None, "locked": None} for i, n in enumerate(layer_names, 1)]
    xrefs = [{"handle": f"B{i}", "space": "MODEL", "name": f"FAKE-XREF-{i}", "path_status": s}
             for i, s in enumerate(xref_status, 1)]
    not_extracted = {"status": "NOT_EXTRACTED", "expected": None, "enumerated": 0, "reason": "NOT_REQUESTED"}
    cov = {g: dict(not_extracted) for g in ("blocks", "block_refs", "attributes", "texts", "dimensions", "units")}
    if layers_status == "INCOMPLETE":
        cov["layers"] = {"status": "INCOMPLETE", "expected": None, "enumerated": len(layers), "reason": "PARTIAL_ENUMERATION"}
    else:
        cov["layers"] = {"status": "COMPLETE", "expected": len(layers), "enumerated": len(layers), "reason": None}
    cov["xrefs"] = {"status": "COMPLETE", "expected": len(xrefs), "enumerated": len(xrefs), "reason": None}
    return {"schema": "tvxd.cadaudit.cad_read/v1", "fixture_note": "FIXTURE ONLY: fake CHC-like extraction, no drawing.",
            "drawing": {"file_id": "C01", "file_name": "FAKE-CHC-LIKE.dwg", "sha256": sha(b"FAKE CHC-LIKE"), "size_bytes": 1,
                        "source_tool": "FAKE-EXPORTER", "source_tool_version": "0", "extracted_at": TS,
                        "read_mode": "READ_ONLY", "dwg_modified": False},
            "coverage": cov, "layers": layers, "xrefs": xrefs}


CHC_RULES = (b"# FIXTURE ONLY: fake rules shaped like an approved layer and xref rule. Not a CHUAN-HOA-CAD rule set.\n"
             b"schema: tvxd.cadaudit.rules/v1\nrules_version: fake-chc-like.1\nrules:\n"
             b"  - id: FAKE-LAYER-LIST\n    title: fake layer list\n    status: APPROVED\n    source: FIXTURE (fake)\n"
             b"    applies_to: layers\n    selector: {}\n"
             b"    check: {type: allowed_values, field: name, values: [FAKE-LAYER-ONE, FAKE-LAYER-TWO, FAKE-LAYER-THREE]}\n"
             b"    standard_required: false\n"
             b"  - id: FAKE-XREF-RESOLVED\n    title: fake xref resolved\n    status: APPROVED\n    source: FIXTURE (fake)\n"
             b"    applies_to: xrefs\n    selector: {}\n    check: {type: xref_resolved}\n    standard_required: false\n")


class ChcLike(BaseTest):
    def test_fail_on_incomplete_layers_and_unknown_xref(self):
        cad = chc_like_cad(["FAKE-LAYER-ONE", "FAKE-LAYER-TWO", "FAKE-LAYER-OTHER"], ["RESOLVED", None])
        case = Case(self, cad, CHC_RULES)
        layer, xref = case.report["rules"]
        self.assertEqual((layer["verdict"], layer["coverage_complete"]), ("FAIL", False))
        self.assertEqual((xref["verdict"], xref["reasons"]), ("UNKNOWN", ["FIELD_MISSING"]))
        res = case.run()
        self.assertDat(res)
        self.assertEqual(res.out["buoc4_actual"]["theo_loai"], {"truong_kiem": 5})

    def test_unknown_on_incomplete_layers_and_pass_on_xref(self):
        cad = chc_like_cad(["FAKE-LAYER-ONE", "FAKE-LAYER-TWO", "FAKE-LAYER-THREE"], ["RESOLVED", "RESOLVED"])
        case = Case(self, cad, CHC_RULES)
        layer, xref = case.report["rules"]
        self.assertEqual((layer["verdict"], layer["reasons"]), ("UNKNOWN", ["COVERAGE_INCOMPLETE"]))
        self.assertEqual(xref["verdict"], "PASS")
        self.assertTrue(case.report["summary"]["all_rules_approved"])
        self.assertDat(case.run())

    def test_layer_check_never_reads_a_null_field_it_does_not_check(self):
        """Các trường layer khác null không làm dòng UNKNOWN: chỉ trường được kiểm (name) tính."""
        case = Case(self, chc_like_cad(["FAKE-LAYER-ONE"], ["RESOLVED"], "COMPLETE"), CHC_RULES)
        self.assertEqual(case.report["rules"][0]["verdict"], "PASS")
        self.assertDat(case.run())


# ---------------------------------------------------------------------------------------------------- KHONG_DAT
class HashAndSchema(BaseTest):
    def test_wrong_pinned_hash_for_each_file_stops_and_still_writes_output(self):
        for key, code in (("cad_read", "SHA256_CAD_READ_SAI"), ("quy_tac", "SHA256_QUY_TAC_SAI"), ("bao_cao", "SHA256_BAO_CAO_SAI")):
            with self.subTest(key):
                res = Case.fixture(self, "cad_read_fail.json").run(pin={key: "0" * 64})
                self.assertKhongDat(res, [code])
                o = res.out
                self.assertEqual(o["buoc_da_chay"], ["1"])
                self.assertFalse(o["sha256"][key]["khop"])
                self.assertEqual(o["sha256"][key]["ghim"], "0" * 64)
                for later in ("buoc2_schema", "buoc3_evidence_id", "buoc4_actual", "buoc5_6_quy_tac", "buoc7_thieu_evidence"):
                    self.assertIsNone(o[later])

    def test_uppercase_pinned_hash_is_accepted_and_all_three_wrong_gives_three_reasons(self):
        case = Case.fixture(self)
        res = case.run(pin={"cad_read": "A" * 64, "quy_tac": "B" * 64, "bao_cao": "C" * 64})
        self.assertKhongDat(res, ["SHA256_CAD_READ_SAI", "SHA256_QUY_TAC_SAI", "SHA256_BAO_CAO_SAI"])
        self.assertEqual(res.out["sha256"]["cad_read"]["ghim"], "a" * 64)   # chuẩn hóa chữ thường

    def test_a_hash_mismatch_with_a_non_json_file_is_still_khong_dat_not_an_input_error(self):
        res = Case.fixture(self).run(raw={"bao_cao": b"not json"}, pin={"bao_cao": "1" * 64})
        self.assertKhongDat(res, ["SHA256_BAO_CAO_SAI"])

    def test_report_that_breaks_its_schema(self):
        mutations = {"notice": lambda r: r.update(notice="x"), "missing key": lambda r: r.pop("summary"),
                     "extra key": lambda r: r.update(extra=1), "bad verdict": lambda r: r["rules"][0].update(verdict="OK"),
                     "bad counts": lambda r: r["rules"][0]["counts"].pop("FAIL")}
        for name, mut in mutations.items():
            with self.subTest(name):
                res = Case.fixture(self).run(mut_report=mut)
                self.assertKhongDat(res, ["BAO_CAO_SAI_SCHEMA"])
                self.assertFalse(res.out["buoc2_schema"]["bao_cao"]["hop_le"])
                self.assertGreater(res.out["buoc2_schema"]["bao_cao"]["so_loi"], 0)
                self.assertIsNone(res.out["buoc3_evidence_id"])

    def test_cad_read_that_breaks_its_schema(self):
        res = Case.fixture(self).run(mut_cad=lambda c: c["drawing"].update(read_mode="READ_WRITE"))
        self.assertKhongDat(res, ["CAD_READ_SAI_SCHEMA"])
        res = Case.fixture(self).run(mut_cad=lambda c: c["layers"][0].pop("name"))
        self.assertKhongDat(res, ["CAD_READ_SAI_SCHEMA"])

    def test_report_that_points_at_other_files(self):
        for key, mut in {"input_sha256": lambda r: r["input"].update(input_sha256="0" * 64),
                         "dwg_sha256": lambda r: r["input"].update(dwg_sha256="0" * 64),
                         "file_id": lambda r: r["input"].update(file_id="F02"),
                         "rules_sha256": lambda r: r["rules_file"].update(sha256="0" * 64),
                         "rules_version": lambda r: r["rules_file"].update(rules_version="other")}.items():
            with self.subTest(key):
                res = Case.fixture(self).run(mut_report=mut)
                self.assertKhongDat(res, ["LIEN_KET_BAO_CAO_SAI"])
                self.assertEqual([k for k, ok in res.out["lien_ket_bao_cao"].items() if not ok], [key])


class EvidenceIds(BaseTest):
    """Bước 3. Ca nào đổi evidence ID cấp dòng thì dòng đó cũng thiếu ID của trường được kiểm (bước 4)."""

    def mut_rule_ev(self, rule_id, fn):
        def mut(report):
            rule = rule_entry(report, rule_id)
            rule["evidence_ids"] = fn(rule["evidence_ids"])
        return mut

    def test_wrong_form_that_the_schema_still_accepts(self):
        """Schema dùng `$` nên chấp nhận ID có "\\n" ở cuối; phép kiểm truy vết dùng fullmatch và từ chối."""
        case = Case.fixture(self, "cad_read_fail.json")
        res = case.run(mut_report=self.mut_rule_ev("R-LAYER-NAME", lambda ids: [ids[0] + "\n"]))
        self.assertKhongDat(res, ["EVIDENCE_ID_SAI_DANG"])
        self.assertEqual(res.out["buoc3_evidence_id"]["sai_dang"], 1)

    def test_wrong_file_id(self):
        res = Case.fixture(self, "cad_read_fail.json").run(
            mut_report=self.mut_rule_ev("R-LAYER-NAME", lambda ids: ["CADEV:F02:14:name"]))
        self.assertKhongDat(res, ["EVIDENCE_ID_SAI_FILE_ID"])
        self.assertEqual(res.out["buoc3_evidence_id"]["sai_file_id"], 1)

    def test_ids_that_resolve_to_nothing(self):
        ids = {"unknown handle": "CADEV:F01:FFFF:name", "unknown field": "CADEV:F01:14:nonexistent",
               "file path that does not exist": "CADEV:F01:FILE:coverage.layers.bogus",
               "units field that does not exist": "CADEV:F01:FILE:units.nothing",
               "file path that is not a single value": "CADEV:F01:FILE:coverage.layers"}
        for name, ev in ids.items():
            with self.subTest(name):
                res = Case.fixture(self, "cad_read_fail.json").run(
                    mut_report=self.mut_rule_ev("R-LAYER-NAME", lambda old, ev=ev: old + [ev]))
                self.assertKhongDat(res, ["EVIDENCE_ID_KHONG_GIAI_DUOC"])
                self.assertEqual(res.out["buoc3_evidence_id"]["khong_giai_duoc"], 1)

    def test_file_level_id_of_a_rule_with_a_missing_field(self):
        res = Case.fixture(self, "cad_read_unknown.json").run(
            mut_report=self.mut_rule_ev("R-LAYER-NAME", lambda ids: ["CADEV:F01:FILE:coverage.layers.bogus"]))
        self.assertKhongDat(res, ["EVIDENCE_ID_KHONG_GIAI_DUOC"])

    def test_id_that_resolves_to_two_values_across_groups(self):
        """Một block dùng lại handle của layer 14: `CADEV:F01:14:name` có hai giá trị."""
        def dup(cad):
            cad["blocks"].append({"handle": "14", "space": "MODEL", "name": "OTHER", "is_xref_dependent": False, "entity_count": 1})
        res = Case.fixture(self, "cad_read_fail.json").run(mut_cad=dup)
        self.assertKhongDat(res, ["EVIDENCE_ID_NHIEU_GIA_TRI", "ACTUAL_LECH", "PHAM_VI_LECH"])   # actual không xác định; quy tắc block có thêm đối tượng
        self.assertGreater(res.out["buoc3_evidence_id"]["nhieu_gia_tri"], 0)

    def test_id_that_resolves_to_two_values_inside_one_group(self):
        """Hai layer cùng handle (dựng thẳng, không qua loader của cadaudit): ID có hai giá trị, dòng không xác định."""
        def dup(cad):
            cad["layers"].append(dict(cad["layers"][0], name="DUPLICATE"))
        res = Case.fixture(self, "cad_read_pass.json").run(mut_cad=dup)
        self.assertKhongDat(res, ["EVIDENCE_ID_NHIEU_GIA_TRI", "DONG_KHONG_TIM_THAY_DOI_TUONG", "PHAM_VI_LECH"])   # hai đối tượng, một dòng

    def test_row_level_id_replaced_by_one_that_resolves_is_not_the_checked_field(self):
        def mut(report):
            result_row(report, "R-LAYER-NAME", "14")["evidence_ids"] = ["CADEV:F01:13:name"]
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=mut)
        self.assertKhongDat(res, ["DONG_THIEU_ID_TRUONG_KIEM"])
        self.assertEqual(res.out["buoc3_evidence_id"]["giai_dung_mot"], res.out["buoc3_evidence_id"]["tong"])


class ActualValues(BaseTest):
    def test_actual_that_differs_from_the_cited_value(self):
        for rule, handle, new in (("R-LAYER-NAME", "14", "wall_02"), ("R-TEXT-HEIGHT", "51", 1.5),
                                  ("R-XREF-RESOLVED", "70", "RESOLVED"), ("R-UNITS", "FILE", 5),
                                  ("R-DIM-OVERRIDE", "60", 2400.0)):
            with self.subTest(rule=rule):
                def mut(report, rule=rule, handle=handle, new=new):
                    result_row(report, rule, handle)["actual"] = new
                res = Case.fixture(self, "cad_read_fail.json").run(mut_report=mut)
                self.assertKhongDat(res, ["ACTUAL_LECH"])
                self.assertEqual(res.out["buoc4_actual"]["actual_lech"], 1)

    def test_equals_field_actual_is_the_second_field(self):
        """R-DIM-OVERRIDE: actual là `display_value` (field_b), không phải `measured_value`."""
        case = Case.fixture(self, "cad_read_fail.json")
        row = result_row(case.report, "R-DIM-OVERRIDE", "60")
        self.assertEqual((row["actual"], row["evidence_ids"][1]), (2500.0, "CADEV:F01:60:display_value"))
        self.assertDat(case.run())

    def test_null_actual_is_wrong_when_the_source_value_is_not_null(self):
        def mut(report):
            result_row(report, "R-LAYER-NAME", "10")["actual"] = None
        self.assertKhongDat(Case.fixture(self).run(mut_report=mut), ["ACTUAL_LECH"])

    def test_non_null_actual_is_wrong_when_the_source_value_is_null(self):
        def mut(report):
            result_row(report, "R-TEXT-FONT", "50")["actual"] = "arial.ttf"
        self.assertKhongDat(Case.fixture(self, "cad_read_unknown.json").run(mut_report=mut), ["ACTUAL_LECH"])

    def test_pass_claimed_for_a_null_source_value(self):
        """Dòng PASS/FAIL mà trường nguồn là null: phải là UNKNOWN FIELD_MISSING, nên không được coi là khớp."""
        def mut(report):
            row = result_row(report, "R-TEXT-FONT", "50")
            row["verdict"], row["reason"] = "PASS", None          # actual vẫn null, đúng với nguồn
        res = Case.fixture(self, "cad_read_unknown.json").run(mut_report=mut)
        self.assertKhongDat(res, ["ACTUAL_LECH"], exact=False)

    def test_field_missing_claimed_for_a_value_that_exists(self):
        def mut(report):
            row = result_row(report, "R-TEXT-HEIGHT", "50")
            row["verdict"], row["reason"], row["actual"] = "UNKNOWN", "FIELD_MISSING", None
        res = Case.fixture(self, "cad_read_unknown.json").run(mut_report=mut)
        self.assertKhongDat(res, ["ACTUAL_LECH"], exact=False)

    def test_actual_of_a_standard_required_row(self):
        def mut(report):
            result_row(report, "R-STD-TEXT-HEIGHT", "50")["actual"] = 9.9
        self.assertKhongDat(Case.fixture(self, "cad_read_fail.json", "rules_standard.yaml").run(mut_report=mut), ["ACTUAL_LECH"])

    def test_bool_and_number_are_not_confused(self):
        self.assertTrue(kv.same(1, 1.0))
        self.assertFalse(kv.same(True, 1))
        self.assertFalse(kv.same("1", 1))
        self.assertTrue(kv.same(None, None))
        self.assertFalse(kv.same(None, 0))
        self.assertFalse(kv.same(None, ""))

    def test_attribute_tag_rows(self):
        """Dòng required_field/attribute_tag: giá trị lấy từ attribute (không phải từ block_ref); tag vắng thì actual null."""
        def mut(report):
            result_row(report, "R-TITLE-ATTR", "31")["actual"] = "FX-002"
        self.assertKhongDat(Case.fixture(self).run(mut_report=mut), ["ACTUAL_LECH"])

        def absent(report):
            result_row(report, "R-TITLE-ATTR", "31")["actual"] = "FX-001"
        self.assertKhongDat(Case.fixture(self, "cad_read_fail.json").run(mut_report=absent), ["ACTUAL_LECH"])

    def test_absent_tag_fail_needs_the_proof_of_absence_ids(self):
        def mut(report):
            result_row(report, "R-TITLE-ATTR", "31")["evidence_ids"] = ["CADEV:F01:31:block_name"]
        self.assertKhongDat(Case.fixture(self, "cad_read_fail.json").run(mut_report=mut), ["DONG_THIEU_ID_TRUONG_KIEM"])


class RowStructure(BaseTest):
    def test_row_for_an_object_that_is_not_in_the_group(self):
        def mut(report):
            row = result_row(report, "R-LAYER-NAME", "10")
            row["handle"] = "20"       # handle của một block, không phải layer
        self.assertKhongDat(Case.fixture(self).run(mut_report=mut), ["DONG_KHONG_TIM_THAY_DOI_TUONG", "PHAM_VI_LECH"])

    def test_row_of_a_rule_that_is_not_in_the_rules_file(self):
        def mut(report):
            report["results"][0]["rule_id"] = "R-NOT-IN-FILE"
        res = Case.fixture(self).run(mut_report=mut)
        self.assertKhongDat(res, ["DONG_RULE_ID_LA", "OBJECTS_IN_SCOPE_LECH", "COUNTS_LECH"], exact=False)

    def test_reason_and_verdict_must_agree(self):
        def std_not_slne(report):
            result_row(report, "R-STD-TEXT-HEIGHT", "50")["reason"] = "FIELD_MISSING"

        def pass_with_reason(report):
            result_row(report, "R-LAYER-NAME", "10")["reason"] = "FIELD_MISSING"

        def unknown_without_reason(report):
            result_row(report, "R-TEXT-FONT", "50")["reason"] = None

        def internal_with_slne(report):
            row = result_row(report, "R-LAYER-NAME", "10")
            row["verdict"], row["reason"] = "UNKNOWN", "STANDARD_LOOKUP_NOT_ENABLED"
        for name, mut, inp, rules in (("std", std_not_slne, "cad_read_fail.json", "rules_standard.yaml"),
                                      ("pass with reason", pass_with_reason, "cad_read_pass.json", "rules_internal.yaml"),
                                      ("unknown without reason", unknown_without_reason, "cad_read_unknown.json", "rules_internal.yaml"),
                                      ("internal with SLNE", internal_with_slne, "cad_read_pass.json", "rules_internal.yaml")):
            with self.subTest(name):
                res = Case.fixture(self, inp, rules).run(mut_report=mut)
                self.assertKhongDat(res, ["DONG_LY_DO_LECH"], exact=False)

    def test_absent_tag_row_must_be_fail_only_when_attributes_is_complete(self):
        def mut(report):
            row = result_row(report, "R-TITLE-ATTR", "31")
            row["verdict"], row["reason"] = "UNKNOWN", "COVERAGE_INCOMPLETE"     # nhưng attributes COMPLETE
        self.assertKhongDat(Case.fixture(self, "cad_read_fail.json").run(mut_report=mut), ["DONG_LY_DO_LECH"], exact=False)


class PerRuleRecount(BaseTest):
    def test_counts(self):
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=lambda r: rule_entry(r, "R-LAYER-NAME")["counts"].update(PASS=5))
        self.assertKhongDat(res, ["COUNTS_LECH"])
        rule = next(x for x in res.out["buoc5_6_quy_tac"] if x["rule_id"] == "R-LAYER-NAME")
        self.assertEqual((rule["counts_khop"], rule["so_muc_lech"], rule["counts_tinh_lai"]),
                         (False, 1, {"PASS": 4, "FAIL": 1, "UNKNOWN": 0}))

    def test_objects_in_scope(self):
        res = Case.fixture(self).run(mut_report=lambda r: rule_entry(r, "R-LAYER-NAME").update(objects_in_scope=5))
        self.assertKhongDat(res, ["OBJECTS_IN_SCOPE_LECH"])

    def test_verdict(self):
        """FAIL báo thành PASS: lệch verdict, lệch phần tổng hợp (overall), không còn FAIL có evidence ở cấp quy tắc."""
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=lambda r: rule_entry(r, "R-UNITS").update(verdict="FAIL"))
        self.assertKhongDat(res, ["VERDICT_LECH", "SUMMARY_LECH", "FAIL_UNKNOWN_THIEU_EVIDENCE"])
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=lambda r: rule_entry(r, "R-LAYER-NAME").update(verdict="PASS"))
        self.assertKhongDat(res, ["VERDICT_LECH", "SUMMARY_LECH"])

    def test_reasons(self):
        res = Case.fixture(self, "cad_read_unknown.json").run(
            mut_report=lambda r: rule_entry(r, "R-LAYER-NAME").update(reasons=["FIELD_MISSING"]))
        self.assertKhongDat(res, ["REASONS_LECH"])
        res = Case.fixture(self, "cad_read_unknown.json").run(
            mut_report=lambda r: rule_entry(r, "R-TEXT-FONT").update(reasons=["COVERAGE_INCOMPLETE", "FIELD_MISSING"]))
        self.assertKhongDat(res, ["REASONS_LECH"])
        res = Case.fixture(self, "cad_read_pass.json").run(mut_report=lambda r: rule_entry(r, "R-LAYER-NAME").update(reasons=["NO_OBJECTS_IN_SCOPE"]))
        self.assertKhongDat(res, ["REASONS_LECH"])

    def test_coverage_complete(self):
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=lambda r: rule_entry(r, "R-LAYER-NAME").update(coverage_complete=False))
        self.assertKhongDat(res, ["COVERAGE_COMPLETE_LECH"])
        res = Case.fixture(self, "cad_read_unknown.json").run(mut_report=lambda r: rule_entry(r, "R-LAYER-NAME").update(coverage_complete=True))
        self.assertKhongDat(res, ["COVERAGE_COMPLETE_LECH"])

    def test_coverage_comes_from_the_cad_read_file_not_from_the_report(self):
        """CAD_READ nói layers INCOMPLETE nhưng báo cáo nói PASS và coverage_complete true."""
        def mut(cad):
            cad["coverage"]["layers"] = {"status": "INCOMPLETE", "expected": None, "enumerated": 4, "reason": "READ_ERROR"}
        res = Case.fixture(self, "cad_read_pass.json").run(mut_cad=mut)
        self.assertKhongDat(res, ["COVERAGE_COMPLETE_LECH", "VERDICT_LECH"], exact=False)
        stale = [r["rule_id"] for r in res.out["buoc5_6_quy_tac"] if not r["verdict_khop"]]
        self.assertEqual(stale, ["R-LAYER-NAME", "R-TEXT-FONT", "R-TEXT-HEIGHT"])   # các quy tắc có layers trong reads_groups

    def test_fail_is_kept_when_coverage_is_incomplete(self):
        cad = read_json(fx("cad_read_fail.json"))
        cad["coverage"]["layers"] = {"status": "INCOMPLETE", "expected": None, "enumerated": 5, "reason": "READ_ERROR"}
        case = Case(self, cad, read_bytes(fx("rules_internal.yaml")))
        layer = rule_entry(case.report, "R-LAYER-NAME")
        self.assertEqual((layer["verdict"], layer["coverage_complete"]), ("FAIL", False))
        self.assertDat(case.run())

    def test_rule_metadata_against_the_rules_file(self):
        raw = read_bytes(fx("rules_internal.yaml"))
        old = b"status: FIXTURE\n    source: \"FIXTURE (fake, no real source)\"\n    applies_to: layers"
        self.assertIn(old, raw)
        res = Case.fixture(self).run(rules_bytes=raw.replace(old, old.replace(b"FIXTURE", b"PROPOSED", 1)))   # báo cáo vẫn ghi FIXTURE; hash quy tắc đã sửa cho khớp
        self.assertKhongDat(res, ["QUY_TAC_KHONG_KHOP_TEP"])
        self.assertFalse(next(r for r in res.out["buoc5_6_quy_tac"] if r["rule_id"] == "R-LAYER-NAME")["meta_khop"])

    def test_rule_list_of_the_report_against_the_rules_file(self):
        raw = read_bytes(fx("rules_internal.yaml"))
        cut = raw[:raw.index(b"  - id: R-UNITS")]               # bỏ quy tắc cuối khỏi tệp quy tắc
        res = Case.fixture(self).run(rules_bytes=cut)
        self.assertKhongDat(res, ["QUY_TAC_KHONG_KHOP_TEP", "DONG_RULE_ID_LA"])

    def test_rule_order_of_the_report_against_the_rules_file(self):
        def swap(report):
            report["rules"][0], report["rules"][1] = report["rules"][1], report["rules"][0]
        res = Case.fixture(self).run(mut_report=swap)
        self.assertKhongDat(res, ["QUY_TAC_KHONG_KHOP_TEP"])
        self.assertTrue(all(r["so_muc_lech"] == 0 for r in res.out["buoc5_6_quy_tac"]))   # từng quy tắc vẫn khớp; chỉ thứ tự lệch

    def test_summary(self):
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=lambda r: r["summary"].update(overall="ALL_RULES_PASS"))
        self.assertKhongDat(res, ["SUMMARY_LECH"])
        res = Case.fixture(self, "cad_read_pass.json").run(mut_report=lambda r: r["summary"].pop("overall_note"))
        self.assertKhongDat(res, ["SUMMARY_LECH"])
        res = Case.fixture(self, "cad_read_pass.json").run(mut_report=lambda r: r["summary"].update(all_rules_approved=True))
        self.assertKhongDat(res, ["SUMMARY_LECH"])
        res = Case.fixture(self, "cad_read_pass.json").run(mut_report=lambda r: r["summary"]["results_by_verdict"].update(PASS=0, FAIL=15))
        self.assertKhongDat(res, ["SUMMARY_LECH"])


class FailAndUnknownNeedEvidence(BaseTest):
    def test_rule_level_fail_without_evidence(self):
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=lambda r: rule_entry(r, "R-LAYER-NAME").update(evidence_ids=[]))
        self.assertKhongDat(res, ["FAIL_UNKNOWN_THIEU_EVIDENCE"])
        self.assertEqual(res.out["buoc7_thieu_evidence"], {"quy_tac_thieu_evidence": 1, "dong_thieu_evidence": 0})

    def test_rule_level_unknown_without_evidence(self):
        res = Case.fixture(self, "cad_read_unknown.json").run(mut_report=lambda r: rule_entry(r, "R-LAYER-NAME").update(evidence_ids=[]))
        self.assertKhongDat(res, ["FAIL_UNKNOWN_THIEU_EVIDENCE"])

    def test_row_level_fail_without_evidence(self):
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=lambda r: result_row(r, "R-LAYER-NAME", "14").update(evidence_ids=[]))
        self.assertKhongDat(res, ["DONG_THIEU_ID_TRUONG_KIEM", "FAIL_UNKNOWN_THIEU_EVIDENCE"])
        self.assertEqual(res.out["buoc7_thieu_evidence"]["dong_thieu_evidence"], 1)

    def test_row_level_unknown_without_evidence(self):
        res = Case.fixture(self, "cad_read_unknown.json").run(mut_report=lambda r: result_row(r, "R-TEXT-FONT", "50").update(evidence_ids=[]))
        self.assertKhongDat(res, ["DONG_THIEU_ID_TRUONG_KIEM", "FAIL_UNKNOWN_THIEU_EVIDENCE"])
        self.assertEqual(res.out["buoc7_thieu_evidence"]["dong_thieu_evidence"], 1)

    def test_pass_without_evidence_is_fine(self):
        case = Case.fixture(self)
        self.assertEqual(rule_entry(case.report, "R-LAYER-NAME")["evidence_ids"], [])
        self.assertDat(case.run())


# ---------------------------------------------------------------------------------------------------- 4b: verdict từng dòng
def layer_obj(cad, handle, name):
    return dict(cad["layers"][0], handle=handle, name=name)


def complete(n):
    return {"status": "COMPLETE", "expected": n, "enumerated": n, "reason": None}


def rules_yaml(*rules):
    body = "".join(f"  - {r}\n" for r in rules)
    return ("schema: tvxd.cadaudit.rules/v1\nrules_version: x.1\nrules:\n" + body).encode("utf-8")


def rule_text(rid, group, check, selector="{}", status="FIXTURE"):
    return (f"{{id: {rid}, title: t, status: {status}, source: s, applies_to: {group}, selector: {selector},\n"
            f"     check: {check}, standard_required: false}}")


class RowVerdict(BaseTest):
    def test_flip_one_row_verdict_per_check_type(self):
        blank = read_json(fx("cad_read_pass.json"))
        blank["attributes"][0]["value"] = "   "
        field_rules = rules_yaml(rule_text("R-VALUE", "texts", "{type: required_field, field: value}"))
        blank_text = read_json(fx("cad_read_pass.json"))
        blank_text["texts"][0]["value"] = " \t "
        table = [  # (tên, Case, rule, handle, verdict mới)
            ("name_pattern FAIL->PASS", Case.fixture(self, "cad_read_fail.json"), "R-LAYER-NAME", "14", "PASS"),
            ("name_pattern PASS->FAIL", Case.fixture(self, "cad_read_fail.json"), "R-LAYER-NAME", "10", "FAIL"),
            ("allowed_values FAIL->PASS", Case.fixture(self, "cad_read_fail.json"), "R-TEXT-FONT", "50", "PASS"),
            ("allowed_values PASS->FAIL", Case.fixture(self, "cad_read_fail.json"), "R-TEXT-FONT", "51", "FAIL"),
            ("numeric_range FAIL->PASS", Case.fixture(self, "cad_read_fail.json"), "R-TEXT-HEIGHT", "51", "PASS"),
            ("numeric_range PASS->FAIL", Case.fixture(self, "cad_read_fail.json"), "R-TEXT-HEIGHT", "50", "FAIL"),
            ("equals_field FAIL->PASS", Case.fixture(self, "cad_read_fail.json"), "R-DIM-OVERRIDE", "60", "PASS"),
            ("equals_field PASS->FAIL", Case.fixture(self), "R-DIM-OVERRIDE", "60", "FAIL"),
            ("xref_resolved FAIL->PASS", Case.fixture(self, "cad_read_fail.json"), "R-XREF-RESOLVED", "70", "PASS"),
            ("xref_resolved PASS->FAIL", Case.fixture(self), "R-XREF-RESOLVED", "70", "FAIL"),
            ("attribute_tag PASS->FAIL", Case.fixture(self), "R-TITLE-ATTR", "31", "FAIL"),
            ("attribute_tag blank FAIL->PASS", Case(self, blank, read_bytes(fx("rules_internal.yaml"))), "R-TITLE-ATTR", "31", "PASS"),
            ("required_field PASS->FAIL", Case(self, read_json(fx("cad_read_pass.json")), field_rules), "R-VALUE", "50", "FAIL"),
            ("required_field blank FAIL->PASS", Case(self, blank_text, field_rules), "R-VALUE", "50", "PASS"),
            ("units allowed_values PASS->FAIL", Case.fixture(self), "R-UNITS", "FILE", "FAIL"),
        ]
        for name, case, rule_id, handle, new in table:
            with self.subTest(name):
                self.assertNotEqual(result_row(case.report, rule_id, handle)["verdict"], new)
                self.assertDat(case.run(mut_report=resync))                       # nền: báo cáo thật, đã đồng bộ
                res = case.run(mut_report=flip(rule_id, handle, new))
                self.assertKhongDat(res, ["DONG_VERDICT_LECH"])                   # chỉ verdict dòng lệch, mọi số đếm tự nhất quán
                self.assertEqual(res.out["buoc4_actual"]["verdict_dong_lech"], 1)

    def test_chc_allowed_values_layer_outside_the_list_reported_as_pass(self):
        """Hình dạng CHC-LAYER-V2: allowed_values trên tên layer. Báo cáo ghi PASS cho layer ngoài danh sách."""
        cad = chc_like_cad(["FAKE-LAYER-ONE", "FAKE-LAYER-OTHER"], ["RESOLVED", "RESOLVED"], "COMPLETE")
        case = Case(self, cad, CHC_RULES)
        self.assertEqual(result_row(case.report, "FAKE-LAYER-LIST", "A2")["verdict"], "FAIL")
        self.assertDat(case.run())
        res = case.run(mut_report=flip("FAKE-LAYER-LIST", "A2", "PASS"))     # quy tắc thành PASS, summary thành HAS_UNKNOWN/ALL_RULES_PASS
        self.assertKhongDat(res, ["DONG_VERDICT_LECH"])
        self.assertEqual(rule_entry(case.report, "FAKE-LAYER-LIST")["verdict"], "FAIL")      # báo cáo thật nói FAIL

    def test_chc_xref_resolved_reported_as_fail(self):
        """Hình dạng CHC-XREF-RESOLVED: báo cáo ghi FAIL cho xref có path_status RESOLVED."""
        cad = chc_like_cad(["FAKE-LAYER-ONE"], ["RESOLVED", "RESOLVED"], "COMPLETE")
        case = Case(self, cad, CHC_RULES)
        self.assertEqual(result_row(case.report, "FAKE-XREF-RESOLVED", "B1")["verdict"], "PASS")
        res = case.run(mut_report=flip("FAKE-XREF-RESOLVED", "B1", "FAIL"))
        self.assertKhongDat(res, ["DONG_VERDICT_LECH"])

    def test_unsynchronised_flip_is_caught_by_row_verdict_as_well(self):
        """Không đồng bộ lại số đếm: vẫn có DONG_VERDICT_LECH (cùng các mã đếm lệch)."""
        def mut(report):
            result_row(report, "R-LAYER-NAME", "14")["verdict"] = "PASS"
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=mut)
        self.assertKhongDat(res, ["DONG_VERDICT_LECH", "COUNTS_LECH"], exact=False)

    def test_verdict_checks_do_not_apply_to_unknown_and_standard_rows(self):
        self.assertDat(Case.fixture(self, "cad_read_unknown.json").run())
        self.assertDat(Case.fixture(self, "cad_read_fail.json", "rules_standard.yaml").run())


def edge_cad():
    """CAD_READ giả có giá trị sát biên cho mọi loại check (để so với kết quả thật của cadaudit)."""
    cad = read_json(fx("cad_read_pass.json"))
    heights = [2.4999, 2.5, 3.5, 3.5001, 3.5002, 2.4998, 0.0, 3.0, 3.0, 2.0, 3.5]
    fonts = ["arial.ttf", "ARIAL.TTF", "simplex.shx", "arial.ttf", "STD", "STD", "arial.ttf", None, "simplex.shx", "x", "STD"]
    values = ["x", "", "  ", "\t\n", " a ", "ok", None, "x", "x", "x", "x"]
    cad["texts"] = [{"handle": f"{0x200 + i:X}", "space": "MODEL", "text_type": "TEXT", "value": v, "style": "STD", "font": f,
                     "height": h, "layer": "A-ANNO-TEXT"} for i, (h, f, v) in enumerate(zip(heights, fonts, values))]
    names = ["A-DOR", "A-D", "B-XXX", "A-WALL", "A-X", "A-XY", "A-" + "X" * 253, "A-ANNO-TEXT"]
    cad["layers"] = [layer_obj(cad, f"{0x100 + i:X}", n) for i, n in enumerate(names)]
    dims = [(2400, 2400.4, 1.0), (2400, 2400.5, 1), (2400, 2400.6, 2.5), (None, 1.0, 3.0), (5, 5, 1.0)]
    cad["dimensions"] = [{"handle": f"{0x300 + i:X}", "space": "MODEL", "dim_type": "LINEAR", "measured_value": m,
                          "display_value": d, "dimscale": sc, "layer": "A-ANNO-DIM"} for i, (m, d, sc) in enumerate(dims)]
    cad["xrefs"] = [{"handle": f"{0x400 + i:X}", "space": "MODEL", "name": f"XR-{i}", "path_status": st}
                    for i, st in enumerate(["RESOLVED", "NOT_FOUND", "UNRESOLVED", None])]
    cad["attributes"][0]["value"] = "   "                                  # DRAWING_NO chỉ có khoảng trắng
    cad["attributes"] = [dict(cad["attributes"][0], handle="40", tag="DRAWING_NO", value="   "),
                         dict(cad["attributes"][0], handle="41", tag="REVISION", value="A")]
    for g in ("layers", "texts", "dimensions", "xrefs", "attributes"):
        cad["coverage"][g] = complete(len(cad[g]))
    return cad


EDGE_RULES = rules_yaml(
    rule_text("H-TOL", "texts", "{type: numeric_range, field: height, min: 2.5, max: 3.5, tolerance: 0.0001}"),
    rule_text("H-MIN", "texts", "{type: numeric_range, field: height, min: 3}"),
    rule_text("H-MAX", "texts", "{type: numeric_range, field: height, max: 3, tolerance: 0.5}"),
    rule_text("F-ALLOWED", "texts", "{type: allowed_values, field: font, values: [arial.ttf, simplex.shx]}"),
    rule_text("V-REQUIRED", "texts", "{type: required_field, field: value}"),
    rule_text("T-EQUALS-STR", "texts", "{type: equals_field, field_a: style, field_b: font}"),
    rule_text("L-LEN5", "layers", "{type: name_pattern, field: name, pattern: 'A-.*', max_length: 5}"),
    rule_text("L-DEFAULT", "layers", "{type: name_pattern, field: name, pattern: 'A-.*'}"),
    rule_text("L-FULLMATCH", "layers", "{type: name_pattern, field: name, pattern: 'A-X'}"),
    rule_text("D-SCALE", "dimensions", "{type: allowed_values, field: dimscale, values: [1, 2.5]}"),
    rule_text("D-EQ-TOL", "dimensions", "{type: equals_field, field_a: measured_value, field_b: display_value, tolerance: 0.5}"),
    rule_text("D-EQ-EXACT", "dimensions", "{type: equals_field, field_a: measured_value, field_b: display_value}"),
    rule_text("X-RESOLVED", "xrefs", "{type: xref_resolved}"),
    rule_text("AT-BLANK", "block_refs", "{type: required_field, attribute_tag: DRAWING_NO}", "{block_name: TITLEBLOCK}"),
    rule_text("AT-REV", "block_refs", "{type: required_field, attribute_tag: REVISION}", "{block_name: TITLEBLOCK}"),
)


class EdgeValuesAgainstCadaudit(BaseTest):
    """So phép kiểm hiện thực lại với kết quả thật của cadaudit trên giá trị sát biên: phải DAT, và dữ liệu
    phải thực sự có đủ PASS, FAIL và UNKNOWN ở mỗi loại check (nếu không thì ca này chưa thử gì)."""

    def test_edge_values_agree_with_cadaudit(self):
        case = Case(self, edge_cad(), EDGE_RULES)
        expected = {"H-TOL": (7, 4, 0), "H-MIN": (6, 5, 0), "H-MAX": (9, 2, 0), "F-ALLOWED": (5, 5, 1), "V-REQUIRED": (7, 3, 1),
                    "T-EQUALS-STR": (3, 7, 1), "L-LEN5": (4, 4, 0), "L-DEFAULT": (7, 1, 0), "L-FULLMATCH": (1, 7, 0),
                    "D-SCALE": (4, 1, 0), "D-EQ-TOL": (3, 1, 1), "D-EQ-EXACT": (1, 3, 1), "X-RESOLVED": (1, 2, 1),
                    "AT-BLANK": (0, 1, 0), "AT-REV": (1, 0, 0)}
        got = {r["rule_id"]: (r["counts"]["PASS"], r["counts"]["FAIL"], r["counts"]["UNKNOWN"]) for r in case.report["rules"]}
        self.assertEqual(got, expected)      # dữ liệu có đủ PASS, FAIL, FIELD_MISSING sát biên ở mỗi loại check
        res = case.run()
        self.assertDat(res)
        self.assertEqual(res.out["buoc4_actual"]["verdict_dong_lech"], 0)

    def test_flipping_any_pass_or_fail_row_of_every_rule_is_caught(self):
        case = Case(self, edge_cad(), EDGE_RULES)
        for rule in case.report["rules"]:
            row = next(r for r in case.report["results"] if r["rule_id"] == rule["rule_id"] and r["verdict"] in ("PASS", "FAIL"))
            with self.subTest(rule["rule_id"]):
                out = case.run(mut_report=flip(rule["rule_id"], row["handle"], "PASS" if row["verdict"] == "FAIL" else "FAIL"))
                self.assertKhongDat(out, ["DONG_VERDICT_LECH"])


class EvaluateCheckUnit(unittest.TestCase):
    def rule(self, check, group="texts"):
        return kv.load_rules(rules_yaml(rule_text("R-X", group, check)))[1][0]

    def test_name_pattern(self):
        r = self.rule("{type: name_pattern, field: name, pattern: 'A-[A-Z]+', max_length: 6}", "layers")
        self.assertEqual([kv.evaluate_check(r, [v]) for v in ("A-WALL", "A-WALLS", "A-WALL-2", "a-wall", "")],
                         ["PASS", "FAIL", "FAIL", "FAIL", "FAIL"])
        d = self.rule("{type: name_pattern, field: name, pattern: '.*'}", "layers")
        self.assertEqual((kv.evaluate_check(d, ["x" * 255]), kv.evaluate_check(d, ["x" * 256])), ("PASS", "FAIL"))   # mặc định 255
        self.assertIsNone(kv.evaluate_check(d, [5]))

    def test_allowed_values(self):
        r = self.rule("{type: allowed_values, field: height, values: [1, 2.5]}")
        self.assertEqual([kv.evaluate_check(r, [v]) for v in (1, 1.0, 2.5, 2, True)], ["PASS", "PASS", "PASS", "FAIL", "FAIL"])
        s = self.rule("{type: allowed_values, field: font, values: [a.ttf]}")
        self.assertEqual([kv.evaluate_check(s, [v]) for v in ("a.ttf", "A.TTF", " a.ttf")], ["PASS", "FAIL", "FAIL"])

    def test_numeric_range(self):
        r = self.rule("{type: numeric_range, field: height, min: 2, max: 4, tolerance: 0.5}")
        self.assertEqual([kv.evaluate_check(r, [v]) for v in (1.5, 1.4, 4.5, 4.6, 3)], ["PASS", "FAIL", "PASS", "FAIL", "PASS"])
        lo = self.rule("{type: numeric_range, field: height, min: 2}")
        hi = self.rule("{type: numeric_range, field: height, max: 2}")
        self.assertEqual((kv.evaluate_check(lo, [1.9]), kv.evaluate_check(lo, [1e9]), kv.evaluate_check(hi, [2.1]), kv.evaluate_check(hi, [-1e9])),
                         ("FAIL", "PASS", "FAIL", "PASS"))
        self.assertIsNone(kv.evaluate_check(lo, ["3"]))
        self.assertIsNone(kv.evaluate_check(lo, [True]))

    def test_required_field(self):
        r = self.rule("{type: required_field, field: value}")
        self.assertEqual([kv.evaluate_check(r, [v]) for v in ("x", " x ", "", "  ", "\t\n", 0)], ["PASS", "PASS", "FAIL", "FAIL", "FAIL", "PASS"])

    def test_equals_field(self):
        n = self.rule("{type: equals_field, field_a: measured_value, field_b: display_value, tolerance: 0.5}", "dimensions")
        self.assertEqual([kv.evaluate_check(n, [100, v]) for v in (100.5, 100.6, 99.5, 99.4)], ["PASS", "FAIL", "PASS", "FAIL"])
        e = self.rule("{type: equals_field, field_a: measured_value, field_b: display_value}", "dimensions")
        self.assertEqual((kv.evaluate_check(e, [1, 1.0]), kv.evaluate_check(e, [1, 1.0000001])), ("PASS", "FAIL"))
        t = self.rule("{type: equals_field, field_a: style, field_b: font}")
        self.assertEqual((kv.evaluate_check(t, ["STD", "STD"]), kv.evaluate_check(t, ["STD", "std"])), ("PASS", "FAIL"))
        self.assertIsNone(kv.evaluate_check(n, [1, "x"]))

    def test_xref_resolved(self):
        r = self.rule("{type: xref_resolved}", "xrefs")
        self.assertEqual([kv.evaluate_check(r, [v]) for v in ("RESOLVED", "NOT_FOUND", "UNRESOLVED", "resolved")],
                         ["PASS", "FAIL", "FAIL", "FAIL"])

    def test_bad_rule_shapes_are_input_errors(self):
        for text in ("{type: name_pattern, field: name, pattern: '('}", "{type: nonsense}"):
            with self.assertRaises(kv.InputError):
                kv.load_rules(rules_yaml(rule_text("R-X", "layers", text)))
        with self.assertRaises(kv.InputError):
            kv.load_rules(rules_yaml(rule_text("R-X", "layers", "{type: xref_resolved}", "{colour: 1}")))
        with self.assertRaises(kv.InputError):
            kv.load_rules(rules_yaml(rule_text("R-X", "texts", "{type: xref_resolved}", "{name_pattern: 'a'}")))


# ---------------------------------------------------------------------------------------------------- 5b: phạm vi
def scope_cad():
    cad = read_json(fx("cad_read_pass.json"))
    for h, n in (("90", "0"), ("91", "Defpoints"), ("92", "XR|A-WALL"), ("93", "A-WALL-2")):
        cad["layers"].append(layer_obj(cad, h, n))
    cad["coverage"]["layers"] = complete(len(cad["layers"]))
    cad["texts"][1]["space"] = "Layout1"
    return cad


SCOPE_RULES = rules_yaml(
    rule_text("R-L-SEL", "layers", "{type: name_pattern, field: name, pattern: 'A-.*'}", "{name_pattern: '(?!0$|Defpoints$)[^|]+'}"),
    rule_text("R-L-FULL", "layers", "{type: name_pattern, field: name, pattern: 'A-.*'}", "{name_pattern: 'A-[A-Z]+'}"),
    rule_text("R-SPACE", "texts", "{type: numeric_range, field: height, min: 0, max: 10}", "{space: MODEL}"),
    rule_text("R-TAG", "attributes", "{type: required_field, field: value}", "{tag: REVISION}"),
    rule_text("R-ATTR-LAYER", "attributes", "{type: required_field, field: value}", "{layer: A-ANNO-TEXT}"),
    rule_text("R-ATTR-BLOCK", "attributes", "{type: required_field, field: value}", "{block_name: TITLEBLOCK}"),
    rule_text("R-ATTR-NONE", "attributes", "{type: required_field, field: value}", "{layer: A-DOOR}"),
    rule_text("R-ATTR-AND", "attributes", "{type: required_field, field: value}", "{layer: A-ANNO-TEXT, tag: REVISION}"),
    rule_text("R-REF-BLOCK", "block_refs", "{type: name_pattern, field: layer, pattern: 'A-.*'}", "{block_name: DOOR-900}"),
    rule_text("R-REF-LAYER", "block_refs", "{type: name_pattern, field: block_name, pattern: '.*'}", "{layer: A-ANNO-TEXT}"),
    rule_text("R-REF-NAME", "block_refs", "{type: name_pattern, field: layer, pattern: '.*'}", "{name_pattern: 'DOOR-[0-9]+'}"),
    rule_text("R-BLOCK-SEL", "blocks", "{type: name_pattern, field: name, pattern: '.*'}", "{name_pattern: 'DOOR-[0-9]+'}"),
    rule_text("R-XREF-SPACE", "xrefs", "{type: xref_resolved}", "{space: MODEL, name_pattern: 'XR-.*'}"),
    rule_text("R-UNITS", "units", "{type: allowed_values, field: insunits, values: [4]}"),
)


class Scope(BaseTest):
    def case(self):
        return Case(self, scope_cad(), SCOPE_RULES)

    def scope_of(self, res, rule_id):
        return next(r for r in res.out["buoc5_6_quy_tac"] if r["rule_id"] == rule_id)

    def test_every_selector_key_agrees_with_cadaudit(self):
        case = self.case()
        counts = {r["rule_id"]: r["objects_in_scope"] for r in case.report["rules"]}
        self.assertEqual(counts, {"R-L-SEL": 5, "R-L-FULL": 2, "R-SPACE": 1, "R-TAG": 1, "R-ATTR-LAYER": 2, "R-ATTR-BLOCK": 2,
                                  "R-ATTR-NONE": 0, "R-ATTR-AND": 1, "R-REF-BLOCK": 1, "R-REF-LAYER": 1, "R-REF-NAME": 1, "R-BLOCK-SEL": 1, "R-XREF-SPACE": 1,
                                  "R-UNITS": 1})
        res = case.run()
        self.assertDat(res)
        for r in res.out["buoc5_6_quy_tac"]:
            self.assertEqual((r["pham_vi_khop"], r["thieu_dong"], r["thua_dong"]), (True, 0, 0), r["rule_id"])
            self.assertEqual(r["so_doi_tuong_pham_vi_tinh_lai"], counts[r["rule_id"]])

    def test_name_pattern_selector_keeps_out_zero_defpoints_and_xref_layers(self):
        case = self.case()
        handles = [r["handle"] for r in case.report["results"] if r["rule_id"] == "R-L-SEL"]
        self.assertEqual(sorted(handles), ["10", "11", "12", "13", "93"])      # không có 90 ("0"), 91 (Defpoints), 92 ("XR|A-WALL")
        for h in ("90", "91", "92"):                                           # dòng thừa cho layer đáng lẽ bị loại
            def extra(report, h=h):
                template = result_row(report, "R-L-SEL", "10")
                report["results"].append(dict(template, handle=h, evidence_ids=[f"CADEV:F01:{h}:name"],
                                              actual=next(x["name"] for x in case.cad["layers"] if x["handle"] == h)))
                resync(report)
            with self.subTest(h):
                res = case.run(mut_report=extra)
                self.assertKhongDat(res, ["PHAM_VI_LECH", "DONG_VERDICT_LECH"], exact=False)
                self.assertEqual(self.scope_of(res, "R-L-SEL")["thua_dong"], 1)

    def test_dropped_fail_row_with_consistent_counts_verdict_and_summary(self):
        """Mục tiêu của 5b: bỏ một layer FAIL rồi sửa counts, objects_in_scope, verdict, summary cho tự nhất quán."""
        case = Case.fixture(self, "cad_read_fail.json")
        self.assertDat(case.run(mut_report=resync))
        res = case.run(mut_report=drop("R-LAYER-NAME", "14"))
        self.assertKhongDat(res, ["PHAM_VI_LECH"])
        rule = self.scope_of(res, "R-LAYER-NAME")
        self.assertEqual((rule["thieu_dong"], rule["thua_dong"], rule["pham_vi_khop"], rule["so_muc_lech"]), (1, 0, False, 1))
        self.assertEqual(rule["verdict"], "PASS")                                          # báo cáo giờ nói PASS
        self.assertTrue(rule["counts_khop"] and rule["verdict_khop"] and rule["objects_in_scope_khop"])   # và tự nhất quán
        self.assertTrue(res.out["tong_hop_khop"])

    def test_dropped_row_of_each_selector_rule(self):
        case = self.case()
        seen = 0
        for rule in case.report["rules"]:
            rows = [r for r in case.report["results"] if r["rule_id"] == rule["rule_id"]]
            if not rows:
                continue
            seen += 1
            with self.subTest(rule["rule_id"]):
                res = case.run(mut_report=drop(rule["rule_id"], rows[0]["handle"]))
                self.assertKhongDat(res, ["PHAM_VI_LECH"])
                self.assertEqual(self.scope_of(res, rule["rule_id"])["thieu_dong"], 1)
        self.assertEqual(seen, 13)

    def test_duplicate_row_is_an_extra_row(self):
        def dup(report):
            report["results"].append(copy.deepcopy(result_row(report, "R-L-SEL", "10")))
            resync(report)
        res = self.case().run(mut_report=dup)
        self.assertKhongDat(res, ["PHAM_VI_LECH"])
        self.assertEqual((self.scope_of(res, "R-L-SEL")["thieu_dong"], self.scope_of(res, "R-L-SEL")["thua_dong"]), (0, 1))

    def test_row_for_an_object_outside_the_selector(self):
        """Layer "A-ANNO-TEXT" khớp R-L-SEL nhưng không khớp R-L-FULL (có hai dấu gạch): dòng đó là thừa."""
        def extra(report):
            report["results"].append(dict(result_row(report, "R-L-FULL", "10"), handle="12", evidence_ids=["CADEV:F01:12:name"],
                                          actual="A-ANNO-TEXT"))
            resync(report)
        res = self.case().run(mut_report=extra)
        self.assertKhongDat(res, ["PHAM_VI_LECH"])
        self.assertEqual(self.scope_of(res, "R-L-FULL")["thua_dong"], 1)

    def test_swapped_row_is_both_missing_and_extra(self):
        def swap(report):
            row = result_row(report, "R-L-FULL", "10")
            row.update(handle="11", evidence_ids=["CADEV:F01:11:name"], actual="A-DOOR")      # đối tượng 11 có trong phạm vi
            report["results"].append(dict(row, handle="12", evidence_ids=["CADEV:F01:12:name"], actual="A-ANNO-TEXT"))
            resync(report)
        res = self.case().run(mut_report=swap)
        self.assertKhongDat(res, ["PHAM_VI_LECH"], exact=False)

    def test_units_scope_uses_file(self):
        res = self.case().run(mut_report=drop("R-UNITS", "FILE"))
        self.assertKhongDat(res, ["PHAM_VI_LECH"])
        self.assertEqual(self.scope_of(res, "R-UNITS")["thieu_dong"], 1)

    def test_attribute_whose_parent_is_missing_stays_in_scope(self):
        cad = scope_cad()
        cad["attributes"][0]["parent_handle"] = "FF"
        cad["coverage"]["block_refs"] = {"status": "INCOMPLETE", "expected": None, "enumerated": 2, "reason": "READ_ERROR"}
        case = Case(self, cad, SCOPE_RULES)
        self.assertGreater(sum(1 for r in case.report["results"] if r["rule_id"] == "R-ATTR-LAYER" and r["handle"] == "40"), 0)
        self.assertDat(case.run())
        res = case.run(mut_report=lambda r: r["results"].remove(result_row(r, "R-ATTR-LAYER", "40")))
        self.assertKhongDat(res, ["PHAM_VI_LECH"], exact=False)
        self.assertEqual(self.scope_of(res, "R-ATTR-LAYER")["thieu_dong"], 1)

    def test_rule_with_no_object_in_scope_and_a_row_anyway(self):
        def extra(report):
            report["results"].append(dict(result_row(report, "R-ATTR-LAYER", "40"), rule_id="R-ATTR-NONE"))
            resync(report)
        res = self.case().run(mut_report=extra)
        self.assertKhongDat(res, ["PHAM_VI_LECH"], exact=False)
        self.assertEqual(self.scope_of(res, "R-ATTR-NONE")["thua_dong"], 1)

    def test_scope_mismatch_counts_in_so_muc_lech_and_output_names(self):
        res = Case.fixture(self).run(mut_report=drop("R-LAYER-NAME", "10"))
        rule = self.scope_of(res, "R-LAYER-NAME")
        for key in ("thieu_dong", "thua_dong", "pham_vi_khop", "so_doi_tuong_pham_vi_tinh_lai"):
            self.assertIn(key, rule)
        self.assertIn("verdict_dong_lech", res.out["buoc4_actual"])
        self.assertLess(kv.REASON_ORDER.index("ACTUAL_LECH"), kv.REASON_ORDER.index("DONG_VERDICT_LECH"))
        self.assertEqual(kv.REASON_ORDER.index("DONG_VERDICT_LECH") + 1, kv.REASON_ORDER.index("DONG_LY_DO_LECH"))
        self.assertEqual(kv.REASON_ORDER.index("PHAM_VI_LECH") + 1, kv.REASON_ORDER.index("COUNTS_LECH"))


# ---------------------------------------------------------------------------------------------------- output
class FilteredOutput(BaseTest):
    def test_output_has_no_layer_xref_block_handle_value_or_path(self):
        secrets = set()
        for inp in INPUTS:
            doc = read_json(fx(inp))
            for g in ("layers", "blocks", "block_refs", "attributes", "texts", "dimensions", "xrefs"):
                for obj in doc[g]:
                    secrets.add(obj["handle"])
                    for k in ("name", "block_name", "layer", "font", "tag", "value", "style", "dim_type"):
                        if isinstance(obj.get(k), str):
                            secrets.add(obj[k])
            secrets.add(doc["drawing"]["file_name"])
            secrets.add(doc["drawing"]["sha256"])        # hash của bản vẽ giả: không phải hash đầu vào, không có trong output
        secrets -= {"MODEL", "A", "STD", "TEXT", "LINEAR"}
        self.assertIn("XR-SITE", secrets)
        self.assertIn("wall_01", secrets)
        for inp, rules in itertools.product(INPUTS, RULES):
            with self.subTest(inp=inp, rules=rules):
                case = Case.fixture(self, inp, rules)
                res = case.run(extra=("--nguoi-chay", "ducdq", "--nguoi-duyet", "reviewer"))
                self.assertDat(res)
                tokens = set(re.findall(r'"([^"]*)"', res.text))
                for s in secrets:
                    self.assertNotIn(s, tokens, f"output has the string {s!r}")
                    if len(s) >= 5:
                        self.assertNotIn(s, res.text)
                for path_part in (case.root, os.path.dirname(case.root), "/tmp", "\\\\", "C:", "run1"):
                    self.assertNotIn(path_part.replace("\\", "\\\\"), res.text)
                self.assertNotRegex(res.text, r'"(actual|expected|handle|evidence_ids)"')
                self.assertNotIn("CADEV", res.text)
                self.assertNotIn(".json", res.text)
                self.assertNotIn(".yaml", res.text)

    def test_output_of_a_failure_with_all_stops_is_also_free_of_data(self):
        res = Case.fixture(self, "cad_read_fail.json").run(mut_report=lambda r: result_row(r, "R-LAYER-NAME", "14").update(actual="wall_02"))
        self.assertKhongDat(res, ["ACTUAL_LECH"])
        for s in ("wall_01", "wall_02", "XR-SITE", "comic.ttf", "FIXTURE-SAMPLE-01"):
            self.assertNotIn(s, res.text)

    def test_script_hash_labels_time_and_determinism(self):
        case = Case.fixture(self)
        a = case.run(extra=("--nguoi-chay", "ducdq", "--nguoi-duyet", "Opus"))
        b = case.run(extra=("--nguoi-chay", "ducdq", "--nguoi-duyet", "Opus"))
        raw = read_bytes(SCRIPT)
        self.assertEqual(a.out["script"]["sha256_tho"], sha(raw))
        self.assertEqual(a.out["script"]["sha256_lf"], sha(raw.replace(b"\r\n", b"\n")))
        self.assertIn("gateway.schema", a.out["script"]["schema_validator"])
        self.assertEqual((a.out["nguoi_chay"], a.out["nguoi_duyet"]), ("ducdq", "Opus"))
        self.assertRegex(a.out["chay_luc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$")
        self.assertEqual(a.out["schema"], "tvxd.m04b.kiem_truy_vet/v1")
        strip = lambda o: {k: v for k, v in o.items() if k != "chay_luc"}  # noqa: E731
        self.assertEqual(strip(a.out), strip(b.out))
        none = case.run()
        self.assertEqual((none.out["nguoi_chay"], none.out["nguoi_duyet"]), (None, None))

    def test_schema_hashes_are_those_of_the_schema_files(self):
        res = Case.fixture(self).run()
        for key, name in (("bao_cao", "cad_audit_report.v1.json"), ("cad_read", "cad_read.v1.json")):
            self.assertEqual(res.out["buoc2_schema"][key]["schema_sha256"],
                             sha(read_bytes(os.path.join(REPO, "cadaudit", "schemas", name))))


# ---------------------------------------------------------------------------------------------------- lỗi đầu vào, ghi tệp
class InputAndOutputFile(BaseTest):
    def test_existing_out_file_is_refused_and_left_unchanged(self):
        case = Case.fixture(self)
        first = case.run()
        before = read_bytes(os.path.join(first.dir, "out.json"))
        listing = sorted(os.listdir(first.dir))
        code, _, err = invoke(["--cad-read", os.path.join(first.dir, "cad_read.json"), "--rules", os.path.join(first.dir, "rules.yaml"),
                               "--report", os.path.join(first.dir, "report.json"),
                               "--sha256-cad-read", sha(read_bytes(os.path.join(first.dir, "cad_read.json"))),
                               "--sha256-rules", sha(read_bytes(os.path.join(first.dir, "rules.yaml"))),
                               "--sha256-report", sha(read_bytes(os.path.join(first.dir, "report.json"))),
                               "--out", os.path.join(first.dir, "out.json")])
        self.assertEqual(code, 2)
        self.assertIn("OUT_DA_TON_TAI", err)
        self.assertEqual(read_bytes(os.path.join(first.dir, "out.json")), before)
        self.assertEqual(sorted(os.listdir(first.dir)), listing)

    def test_out_that_is_an_existing_directory_or_dangling_link_is_refused(self):
        case = Case.fixture(self)
        base = case.run()
        paths = [os.path.join(base.dir, n) for n in ("cad_read.json", "rules.yaml", "report.json")]
        args = ["--cad-read", paths[0], "--rules", paths[1], "--report", paths[2],
                "--sha256-cad-read", sha(read_bytes(paths[0])), "--sha256-rules", sha(read_bytes(paths[1])),
                "--sha256-report", sha(read_bytes(paths[2]))]
        os.mkdir(os.path.join(base.dir, "adir"))
        self.assertEqual(invoke(args + ["--out", os.path.join(base.dir, "adir")])[0], 2)
        link = os.path.join(base.dir, "dangling.json")
        try:
            os.symlink(os.path.join(base.dir, "nowhere.json"), link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this machine")
        self.assertEqual(invoke(args + ["--out", link])[0], 2)
        self.assertFalse(os.path.exists(os.path.join(base.dir, "nowhere.json")))

    def test_missing_output_directory_and_inputs_are_input_errors(self):
        case = Case.fixture(self)
        base = case.run()
        paths = [os.path.join(base.dir, n) for n in ("cad_read.json", "rules.yaml", "report.json")]
        pins = ["--sha256-cad-read", sha(read_bytes(paths[0])), "--sha256-rules", sha(read_bytes(paths[1])),
                "--sha256-report", sha(read_bytes(paths[2]))]
        code, _, err = invoke(["--cad-read", paths[0], "--rules", paths[1], "--report", paths[2], *pins,
                               "--out", os.path.join(base.dir, "no-such-dir", "o.json")])
        self.assertEqual(code, 2)
        self.assertNotIn(base.dir, err)
        for i in range(3):
            moved = list(paths)
            moved[i] = os.path.join(base.dir, "missing.bin")
            out = os.path.join(base.dir, f"o{i}.json")
            code, _, err = invoke(["--cad-read", moved[0], "--rules", moved[1], "--report", moved[2], *pins, "--out", out])
            self.assertEqual(code, 2)
            self.assertFalse(os.path.exists(out))
            self.assertNotIn(base.dir, err)

    def test_input_that_is_not_json_or_yaml_is_exit_2_and_writes_nothing(self):
        cases = {"cad_read": b"{ not json", "bao_cao": b"\xff\xfe not utf-8", "quy_tac": b"rules: [unclosed"}
        for key, data in cases.items():
            with self.subTest(key):
                res = Case.fixture(self).run(raw={key: data})
                self.assertEqual(res.code, 2)
                self.assertIsNone(res.out)
                self.assertEqual(sorted(os.listdir(res.dir)), ["cad_read.json", "report.json", "rules.yaml"])
                self.assertNotIn(res.dir, res.stderr)

    def test_json_with_duplicate_keys_or_nan_is_an_input_error(self):
        case = Case.fixture(self)
        for key, data in (("cad_read", b'{"schema": 1, "schema": 2}'), ("bao_cao", b'{"x": NaN}'), ("bao_cao", b'{"x": 1e999}')):
            with self.subTest(key=key, data=data):
                res = case.run(raw={key: data})
                self.assertEqual((res.code, res.out), (2, None))

    def test_rules_file_with_the_wrong_shape_is_an_input_error(self):
        for data in (b"- a\n- b\n", b"rules: 3\n", b"rules:\n  - id: 5\n", b"rules:\n  - {id: R-A, applies_to: nope, check: {type: x}, status: s}\n"):
            with self.subTest(data=data):
                res = Case.fixture(self).run(raw={"quy_tac": data})
                self.assertEqual((res.code, res.out), (2, None))

    def test_bad_arguments_are_exit_2(self):
        self.assertEqual(invoke([])[0], 2)
        case = Case.fixture(self)
        base = case.run()
        p = [os.path.join(base.dir, n) for n in ("cad_read.json", "rules.yaml", "report.json")]
        common = ["--cad-read", p[0], "--rules", p[1], "--report", p[2], "--out", os.path.join(base.dir, "x.json")]
        for pins in (["--sha256-cad-read", "abc", "--sha256-rules", "0" * 64, "--sha256-report", "0" * 64],
                     ["--sha256-cad-read", "0" * 64, "--sha256-rules", "g" * 64, "--sha256-report", "0" * 64],
                     ["--sha256-cad-read", "0" * 64, "--sha256-rules", "0" * 64]):
            self.assertEqual(invoke(common + pins)[0], 2)
        good = ["--sha256-cad-read", "0" * 64, "--sha256-rules", "0" * 64, "--sha256-report", "0" * 64]
        self.assertEqual(invoke(common + good + ["--nguoi-chay", "a\nb"])[0], 2)
        self.assertEqual(invoke(common + good + ["--nguoi-duyet", "x" * 201])[0], 2)
        self.assertEqual(invoke(common + good + ["--unknown"])[0], 2)
        self.assertFalse(os.path.exists(os.path.join(base.dir, "x.json")))

    def test_internal_error_is_exit_70_and_not_confused_with_khong_dat(self):
        original = kv.step3
        kv.step3 = lambda *a, **k: 1 / 0
        self.addCleanup(setattr, kv, "step3", original)
        res = Case.fixture(self).run()
        self.assertEqual((res.code, res.out), (70, None))
        self.assertIn("ZeroDivisionError", res.stderr)

    def test_no_file_other_than_out_is_created(self):
        res = Case.fixture(self, "cad_read_fail.json", "rules_standard.yaml").run()
        self.assertEqual(sorted(os.listdir(res.dir)), ["cad_read.json", "out.json", "report.json", "rules.yaml"])

    def test_inputs_are_not_modified(self):
        case = Case.fixture(self)
        res = case.run()
        before = {n: read_bytes(os.path.join(res.dir, n)) for n in ("cad_read.json", "rules.yaml", "report.json")}
        invoke(["--cad-read", os.path.join(res.dir, "cad_read.json"), "--rules", os.path.join(res.dir, "rules.yaml"),
                "--report", os.path.join(res.dir, "report.json"), "--sha256-cad-read", sha(before["cad_read.json"]),
                "--sha256-rules", sha(before["rules.yaml"]), "--sha256-report", sha(before["report.json"]),
                "--out", os.path.join(res.dir, "second.json")])
        self.assertEqual(before, {n: read_bytes(os.path.join(res.dir, n)) for n in before})

    def test_subprocess_exit_codes(self):
        """Chạy như người dùng: python scripts/m04b/kiem_truy_vet.py. 0 = DAT, 1 = KHONG_DAT, 2 = lỗi đầu vào."""
        case = Case.fixture(self, "cad_read_fail.json")
        ok = case.run()
        paths = [os.path.join(ok.dir, n) for n in ("cad_read.json", "rules.yaml", "report.json")]
        pins = [sha(read_bytes(p)) for p in paths]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

        def go(out, pin_cad=None):
            return subprocess.run([sys.executable, SCRIPT, "--cad-read", paths[0], "--rules", paths[1], "--report", paths[2],
                                   "--sha256-cad-read", pin_cad or pins[0], "--sha256-rules", pins[1], "--sha256-report", pins[2],
                                   "--out", os.path.join(ok.dir, out)], capture_output=True, text=True, env=env, cwd=ok.dir)
        r = go("p0.json")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "kiem_truy_vet: ket_luan=DAT"))
        r = go("p1.json", pin_cad="0" * 64)
        self.assertEqual((r.returncode, r.stdout.strip()), (1, "kiem_truy_vet: ket_luan=KHONG_DAT ly_do=SHA256_CAD_READ_SAI"))
        r = go("p0.json")                      # đã có
        self.assertEqual(r.returncode, 2)
        self.assertEqual(sorted(os.listdir(ok.dir)), ["cad_read.json", "out.json", "p0.json", "p1.json", "report.json", "rules.yaml"])


# ---------------------------------------------------------------------------------------------------- bộ giải độc lập
class ResolverAgreesWithTheHelper(unittest.TestCase):
    def test_same_answer_as_resolve_evidence_on_every_fixture_id_and_on_crafted_ids(self):
        crafted = ["CADEV:F01:10:name", "CADEV:F01:10:nope", "CADEV:F01:ZZ:name", "CADEV:F02:10:name", "CADEV:F01:FILE:units.insunits",
                   "CADEV:F01:FILE:units.nothing", "CADEV:F01:FILE:coverage.layers.status", "CADEV:F01:FILE:drawing.read_mode",
                   "CADEV:F01:FILE:coverage.nothing.status", "CADEV:F01:FILE:drawing", "CADEV:F01:FILE:units",
                   "CADEV:F01:10:name\n", "cadev:F01:10:name", "CADEV:F01:10", "CADEV:F01:a0:name", "CADEV::10:name", "", "x"]
        for inp in INPUTS:
            doc = read_json(fx(inp))
            rs = kv.Resolver(doc)
            ids = list(crafted)
            for rules in RULES:
                rep = run_audit(read_bytes(fx(inp)), read_bytes(fx(rules)), TS)
                ids += [ev for x in rep["rules"] + rep["results"] for ev in x["evidence_ids"]]
            for ev in ids:
                with self.subTest(inp=inp, ev=ev):
                    expected_one = len(resolve_evidence(doc, ev)) == 1 and not isinstance(resolve_evidence(doc, ev)[0], (dict, list))
                    self.assertEqual(rs.classify(ev) == "giai_dung_mot", expected_one)

    def test_classification_names(self):
        rs = kv.Resolver(read_json(fx("cad_read_pass.json")))
        self.assertEqual(rs.classify("CADEV:F01:10:name"), "giai_dung_mot")
        self.assertEqual(rs.classify("CADEV:F01:10:name\n"), "sai_dang")
        self.assertEqual(rs.classify("CADEV:F01:a0:name"), "sai_dang")
        self.assertEqual(rs.classify(None), "sai_dang")
        self.assertEqual(rs.classify(5), "sai_dang")
        self.assertEqual(rs.classify("CADEV:F02:10:name"), "sai_file_id")
        self.assertEqual(rs.classify("CADEV:F01:99:name"), "khong_giai_duoc")
        self.assertEqual(rs.classify("CADEV:F01:FILE:coverage.layers"), "khong_giai_duoc")
        self.assertEqual(rs.single("CADEV:F01:10:name"), (True, "A-WALL"))
        self.assertEqual(rs.single("CADEV:F01:FILE:units.measurement"), (True, 1))
        self.assertEqual(rs.single("CADEV:F01:99:name"), (False, None))

    def test_a_null_value_is_one_value(self):
        rs = kv.Resolver(read_json(fx("cad_read_unknown.json")))
        self.assertEqual(rs.classify("CADEV:F01:50:font"), "giai_dung_mot")
        self.assertEqual(rs.single("CADEV:F01:50:font"), (True, None))


# ---------------------------------------------------------------------------------------------------- kiểm soát tĩnh
class StaticControls(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(read_bytes(SCRIPT).decode("utf-8"))

    def test_the_script_does_not_import_cadaudit(self):
        mods = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
        self.assertFalse([m for m in mods if m.split(".")[0] == "cadaudit"], mods)
        self.assertIn("gateway", {m.split(".")[0] for m in mods})
        self.assertEqual({m.split(".")[0] for m in mods} - {"argparse", "collections", "datetime", "hashlib", "json", "os", "re", "sys", "yaml", "gateway"}, set())

    def test_the_only_open_modes_are_read_and_exclusive_create(self):
        modes = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
                self.assertIsInstance(mode, ast.Constant, "open() needs a literal mode")
                modes.add(mode.value)
        self.assertEqual(modes, {"rb", "xb"})

    def test_no_other_way_to_write_delete_or_run(self):
        banned_attrs = {"remove", "unlink", "rmdir", "rename", "write_text", "write_bytes", "system", "popen", "makedirs",
                        "mkdir", "chmod", "symlink", "link", "rmtree", "copyfile", "move", "dump", "safe_dump"}
        banned_names = {"eval", "exec", "compile", "__import__", "subprocess"}
        found = [n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute) and n.attr in banned_attrs]
        found += [n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name) and n.id in banned_names]
        self.assertEqual(found, [])
        # `data.replace(b"\r\n", b"\n")` (chuẩn hóa xuống dòng trước khi băm) là phương thức của bytes; os.replace thì cấm.
        os_replace = [n for n in ast.walk(self.tree) if isinstance(n, ast.Attribute) and n.attr == "replace"
                      and isinstance(n.value, ast.Name) and n.value.id == "os"]
        self.assertEqual(os_replace, [])

    def test_yaml_is_read_with_safe_load_only(self):
        calls = [n.func.attr for n in ast.walk(self.tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == "yaml"]
        self.assertEqual(calls, ["safe_load"])


if __name__ == "__main__":
    unittest.main()
