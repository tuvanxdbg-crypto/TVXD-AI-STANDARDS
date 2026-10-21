"""M04-B: tests của scripts/m04b/tom_tat.py (docs/M04_B_PLAN.md mục 5, "Bản tóm tắt"). Chỉ dữ liệu giả (fixture), offline.

Mỗi bộ dữ liệu (stage) nằm trong một thư mục tạm riêng và bị xóa sau mỗi ca: CAD_READ fixture, tệp quy tắc fixture,
báo cáo do pipeline `cadaudit` thật tạo ra, và output thật của `kiem_truy_vet.main` (G7). Các ca lỗi sửa MỘT chỗ rồi
tính lại hash cho khớp, nên chỉ đúng kiểm đầu vào cần thử mới bắt được.
"""
import ast
import contextlib
import copy
import hashlib
import io
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
from m04_helpers import REPO, check_args, fx, read_bytes, read_json, run_cli

SCRIPT_DIR = os.path.join(REPO, "scripts", "m04b")
SCRIPT = os.path.join(SCRIPT_DIR, "tom_tat.py")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import kiem_truy_vet as kv  # noqa: E402
import tom_tat as tt  # noqa: E402

TS = "2026-10-19T10:00:00+07:00"
GIT_SHA = "9f11076" + "0" * 33
INPUTS = ("cad_read_pass.json", "cad_read_fail.json", "cad_read_unknown.json")
RULES = ("rules_internal.yaml", "rules_standard.yaml")
KEYS = ("cad_read", "quy_tac", "bao_cao")

TOP_KEYS = {"schema", "sha256", "cadaudit_sha", "cadaudit_version", "report_schema", "rules_version", "overall",
            "all_rules_approved", "overall_note", "rules_by_verdict", "rules_by_status", "results_by_verdict", "quy_tac",
            "coverage", "kiem_truy_vet", "script", "tao_luc"}
RULE_KEYS = {"rule_id", "rule_status", "classification", "verdict", "reasons", "counts", "objects_in_scope",
             "coverage_complete"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dumps(doc) -> bytes:
    return json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8")


def invoke(module, args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main([str(a) for a in args])
    return code, out.getvalue(), err.getvalue()


def all_strings(node, keys=True):
    """Mọi chuỗi trong một tài liệu JSON: giá trị, và khóa nếu `keys`."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            if keys:
                yield k
            yield from all_strings(v, keys)
    elif isinstance(node, list):
        for v in node:
            yield from all_strings(v, keys)


class Result:
    def __init__(self, code, stdout, stderr, out_path):
        self.code, self.stdout, self.stderr, self.out_path = code, stdout, stderr, out_path
        self.text = self.doc = None
        if os.path.isfile(out_path):
            self.text = read_bytes(out_path).decode("utf-8")
            try:
                self.doc = json.loads(self.text)
            except ValueError:          # tệp có sẵn của test (không phải output của script)
                self.doc = None


class Stage:
    """Một bộ bốn tệp đầu vào đã ghim hash, trong một thư mục tạm."""

    def __init__(self, pipe, d, cad, report, files, kvt, kvt_code):
        self.pipe, self.dir, self.cad, self.report, self.files, self.kvt, self.kvt_code = pipe, d, cad, report, files, kvt, kvt_code
        self.paths = {"cad_read": os.path.join(d, "cad_read.json"), "quy_tac": os.path.join(d, "rules.yaml"),
                      "bao_cao": os.path.join(d, "report.json"), "kiem_truy_vet": os.path.join(d, "kvt.json")}
        for k, p in self.paths.items():
            with open(p, "wb") as f:
                f.write(files[k])
        self.pins = {k: sha(files[k]) for k in KEYS}

    def args(self, **over):
        a = {"cad_read": self.paths["cad_read"], "rules": self.paths["quy_tac"], "report": self.paths["bao_cao"],
             "kiem_truy_vet": self.paths["kiem_truy_vet"], "sha256_cad_read": self.pins["cad_read"],
             "sha256_rules": self.pins["quy_tac"], "sha256_report": self.pins["bao_cao"], "cadaudit_sha": GIT_SHA,
             "out": os.path.join(self.dir, "tom_tat.json")}
        a.update(over)
        argv = []
        for k, v in a.items():
            argv += ["--" + k.replace("_", "-"), v]
        return argv

    def run(self, **over) -> Result:
        argv = self.args(**over)
        out_path = argv[argv.index("--out") + 1]
        return Result(*invoke(tt, argv), out_path)

    def listing(self):
        return sorted(os.listdir(self.dir))


class Pipeline:
    """Dựng các stage. Một stage gồm CAD_READ, quy tắc, báo cáo (do `run_audit` của cadaudit tạo), kiểm truy vết.

    `report_fn` và `cad_post` sửa báo cáo hoặc CAD_READ SAU khi báo cáo được tạo; hash và liên kết được tính lại. Tệp
    kiểm truy vết chỉ được chạy lại thật khi `rerun_kvt`; không thì lấy bản của dữ liệu sạch rồi vá ba hash, để một
    ca lỗi kiểu dữ liệu không bị G7 chặn trước khi tới `tom_tat`. `raw` thay nguyên byte của một tệp."""

    def __init__(self, tc: unittest.TestCase, inp="cad_read_pass.json", rules="rules_internal.yaml", cad_pre=None):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="m04b-tt-"))
        tc.addCleanup(shutil.rmtree, self.root, True)
        self.cad_doc = read_json(fx(inp))
        if cad_pre:
            cad_pre(self.cad_doc)
        self.rules_bytes = read_bytes(fx(rules))
        self.n = 0
        self.base = self.stage(rerun_kvt=True)
        assert self.base.kvt_code == 0, self.base.kvt_code
        self.base_kvt = copy.deepcopy(self.base.kvt)

    def stage(self, cad_post=None, report_fn=None, rules=None, rerun_kvt=False, kvt_fn=None, raw=None):
        raw = raw or {}
        self.n += 1
        d = os.path.join(self.root, f"s{self.n}")
        os.mkdir(d)
        real_rules = self.rules_bytes if rules is None else rules
        report = run_audit(dumps(self.cad_doc), real_rules, TS)
        rules_bytes = raw.get("quy_tac", real_rules)
        cad = copy.deepcopy(self.cad_doc)
        if cad_post:
            cad_post(cad)
        cad_bytes = raw.get("cad_read", dumps(cad))
        report["input"]["input_sha256"] = sha(cad_bytes)
        report["rules_file"]["sha256"] = sha(rules_bytes)
        if report_fn:
            report_fn(report)
        files = {"cad_read": cad_bytes, "quy_tac": rules_bytes, "bao_cao": raw.get("bao_cao", dumps(report))}
        hashes = {k: sha(files[k]) for k in KEYS}
        if rerun_kvt:
            tmp = os.path.join(d, "kvt-run.json")
            paths = {}
            for k, name in (("cad_read", "c.bin"), ("quy_tac", "r.bin"), ("bao_cao", "b.bin")):
                paths[k] = os.path.join(d, name)
                with open(paths[k], "wb") as f:
                    f.write(files[k])
            code, _, _ = invoke(kv, ["--cad-read", paths["cad_read"], "--rules", paths["quy_tac"], "--report", paths["bao_cao"],
                                     "--sha256-cad-read", hashes["cad_read"], "--sha256-rules", hashes["quy_tac"],
                                     "--sha256-report", hashes["bao_cao"], "--out", tmp])
            kvt = json.loads(read_bytes(tmp).decode("utf-8"))
            for p in (*paths.values(), tmp):
                os.remove(p)
        else:
            code, kvt = None, copy.deepcopy(self.base_kvt)
            for k in KEYS:
                kvt["sha256"][k]["tinh_duoc"] = kvt["sha256"][k]["ghim"] = hashes[k]
        if kvt_fn:
            kvt_fn(kvt)
        files["kiem_truy_vet"] = raw.get("kiem_truy_vet", dumps(kvt))
        return Stage(self, d, cad, report, files, kvt, code)


class Base(unittest.TestCase):
    def pipe(self) -> Pipeline:
        """Pipeline mặc định (fixture pass + rules_internal), dựng một lần cho mỗi ca test."""
        if not hasattr(self, "_pipe"):
            self._pipe = Pipeline(self)
        return self._pipe

    def assertWrote(self, res):
        self.assertEqual((res.code, res.stderr), (0, ""), res.stderr)
        self.assertIsNotNone(res.doc)

    def assertRefused(self, st, res, code=None, before=None):
        """exit 2, không tạo tệp, thông điệp không có đường dẫn; `code` (nếu có) là mã lỗi dự kiến."""
        self.assertEqual(res.code, 2, res.stderr)
        self.assertIsNone(res.doc)
        self.assertFalse(os.path.exists(res.out_path))
        self.assertEqual(res.stdout, "")
        self.assertEqual(st.listing(), before if before is not None else sorted(["cad_read.json", "rules.yaml", "report.json", "kvt.json"]))
        for part in (st.dir, st.pipe.root, "/tmp", "\\\\"):
            self.assertNotIn(part, res.stderr)
        if code:
            self.assertIn(code, res.stderr)


# ---------------------------------------------------------------------------------------------------- ca tốt
class Good(Base):
    def test_every_fixture_pair_gives_the_exact_shape_and_values(self):
        for inp, rules in [(i, r) for i in INPUTS for r in RULES]:
            with self.subTest(inp=inp, rules=rules):
                pipe = Pipeline(self, inp, rules)
                st = pipe.base
                res = st.run()
                self.assertWrote(res)
                o = res.doc
                self.assertEqual(set(o), TOP_KEYS)
                self.assertEqual(o["schema"], "tvxd.m04b.tom_tat/v1")
                self.assertEqual(set(o["sha256"]), {"cad_read", "quy_tac", "bao_cao", "kiem_truy_vet"})
                self.assertEqual(o["sha256"], {"cad_read": sha(st.files["cad_read"]), "quy_tac": sha(read_bytes(fx(rules))),
                                               "bao_cao": sha(st.files["bao_cao"]), "kiem_truy_vet": sha(st.files["kiem_truy_vet"])})
                self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", v) for v in o["sha256"].values()))
                self.assertEqual(o["cadaudit_sha"], GIT_SHA)
                rep = st.report
                self.assertEqual((o["cadaudit_version"], o["report_schema"], o["rules_version"]),
                                 (rep["cadaudit_version"], rep["schema"], rep["rules_file"]["rules_version"]))
                sm = rep["summary"]
                self.assertEqual((o["overall"], o["all_rules_approved"], o["overall_note"]),
                                 (sm["overall"], sm["all_rules_approved"], sm.get("overall_note")))
                for k in ("rules_by_verdict", "rules_by_status", "results_by_verdict"):
                    self.assertEqual(o[k], sm[k])
                self.assertEqual(len(o["quy_tac"]), len(rep["rules"]))
                for got, want in zip(o["quy_tac"], rep["rules"]):
                    self.assertEqual(set(got), RULE_KEYS)
                    self.assertEqual(got, {k: want[k] for k in RULE_KEYS})
                self.assertEqual(set(o["coverage"]), {"layers", "xrefs"})
                for g in ("layers", "xrefs"):
                    c = st.cad["coverage"][g]
                    self.assertEqual(set(o["coverage"][g]), {"status", "expected", "enumerated", "reason"})
                    self.assertEqual(o["coverage"][g], {k: c[k] for k in ("status", "expected", "enumerated", "reason")})
                self.assertEqual(set(o["kiem_truy_vet"]), {"ket_luan", "ly_do_khong_dat", "script_sha256_lf"})
                self.assertEqual(o["kiem_truy_vet"], {"ket_luan": "DAT", "ly_do_khong_dat": [],
                                                      "script_sha256_lf": st.kvt["script"]["sha256_lf"]})
                self.assertEqual(set(o["script"]), {"sha256_tho", "sha256_lf"})
                self.assertRegex(o["tao_luc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$")
                self.assertEqual(res.stdout.strip(), f"tom_tat: da ghi; overall={o['overall']} kiem_truy_vet=DAT")
                self.assertEqual(st.listing(), ["cad_read.json", "kvt.json", "report.json", "rules.yaml", "tom_tat.json"])

    def test_values_differ_per_fixture_and_follow_the_report(self):
        """Kiểm chéo: các fixture cho tóm tắt khác nhau, và các giá trị đến từ báo cáo/CAD_READ chứ không cố định."""
        seen = {}
        for inp in INPUTS:
            res = Pipeline(self, inp).base.run()
            self.assertWrote(res)
            seen[inp] = (res.doc["overall"], tuple(r["verdict"] for r in res.doc["quy_tac"]), res.doc["coverage"]["layers"]["status"])
        self.assertEqual(seen["cad_read_fail.json"][0], "HAS_FAIL")
        self.assertEqual(seen["cad_read_unknown.json"][2], "INCOMPLETE")
        self.assertEqual(len(set(seen.values())), 3)

    def test_the_incomplete_coverage_fixture_is_copied_with_its_enum_reason_and_without_the_note(self):
        res = Pipeline(self, "cad_read_unknown.json").base.run()
        self.assertWrote(res)
        self.assertEqual(res.doc["coverage"], {
            "layers": {"status": "INCOMPLETE", "expected": 5, "enumerated": 4, "reason": "READ_ERROR"},
            "xrefs": {"status": "INCOMPLETE", "expected": None, "enumerated": 1, "reason": "XREF_DEPENDENT"}})
        self.assertNotIn("fake: one layer record unreadable", res.text)

    def test_uppercase_pins_and_sha_are_normalised_to_lower_case(self):
        st = Pipeline(self).base
        res = st.run(sha256_cad_read=st.pins["cad_read"].upper(), sha256_rules=st.pins["quy_tac"].upper(),
                     sha256_report=st.pins["bao_cao"].upper(), cadaudit_sha=GIT_SHA.upper())
        self.assertWrote(res)
        self.assertEqual(res.doc["cadaudit_sha"], GIT_SHA)
        self.assertEqual(res.doc["sha256"]["cad_read"], st.pins["cad_read"])

    def test_the_real_cli_report_writer_and_g7_output_feed_the_summary(self):
        """Đường thật: `cadaudit check` ghi báo cáo bằng bộ ghi của nó, G7 kiểm đúng tệp đó, rồi tóm tắt."""
        w = m04_helpers.World("cad_read_unknown.json", "rules_internal.yaml")
        self.addCleanup(w.cleanup)
        self.assertEqual(run_cli(*check_args(w.input, w.rules, w.out("report.json")))[0], 0)
        p = {k: sha(read_bytes(v)) for k, v in (("cad", w.input), ("rules", w.rules), ("report", w.out("report.json")))}
        kvt = w.out("kvt.json")
        code, _, _ = invoke(kv, ["--cad-read", w.input, "--rules", w.rules, "--report", w.out("report.json"),
                                 "--sha256-cad-read", p["cad"], "--sha256-rules", p["rules"], "--sha256-report", p["report"], "--out", kvt])
        self.assertEqual(code, 0)
        out = w.out("tom-tat.json")
        code, stdout, err = invoke(tt, ["--cad-read", w.input, "--rules", w.rules, "--report", w.out("report.json"), "--kiem-truy-vet", kvt,
                                        "--sha256-cad-read", p["cad"], "--sha256-rules", p["rules"], "--sha256-report", p["report"],
                                        "--cadaudit-sha", GIT_SHA, "--out", out])
        self.assertEqual((code, err), (0, ""))
        doc = json.loads(read_bytes(out))
        self.assertEqual(doc["sha256"]["kiem_truy_vet"], sha(read_bytes(kvt)))
        self.assertEqual(doc["kiem_truy_vet"]["ket_luan"], "DAT")
        self.assertEqual(doc["overall"], read_json(w.out("report.json"))["summary"]["overall"])

    def test_deterministic_except_for_the_time(self):
        st = Pipeline(self).base
        a = st.run(out=os.path.join(st.dir, "a.json"))
        b = st.run(out=os.path.join(st.dir, "b.json"))
        strip = lambda o: {k: v for k, v in o.items() if k != "tao_luc"}  # noqa: E731
        self.assertEqual(strip(a.doc), strip(b.doc))

    def test_script_hashes_are_those_of_the_script_file(self):
        res = Pipeline(self).base.run()
        raw = read_bytes(SCRIPT)
        self.assertEqual(res.doc["script"], {"sha256_tho": sha(raw), "sha256_lf": sha(raw.replace(b"\r\n", b"\n"))})

    def test_lf_hash_ignores_crlf_checkouts(self):
        """Checkout Windows có thể đổi LF thành CRLF: `sha256_lf` phải như nhau, `sha256_tho` thì khác."""
        lf, crlf = tt.script_hashes(b"a\nb\nc\n"), tt.script_hashes(b"a\r\nb\r\nc\r\n")
        self.assertEqual(lf["sha256_lf"], crlf["sha256_lf"])
        self.assertNotEqual(lf["sha256_tho"], crlf["sha256_tho"])
        self.assertEqual(lf["sha256_lf"], sha(b"a\nb\nc\n"))

    def test_inputs_are_not_modified_and_only_out_is_created(self):
        st = Pipeline(self).base
        before = {k: read_bytes(p) for k, p in st.paths.items()}
        self.assertWrote(st.run())
        self.assertEqual(before, {k: read_bytes(p) for k, p in st.paths.items()})
        self.assertEqual(st.listing(), ["cad_read.json", "kvt.json", "report.json", "rules.yaml", "tom_tat.json"])

    def test_subprocess_run_like_a_user(self):
        st = Pipeline(self).base
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        argv = st.args()
        r = subprocess.run([sys.executable, "-I", SCRIPT, *argv], capture_output=True, text=True, env=env, cwd=st.dir)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertTrue(r.stdout.startswith("tom_tat: da ghi; overall="))
        r = subprocess.run([sys.executable, "-I", SCRIPT, *argv], capture_output=True, text=True, env=env, cwd=st.dir)
        self.assertEqual(r.returncode, 2)
        self.assertIn("OUT_DA_TON_TAI", r.stderr)


# ---------------------------------------------------------------------------------------------------- rò rỉ
SENTINELS = ("SENTINEL-DRAWING-NAME.dwg", "SENTFILEID99", "A-SENTINELLAYER", "XR-SENTINELXREF", "SENTINEL-NOTE-LAYERS",
             "SENTINEL-NOTE-XREFS", "SENTINEL-TEXT-VALUE", "SENTINEL-ATTR-VALUE", "SENTINEL-BLOCK", "SENTINEL-STYLE")
# Chuỗi chung có thể trùng với một enum hợp lệ trong output nên không đưa vào danh sách "lọt".
GENERIC = {"MODEL", "A", "STD", "TEXT", "LINEAR", "RESOLVED", "Continuous", "FILE", "READ_ERROR", "XREF_DEPENDENT"}


def plant(doc):
    doc["drawing"]["file_name"] = SENTINELS[0]
    doc["drawing"]["file_id"] = SENTINELS[1]
    doc["layers"][0]["name"] = SENTINELS[2]
    doc["xrefs"][0]["name"] = SENTINELS[3]
    doc["coverage"]["layers"]["note"] = SENTINELS[4]
    doc["coverage"]["xrefs"]["note"] = SENTINELS[5]
    doc["texts"][0]["value"] = SENTINELS[6]
    doc["attributes"][0]["value"] = SENTINELS[7]
    doc["blocks"][0]["name"] = SENTINELS[8]
    doc["texts"][0]["style"] = SENTINELS[9]


def drawing_strings(doc):
    out = set()
    for k in ("drawing", "layers", "blocks", "block_refs", "attributes", "texts", "dimensions", "xrefs"):
        out |= set(all_strings(doc[k], keys=False))
    for c in doc["coverage"].values():
        if isinstance(c.get("note"), str):
            out.add(c["note"])
    return out


class NoLeak(Base):
    def check_output(self, st, res, extra=()):
        self.assertWrote(res)
        tokens = set(all_strings(res.doc))
        secrets = (drawing_strings(st.cad) | set(extra) | set(SENTINELS)) - GENERIC
        for s in secrets:
            self.assertNotIn(s, tokens, f"the output has the string {s!r}")
            if len(s) >= 8:
                self.assertNotIn(s, res.text)
        for part in (st.dir, st.pipe.root, "/tmp", "\\\\", "C:", ".json", ".yaml", ".dwg"):
            self.assertNotIn(part, res.text)
        for word in ("CADEV", "evidence_ids", '"handle"', '"actual"', '"drawing"', "file_name", "file_id",
                     "dwg_sha256", "standard_hint", "reads_groups", '"note"', '"results"', "extracted_at"):
            self.assertNotIn(word, res.text)
        self.assertNotIn(st.cad["drawing"]["sha256"], res.text)             # hash DWG: không phải hash tệp nào đưa vào
        self.assertNotIn(st.report["input"]["dwg_sha256"], res.text)

    def test_nothing_from_the_drawing_report_rows_or_paths_leaks(self):
        for inp, rules in [(i, r) for i in INPUTS for r in RULES]:
            with self.subTest(inp=inp, rules=rules):
                pipe = Pipeline(self, inp, rules, cad_pre=plant if inp == "cad_read_pass.json" else None)
                st = pipe.base
                self.check_output(st, st.run())

    def test_planted_strings_in_every_free_text_place_of_the_report_do_not_leak(self):
        """Báo cáo bị cài chuỗi gác vào title, standard_hint, evidence_ids, actual, expected: bản tóm tắt không đọc chúng."""
        planted = ("SENTINEL-TITLE", "SENTINEL-HINT", "SENTINEL-ACTUAL", "SENTINEL-EXPECTED", "SENTINEL-EXTRA-KEY")

        def fn(report):
            report["rules"][0]["title"] = planted[0]
            report["rules"][0]["standard_hint"] = planted[1]
            report["rules"][0]["evidence_ids"].append("CADEV:F01:FILE:SENTINEL-EVIDENCE")
            row = report["results"][0]
            row["actual"], row["expected"] = planted[2], planted[3]
            row["evidence_ids"].append("CADEV:F01:FILE:SENTINEL-ROW-EVIDENCE")
        st = Pipeline(self, "cad_read_fail.json").stage(report_fn=fn)
        res = st.run()
        self.check_output(st, res, extra=planted + ("SENTINEL-EVIDENCE", "SENTINEL-ROW-EVIDENCE", "wall_01", "comic.ttf"))
        for s in ("SENTINEL-EVIDENCE", "SENTINEL-ROW-EVIDENCE"):
            self.assertNotIn(s, res.text)

    def test_the_fail_fixture_names_do_not_leak(self):
        st = Pipeline(self, "cad_read_fail.json").base
        res = st.run()
        self.check_output(st, res)
        for s in ("wall_01", "comic.ttf", "XR-SITE", "FIXTURE-SAMPLE-01", "GHI CHU", "DOOR-900", "TITLEBLOCK", "A-ANNO-TEXT"):
            self.assertNotIn(s, res.text)

    def test_free_text_in_an_enum_place_is_refused_instead_of_copied(self):
        for label, st in (
                ("coverage.reason", self.pipe().stage(cad_post=lambda c: c["coverage"]["layers"].update(reason="SENTINEL-REASON"))),
                ("coverage.status", self.pipe().stage(cad_post=lambda c: c["coverage"]["xrefs"].update(status="SENTINEL-STATUS"))),
                ("rule reason", self.pipe().stage(report_fn=lambda r: r["rules"][0]["reasons"].append("SENTINEL-RULE-REASON"))),
                ("rule status", self.pipe().stage(report_fn=lambda r: r["rules"][0].update(rule_status="SENTINEL-RULE-STATUS"))),
                ("overall", self.pipe().stage(report_fn=lambda r: r["summary"].update(overall="SENTINEL-OVERALL"))),
                ("overall_note", self.pipe().stage(report_fn=lambda r: r["summary"].update(overall_note="SENTINEL-NOTE")))):
            with self.subTest(label):
                res = st.run()
                self.assertRefused(st, res)
                self.assertNotIn("SENTINEL", res.stderr)


# ---------------------------------------------------------------------------------------------------- G7 KHONG_DAT
class G7NotPassed(Base):
    def test_a_khong_dat_check_is_summarised_with_its_exact_conclusion(self):
        def tamper(report):
            report["rules"][0]["counts"]["PASS"] += 1
        st = self.pipe().stage(report_fn=tamper, rerun_kvt=True)
        self.assertEqual((st.kvt_code, st.kvt["ket_luan"]), (1, "KHONG_DAT"))
        self.assertEqual(st.kvt["buoc_da_chay"], ["1", "2", "3", "4", "5", "6", "7"])
        self.assertIn("COUNTS_LECH", st.kvt["ly_do_khong_dat"])
        res = st.run()
        self.assertWrote(res)
        self.assertEqual(res.doc["kiem_truy_vet"], {"ket_luan": "KHONG_DAT", "ly_do_khong_dat": st.kvt["ly_do_khong_dat"],
                                                    "script_sha256_lf": st.kvt["script"]["sha256_lf"]})
        self.assertEqual(res.doc["kiem_truy_vet"]["ly_do_khong_dat"][0], "COUNTS_LECH")
        self.assertEqual(res.doc["sha256"]["bao_cao"], sha(st.files["bao_cao"]))     # hash ghim lại khớp báo cáo đã sửa
        self.assertEqual(res.doc["quy_tac"][0]["counts"], st.report["rules"][0]["counts"])

    def test_several_reasons_keep_the_order_of_the_check(self):
        def tamper(report):
            report["rules"][0]["verdict"] = "FAIL"
            report["summary"]["overall"] = "HAS_FAIL"
        st = self.pipe().stage(report_fn=tamper, rerun_kvt=True)
        self.assertEqual(st.kvt["ket_luan"], "KHONG_DAT")
        self.assertGreaterEqual(len(st.kvt["ly_do_khong_dat"]), 2)
        res = st.run()
        self.assertWrote(res)
        self.assertEqual(res.doc["kiem_truy_vet"]["ly_do_khong_dat"], st.kvt["ly_do_khong_dat"])

    def test_a_check_that_stopped_early_is_refused(self):
        """G7 dừng ở bước 1 (sai hash ghim): `buoc_da_chay` chỉ có "1". Hash tính được vẫn khớp, nhưng không đủ bảy bước."""
        pipe = Pipeline(self)
        probe = pipe.stage()
        early_path = os.path.join(probe.dir, "early.json")
        code, _, _ = invoke(kv, ["--cad-read", probe.paths["cad_read"], "--rules", probe.paths["quy_tac"],
                                 "--report", probe.paths["bao_cao"], "--sha256-cad-read", probe.pins["cad_read"],
                                 "--sha256-rules", probe.pins["quy_tac"], "--sha256-report", "0" * 64, "--out", early_path])
        self.assertEqual(code, 1)
        early = json.loads(read_bytes(early_path))
        self.assertEqual((early["ket_luan"], early["buoc_da_chay"]), ("KHONG_DAT", ["1"]))
        st = pipe.stage(raw={"kiem_truy_vet": dumps(early)})
        self.assertEqual({k: v["tinh_duoc"] for k, v in early["sha256"].items()}, st.pins)   # chỉ thiếu bước, hash vẫn khớp
        self.assertRefused(st, st.run(), "KIEM_TRUY_VET_THIEU_BUOC")


# ---------------------------------------------------------------------------------------------------- rule_id lạ
class OddRuleIds(Base):
    def test_odd_rule_ids_are_replaced_by_their_index(self):
        odd = ["bad id/with slash", "lower-case", "A", "X" * 65, "A\n", "", "wall_01-name", "-START", "9START", "ok_ID-1",
               "Ab", "R-OK_1", "AB", "A" + "B" * 63]

        def fn(report):
            base = report["rules"][0]
            report["rules"] = [dict(copy.deepcopy(base), rule_id=v) for v in odd]
        st = self.pipe().stage(report_fn=fn)
        res = st.run()
        self.assertWrote(res)
        got = [r["rule_id"] for r in res.doc["quy_tac"]]
        want = ["RULE_0", "RULE_1", "RULE_2", "RULE_3", "RULE_4", "RULE_5", "RULE_6", "RULE_7", "RULE_8", "RULE_9",
                "RULE_10", "R-OK_1", "AB", "A" + "B" * 63]
        self.assertEqual(got, want)
        tokens = set(all_strings(res.doc))
        for v in odd[:11]:
            if v:
                self.assertNotIn(v, tokens)

    def test_a_valid_rule_id_is_copied_and_the_order_is_the_report_order(self):
        st = Pipeline(self).base
        res = st.run()
        self.assertEqual([r["rule_id"] for r in res.doc["quy_tac"]], [r["rule_id"] for r in st.report["rules"]])
        self.assertTrue(all(re.fullmatch(r"[A-Z][A-Z0-9_-]{1,63}", r["rule_id"]) for r in res.doc["quy_tac"]))

    def test_a_non_string_rule_id_is_replaced_too(self):
        st = self.pipe().stage(report_fn=lambda r: r["rules"][0].update(rule_id=["wall_01"]))
        res = st.run()
        self.assertWrote(res)
        self.assertEqual(res.doc["quy_tac"][0]["rule_id"], "RULE_0")
        self.assertNotIn("wall_01", res.text)


# ---------------------------------------------------------------------------------------------------- exit 2
class Refused(Base):
    def test_each_wrong_pin(self):
        st = Pipeline(self).base
        for key, code in (("sha256_cad_read", "SHA256_CAD_READ_SAI"), ("sha256_rules", "SHA256_QUY_TAC_SAI"),
                          ("sha256_report", "SHA256_BAO_CAO_SAI")):
            with self.subTest(key):
                self.assertRefused(st, st.run(**{key: "0" * 64}), code)

    def test_a_pin_of_the_wrong_shape_or_a_missing_argument(self):
        st = Pipeline(self).base
        for bad in ("abc", "g" * 64, "0" * 63, "0" * 65, ""):
            res = st.run(sha256_report=bad)
            self.assertEqual((res.code, res.doc), (2, None))
        argv = st.args()
        i = argv.index("--kiem-truy-vet")
        code, _, err = invoke(tt, argv[:i] + argv[i + 2:])
        self.assertEqual(code, 2)
        self.assertEqual(invoke(tt, [])[0], 2)
        self.assertEqual(invoke(tt, argv + ["--unknown", "x"])[0], 2)
        self.assertEqual(st.listing(), sorted(["cad_read.json", "rules.yaml", "report.json", "kvt.json"]))

    def test_bad_cadaudit_sha(self):
        st = Pipeline(self).base
        for bad in ("abc", "g" * 40, "a" * 39, "a" * 41, "a" * 64, "9f11076", ""):
            with self.subTest(bad):
                res = st.run(cadaudit_sha=bad)
                self.assertRefused(st, res)
                self.assertIn("--cadaudit-sha", res.stderr)

    def test_kiem_truy_vet_with_the_wrong_schema(self):
        for bad in ("tvxd.m04b.kiem_truy_vet/v2", "", None, "tvxd.m04b.tom_tat/v1"):
            with self.subTest(bad):
                st = self.pipe().stage(kvt_fn=lambda k, b=bad: k.update(schema=b))
                self.assertRefused(st, st.run(), "KIEM_TRUY_VET_SAI_SCHEMA")
        st = self.pipe().stage(kvt_fn=lambda k: k.pop("schema"))
        self.assertRefused(st, st.run(), "KIEM_TRUY_VET_SAI_SCHEMA")

    def test_kiem_truy_vet_that_is_not_an_object(self):
        for raw in (b"[]", b'"x"', b"3", b"null"):
            with self.subTest(raw):
                st = self.pipe().stage(raw={"kiem_truy_vet": raw})
                self.assertRefused(st, st.run(), "KIEM_TRUY_VET_SAI_SCHEMA")

    def test_kiem_truy_vet_with_a_mismatched_hash_for_each_file(self):
        for key in KEYS:
            with self.subTest(key):
                st = self.pipe().stage(kvt_fn=lambda k, key=key: k["sha256"][key].update(tinh_duoc="1" * 64))
                self.assertRefused(st, st.run(), "KIEM_TRUY_VET_HASH_LECH")

    def test_kiem_truy_vet_with_a_hash_of_another_run_of_the_same_inputs(self):
        """Kiểm truy vết của một báo cáo khác (đã chạy G7 trên báo cáo khác) không dùng được cho báo cáo này."""
        pipe = Pipeline(self)
        other = pipe.stage(report_fn=lambda r: r["rules"][0].update(title="khac"), rerun_kvt=True)
        self.assertEqual(other.kvt["ket_luan"], "DAT")
        st = pipe.stage(raw={"kiem_truy_vet": dumps(other.kvt)})
        self.assertRefused(st, st.run(), "KIEM_TRUY_VET_HASH_LECH")

    def test_kiem_truy_vet_with_a_missing_or_reordered_step(self):
        for steps in (["1", "2", "3", "4", "5", "6"], ["1", "2", "3", "4", "5", "6", "7", "8"], ["1"], [], ["1", "2", "3", "4", "5", "7", "6"],
                      [1, 2, 3, 4, 5, 6, 7], "1234567", None):
            with self.subTest(steps):
                st = self.pipe().stage(kvt_fn=lambda k, s=steps: k.update(buoc_da_chay=s))
                self.assertRefused(st, st.run(), "KIEM_TRUY_VET_THIEU_BUOC")
        st = self.pipe().stage(kvt_fn=lambda k: k.pop("buoc_da_chay"))
        self.assertRefused(st, st.run(), "KIEM_TRUY_VET_THIEU_BUOC")

    def test_kiem_truy_vet_with_the_wrong_kind_of_conclusion(self):
        cases = {"ket_luan_la": lambda k: k.update(ket_luan="PASS"),
                 "dat_nhung_co_ly_do": lambda k: k.update(ly_do_khong_dat=["COUNTS_LECH"]),
                 "khong_dat_khong_ly_do": lambda k: k.update(ket_luan="KHONG_DAT"),
                 "ly_do_tu_do": lambda k: k.update(ket_luan="KHONG_DAT", ly_do_khong_dat=["layer wall_01 sai"]),
                 "ly_do_khong_phai_chuoi": lambda k: k.update(ket_luan="KHONG_DAT", ly_do_khong_dat=[3]),
                 "ly_do_khong_phai_list": lambda k: k.update(ket_luan="KHONG_DAT", ly_do_khong_dat="COUNTS_LECH"),
                 "script_hash_sai_dang": lambda k: k["script"].update(sha256_lf="xyz"),
                 "thieu_script": lambda k: k.pop("script"),
                 "thieu_sha256": lambda k: k.pop("sha256")}
        for name, fn in cases.items():
            with self.subTest(name):
                st = self.pipe().stage(kvt_fn=fn)
                res = st.run()
                self.assertRefused(st, res, "KIEM_TRUY_VET_SAI_KIEU")
                self.assertNotIn("wall_01", res.stderr)

    def test_rules_file_hash_in_the_report_differs_from_the_rules_file(self):
        """Báo cáo ghi hash tệp quy tắc khác. G7 chạy lại thật cho ra KHONG_DAT, nhưng tóm tắt vẫn từ chối."""
        st = self.pipe().stage(report_fn=lambda r: r["rules_file"].update(sha256="2" * 64), rerun_kvt=True)
        self.assertEqual((st.kvt_code, st.kvt["ket_luan"]), (1, "KHONG_DAT"))
        self.assertIn("LIEN_KET_BAO_CAO_SAI", st.kvt["ly_do_khong_dat"])
        self.assertRefused(st, st.run(), "BAO_CAO_QUY_TAC_SHA_LECH")
        st = self.pipe().stage(report_fn=lambda r: r["rules_file"].update(sha256="2" * 64))
        self.assertRefused(st, st.run(), "BAO_CAO_QUY_TAC_SHA_LECH")

    def test_input_hash_in_the_report_differs_from_the_cad_read_file(self):
        st = self.pipe().stage(report_fn=lambda r: r["input"].update(input_sha256="3" * 64), rerun_kvt=True)
        self.assertEqual((st.kvt_code, st.kvt["ket_luan"]), (1, "KHONG_DAT"))
        self.assertRefused(st, st.run(), "BAO_CAO_INPUT_SHA_LECH")
        st = self.pipe().stage(report_fn=lambda r: r["input"].update(input_sha256="3" * 64))
        self.assertRefused(st, st.run(), "BAO_CAO_INPUT_SHA_LECH")

    def test_report_with_the_wrong_schema_or_a_wrong_type(self):
        cases = {
            "schema": lambda r: r.update(schema="tvxd.cadaudit.report/v2"),
            "rules_khong_phai_list": lambda r: r.update(rules={}),
            "rule_khong_phai_dict": lambda r: r["rules"].append("x"),
            "verdict_la": lambda r: r["rules"][0].update(verdict="MAYBE"),
            "verdict_thieu": lambda r: r["rules"][0].pop("verdict"),
            "classification_la": lambda r: r["rules"][0].update(classification="X"),
            "coverage_complete_la_int": lambda r: r["rules"][0].update(coverage_complete=1),
            "objects_am": lambda r: r["rules"][0].update(objects_in_scope=-1),
            "objects_bool": lambda r: r["rules"][0].update(objects_in_scope=True),
            "objects_float": lambda r: r["rules"][0].update(objects_in_scope=1.5),
            "reasons_khong_phai_list": lambda r: r["rules"][0].update(reasons="FIELD_MISSING"),
            "counts_thieu_khoa": lambda r: r["rules"][0]["counts"].pop("FAIL"),
            "counts_them_khoa": lambda r: r["rules"][0]["counts"].update(EXTRA=1),
            "counts_am": lambda r: r["rules"][0]["counts"].update(PASS=-1),
            "counts_chuoi": lambda r: r["rules"][0]["counts"].update(PASS="1"),
            "counts_bool": lambda r: r["rules"][0]["counts"].update(PASS=True),
            "summary_thieu_overall": lambda r: r["summary"].pop("overall"),
            "approved_la_int": lambda r: r["summary"].update(all_rules_approved=0),
            "by_verdict_them_khoa": lambda r: r["summary"]["rules_by_verdict"].update(EXTRA=0),
            "by_status_thieu": lambda r: r["summary"]["rules_by_status"].pop("APPROVED"),
            "results_by_verdict_float": lambda r: r["summary"]["results_by_verdict"].update(PASS=1.0),
            "version_rong": lambda r: r.update(cadaudit_version=""),
            "version_dai": lambda r: r.update(cadaudit_version="v" * 65),
            "version_dieu_khien": lambda r: r.update(cadaudit_version="0.1\n"),
            "version_khong_phai_chuoi": lambda r: r.update(cadaudit_version=1),
            "rules_version_thieu": lambda r: r["rules_file"].pop("rules_version"),
            "rules_version_dieu_khien": lambda r: r["rules_file"].update(rules_version="a\x00b"),
            "rules_file_khong_phai_dict": lambda r: r.update(rules_file=[]),
            "input_khong_phai_dict": lambda r: r.update(input=None),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                st = self.pipe().stage(report_fn=fn)
                self.assertRefused(st, st.run(), "BAO_CAO_SAI_")

    def test_report_that_is_not_an_object(self):
        for raw in (b"[]", b"3", b"null"):
            with self.subTest(raw):
                st = self.pipe().stage(raw={"bao_cao": raw})
                self.assertRefused(st, st.run(), "BAO_CAO_SAI_SCHEMA")

    def test_cad_read_with_a_wrong_coverage_type(self):
        cases = {
            "thieu_coverage": lambda c: c.pop("coverage"),
            "coverage_khong_phai_dict": lambda c: c.update(coverage=[]),
            "thieu_layers": lambda c: c["coverage"].pop("layers"),
            "thieu_xrefs": lambda c: c["coverage"].pop("xrefs"),
            "layers_khong_phai_dict": lambda c: c["coverage"].update(layers="COMPLETE"),
            "status_la": lambda c: c["coverage"]["layers"].update(status="DONE"),
            "status_thieu": lambda c: c["coverage"]["xrefs"].pop("status"),
            "expected_chuoi": lambda c: c["coverage"]["layers"].update(expected="4"),
            "expected_am": lambda c: c["coverage"]["layers"].update(expected=-1),
            "expected_bool": lambda c: c["coverage"]["xrefs"].update(expected=True),
            "enumerated_thieu": lambda c: c["coverage"]["xrefs"].pop("enumerated"),
            "enumerated_float": lambda c: c["coverage"]["xrefs"].update(enumerated=1.0),
            "enumerated_null": lambda c: c["coverage"]["layers"].update(enumerated=None),
            "reason_la": lambda c: c["coverage"]["layers"].update(reason="CHU_DE_TU_DO"),
            "reason_so": lambda c: c["coverage"]["layers"].update(reason=3),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                st = self.pipe().stage(cad_post=fn)
                self.assertRefused(st, st.run(), "CAD_READ_SAI_KIEU")
        st = self.pipe().stage(raw={"cad_read": b"[]"})
        self.assertEqual(st.run().code, 2)

    def test_cad_read_coverage_other_than_layers_and_xrefs_is_not_read(self):
        """Nhóm khác sai hoặc thiếu không làm tóm tắt hỏng: chỉ `layers` và `xrefs` được đọc, và không có nhóm khác trong output."""
        st = self.pipe().stage(cad_post=lambda c: c["coverage"].update(texts="bat-ky-gi"))
        res = st.run()
        self.assertWrote(res)
        self.assertNotIn("bat-ky-gi", res.text)

    def test_out_that_exists_is_refused_and_left_unchanged(self):
        st = Pipeline(self).base
        marker = os.path.join(st.dir, "da-co.json")
        with open(marker, "wb") as f:
            f.write(b"giu nguyen")
        before = st.listing()
        res = st.run(out=marker)
        self.assertEqual(res.code, 2)
        self.assertIn("OUT_DA_TON_TAI", res.stderr)
        self.assertEqual(read_bytes(marker), b"giu nguyen")
        self.assertEqual(st.listing(), before)
        self.assertNotIn(st.dir, res.stderr)

    def test_out_that_is_a_directory(self):
        st = Pipeline(self).base
        d = os.path.join(st.dir, "thu-muc")
        os.mkdir(d)
        before = st.listing()
        res = st.run(out=d)
        self.assertEqual((res.code, st.listing(), os.listdir(d)), (2, before, []))
        self.assertIn("OUT_DA_TON_TAI", res.stderr)

    def test_out_that_is_a_symlink(self):
        st = Pipeline(self).base
        target = os.path.join(st.dir, "dich.json")
        dangling, to_file = os.path.join(st.dir, "treo.json"), os.path.join(st.dir, "toi-tep.json")
        with open(os.path.join(st.dir, "co-san.json"), "wb") as f:
            f.write(b"giu nguyen")
        try:
            os.symlink(target, dangling)
            os.symlink(os.path.join(st.dir, "co-san.json"), to_file)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this machine")
        for link in (dangling, to_file):
            res = st.run(out=link)
            self.assertEqual(res.code, 2)
            self.assertIn("OUT_DA_TON_TAI", res.stderr)
        self.assertFalse(os.path.exists(target))
        self.assertEqual(read_bytes(os.path.join(st.dir, "co-san.json")), b"giu nguyen")

    def test_out_in_a_missing_directory(self):
        st = Pipeline(self).base
        before = st.listing()
        res = st.run(out=os.path.join(st.dir, "khong-co", "o.json"))
        self.assertEqual((res.code, res.doc, st.listing()), (2, None, before))
        self.assertNotIn(st.dir, res.stderr)

    def test_missing_input_files(self):
        st = Pipeline(self).base
        for key in ("cad_read", "rules", "report", "kiem_truy_vet"):
            with self.subTest(key):
                res = st.run(**{key: os.path.join(st.dir, "khong-co.bin")})
                self.assertRefused(st, res)
                self.assertNotIn("khong-co", res.stderr)

    def test_duplicate_keys_nan_and_non_json_in_each_json_input(self):
        pipe = Pipeline(self)
        good = {"cad_read": pipe.base.files["cad_read"], "bao_cao": pipe.base.files["bao_cao"],
                "kiem_truy_vet": pipe.base.files["kiem_truy_vet"]}
        names = {"cad_read": "CAD_READ", "bao_cao": "BAO_CAO", "kiem_truy_vet": "KIEM_TRUY_VET"}
        for key, data in good.items():
            dup = b'{"schema": "x", ' + data.lstrip()[1:]                    # khóa `schema` có hai lần
            variants = {"khoa_trung": dup, "nan": b'{"x": NaN}', "infinity": b'{"x": -Infinity}', "so_qua_lon": b'{"x": 1e999}',
                        "khong_phai_json": b"{ not json", "khong_utf8": b"\xff\xfe\x00"}
            for vname, raw in variants.items():
                with self.subTest(key=key, variant=vname):
                    st = pipe.stage(raw={key: raw})
                    res = st.run()
                    self.assertRefused(st, res, f"{names[key]}_KHONG_PHAI_JSON")

    def test_duplicate_key_nested_in_the_report(self):
        data = Pipeline(self).base.files["bao_cao"].decode("utf-8")
        raw = data.replace('"PASS":', '"PASS": 0, "PASS":', 1).encode("utf-8")
        st = self.pipe().stage(raw={"bao_cao": raw})
        self.assertRefused(st, st.run(), "BAO_CAO_KHONG_PHAI_JSON")

    def test_internal_error_is_exit_70_and_writes_nothing(self):
        st = Pipeline(self).base
        original = tt.script_info
        tt.script_info = lambda: 1 / 0
        self.addCleanup(setattr, tt, "script_info", original)
        res = st.run()
        self.assertEqual((res.code, res.doc), (70, None))
        self.assertIn("ZeroDivisionError", res.stderr)
        self.assertEqual(st.listing(), sorted(["cad_read.json", "rules.yaml", "report.json", "kvt.json"]))


# ---------------------------------------------------------------------------------------------------- kiểm soát tĩnh
class StaticControls(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(read_bytes(SCRIPT).decode("utf-8"))

    def test_only_standard_library_modules_and_no_cadaudit_gateway_network_or_process(self):
        mods = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
        top = {m.split(".")[0] for m in mods}
        self.assertEqual(top - {"argparse", "datetime", "hashlib", "json", "os", "re", "sys"}, set(), mods)
        for banned in ("cadaudit", "gateway", "kiem_truy_vet", "yaml", "subprocess", "socket", "urllib", "http", "ssl",
                       "requests", "shutil", "ctypes", "win32com", "comtypes"):
            self.assertNotIn(banned, top)

    def test_the_only_open_modes_are_read_and_exclusive_create(self):
        modes = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
                self.assertIsInstance(mode, ast.Constant, "open() needs a literal mode")
                modes.append(mode.value)
        self.assertEqual(set(modes), {"rb", "xb"})
        self.assertEqual(modes.count("xb"), 1)

    def test_no_other_way_to_write_delete_or_run(self):
        banned_attrs = {"remove", "unlink", "rmdir", "rename", "write_text", "write_bytes", "system", "popen", "makedirs",
                        "mkdir", "chmod", "symlink", "link", "rmtree", "copyfile", "move", "dump", "safe_dump", "run", "Popen",
                        "call", "check_call", "check_output", "urlopen", "connect", "startfile"}
        banned_names = {"eval", "exec", "compile", "__import__", "subprocess", "socket"}
        found = [n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute) and n.attr in banned_attrs]
        found += [n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name) and n.id in banned_names]
        self.assertEqual(found, [])
        os_replace = [n for n in ast.walk(self.tree) if isinstance(n, ast.Attribute) and n.attr == "replace"
                      and isinstance(n.value, ast.Name) and n.value.id == "os"]
        self.assertEqual(os_replace, [])          # `bytes.replace` (chuẩn hóa CRLF trước khi băm) thì được

    def test_the_output_is_built_from_a_fixed_field_list(self):
        """Không có chỗ nào chép nguyên khối từ báo cáo hay CAD_READ vào output: không `dict(report...)`, không `**report`."""
        src = read_bytes(SCRIPT).decode("utf-8")
        for pat in (r"\*\*\s*(report|cad|rep|ktv)\b", r"\bdict\(\s*(report|cad|rep|ktv)\b", r"copy\.deepcopy"):
            self.assertIsNone(re.search(pat, src), pat)
        for forbidden in ("results", "evidence_ids", "drawing", "handle", "standard_hint", "reads_groups", "dwg_sha256", "file_id"):
            strings = [n.value for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and n.value == forbidden]
            self.assertEqual(strings, [], f"the script mentions {forbidden!r} as data")


if __name__ == "__main__":
    unittest.main()
