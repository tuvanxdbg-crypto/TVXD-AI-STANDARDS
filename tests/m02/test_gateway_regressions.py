#!/usr/bin/env python3
"""Regressions for GPT_REVIEW_V1 at d35b574 (PR #5), findings F1-F7. Fixture data and fake backends only."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HERE, TODAY, FixtureCopy, lookup, make_service

from fake_notebooklm import FakeNotebookLM
from gateway import schema
from gateway.adapters.notebooklm import McpStdioNotebookLMClient
from gateway.clauses import canonical_clause, parse_sections
from gateway.errors import GatewayError
from gateway.evidence import content_evidence_id

ELEC = {"work_code": "ELEC-LV-FAKE", "assessment_date": TODAY}
GEN = {"work_code": "GEN-FAKE", "assessment_date": TODAY}
QCVN_PASSAGE = "Khoảng cách thông thủy giả lập phía trước tủ điện hạ thế không nhỏ hơn 1111 mm."
QCVN_2024 = "02_QCVN/QCVN-FAKE-01-2024.md"


def answers(*citations, sources_used=None, answer="(fake) câu trả lời giả lập"):
    body = {"answer": answer, "citations": [{"source_id": s, "passage": p} for s, p in citations]}
    if sources_used:
        body["sources_used"] = sources_used
    return {"nb-fixture-001": body}


def checks(r: dict) -> dict:
    return {c["name"]: c["result"] for c in r["checks"]}


def reid(ev: dict) -> dict:
    """A tamperer who also recomputes EVIDENCE_ID: only the semantic checks can catch it."""
    ev = copy.deepcopy(ev)
    ev["EVIDENCE_ID"] = content_evidence_id(ev)
    return ev


def rehash(fx: FixtureCopy, rel: str, edit) -> None:
    """Change a fixture file in the temporary copy and keep INDEX (source + sync hash) consistent."""
    p = fx.library / rel
    old = hashlib.sha256(p.read_bytes()).hexdigest()
    p.write_bytes(edit(p.read_bytes()))
    new = hashlib.sha256(p.read_bytes()).hexdigest()
    text = fx.index.read_text(encoding="utf-8")
    fx.index.write_text(text.replace(old, new), encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.fx = FixtureCopy()

    def tearDown(self):
        self.fx.cleanup()

    def verify(self, svc, ev, ctx=ELEC):
        r = svc.call("standards_verify", {"evidence": ev, **ctx})
        self.assertFalse(schema.check(r, "verify.response.v1.json"))
        return r


class F1VerifyBindsEvidenceFields(Base):
    """F1: CLAUSE, SOURCE_ID, SOURCE_HASH (and the other identity fields) are checked, not trusted."""

    def setUp(self):
        super().setUp()
        self.svc, _ = make_service(self.fx.config)
        self.ev = lookup(self.svc, query="QCVN FAKE 01 mục 2.1", **ELEC)["results"][0]
        self.assertEqual(self.ev["STATUS"], "VERIFIED")

    def tamper(self, fn) -> dict:
        ev = copy.deepcopy(self.ev)
        fn(ev)
        return ev

    def test_genuine_evidence_still_verifies(self):
        r = self.verify(self.svc, self.ev)
        self.assertEqual(r["status"], "VERIFIED")
        self.assertEqual(checks(r)["MAPPING"], "SKIPPED")
        self.assertTrue(all(v == "PASS" for k, v in checks(r).items() if k != "MAPPING"))

    def test_each_modified_field_fails_its_own_check(self):
        cases = {
            "CLAUSE": (lambda e: e.update(CLAUSE={"id": "999", "heading": "fabricated clause"}), "CLAUSE"),
            "CLAUSE=null": (lambda e: e.update(CLAUSE=None), "CLAUSE"),
            "CLAUSE sibling": (lambda e: e.update(CLAUSE={"id": "2.2", "heading": e["CLAUSE"]["heading"]}), "CLAUSE"),
            "SOURCE_ID": (lambda e: e.update(SOURCE_ID="OTHER@2099"), "SOURCE_ID"),
            "DOCUMENT.title": (lambda e: e["DOCUMENT"].update(title="Tài liệu khác"), "SOURCE_ID"),
            "SOURCE_HASH.expected": (lambda e: e["SOURCE_HASH"].update(expected="0" * 64), "SOURCE_HASH"),
            "SOURCE_HASH.observed": (lambda e: e["SOURCE_HASH"].update(observed="f" * 64), "SOURCE_HASH"),
            "SOURCE_HASH.match": (lambda e: e["SOURCE_HASH"].update(match=False), "SOURCE_HASH"),
            "SOURCE_HASH.observed_from": (lambda e: e["SOURCE_HASH"].update(observed_from="notebooklm_sync_identity"),
                                          "SOURCE_HASH"),
            "SOURCE_HASH=null": (lambda e: e.update(SOURCE_HASH=None), "SOURCE_HASH"),
            "SOURCE_LOCATION.path": (lambda e: e["SOURCE_LOCATION"].update(path="02_QCVN/QCVN-FAKE-01-2019.md"),
                                     "SOURCE_LOCATION"),
            "route": (lambda e: e["RETRIEVAL_PATH"].update(route="NOTEBOOKLM"), "SOURCE_LOCATION"),
            "resolved_by": (lambda e: e["RETRIEVAL_PATH"].update(resolved_by="SEMANTIC"), "SOURCE_LOCATION"),
            "EVIDENCE.truncated": (lambda e: e["EVIDENCE"].update(truncated=True), "EXCERPT_MATCH"),
            "EVIDENCE.text prefix": (lambda e: e["EVIDENCE"].update(text=e["EVIDENCE"]["text"][:40]), "EXCERPT_MATCH"),
        }
        for name, (fn, check) in cases.items():
            bad = self.tamper(fn)
            r = self.verify(self.svc, bad)                    # EVIDENCE_ID left unchanged
            self.assertEqual(r["status"], "FAILED", name)
            r = self.verify(self.svc, reid(bad))              # EVIDENCE_ID recomputed by the tamperer
            self.assertEqual(r["status"], "FAILED", name)
            self.assertEqual(checks(r)["EVIDENCE_ID"], "PASS", name)
            self.assertEqual(checks(r)[check], "FAIL", name)

    def test_unchanged_evidence_id_does_not_make_a_modified_object_trustworthy(self):
        for fn in (lambda e: e.update(SOURCE_ID="OTHER@2099"),
                   lambda e: e["ANSWER"].update(text="câu trả lời bịa", origin="NOTEBOOKLM"),
                   lambda e: e["EVIDENCE"].update(layout_dependent=True)):
            r = self.verify(self.svc, self.tamper(fn))
            self.assertEqual((r["status"], checks(r)["EVIDENCE_ID"]), ("FAILED", "FAIL"))

    def test_modified_registered_evidence_is_not_rescued_by_its_id(self):
        bad = self.tamper(lambda e: e.update(CLAUSE={"id": "999", "heading": "fabricated clause"}))
        self.assertEqual(self.verify(self.svc, bad)["status"], "FAILED")
        r = self.svc.call("standards_verify", {"evidence_id": self.ev["EVIDENCE_ID"], **ELEC})
        self.assertEqual(r["status"], "VERIFIED")             # the registry holds the Gateway's own object

    def test_notebooklm_evidence_fields_are_bound_too(self):
        svc, _ = make_service(self.fx.config, client=FakeNotebookLM(answers(("src-qcvn01-2024", QCVN_PASSAGE))))
        ev = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)["results"][0]
        self.assertEqual((ev["STATUS"], ev["RETRIEVAL_PATH"]["route"]), ("VERIFIED", "NOTEBOOKLM"))
        self.assertEqual(self.verify(svc, ev)["status"], "VERIFIED")
        cases = {
            "SOURCE_HASH.observed": (lambda e: e["SOURCE_HASH"].update(observed="0" * 64), "SOURCE_HASH"),
            "CLAUSE fabricated": (lambda e: e.update(CLAUSE={"id": "999", "heading": "x"}), "CLAUSE"),
            "SOURCE_ID": (lambda e: e.update(SOURCE_ID="QCVN-FAKE-01@2019"), "SOURCE_ID"),
            "route LOCAL": (lambda e: e["RETRIEVAL_PATH"].update(route="LOCAL", resolved_by="INDEX_CODE"),
                            "SOURCE_LOCATION"),
            "notebook id": (lambda e: e["SOURCE_LOCATION"].update(source_id="src-luat99"), "MAPPING"),
        }
        for name, (fn, check) in cases.items():
            bad = copy.deepcopy(ev)
            fn(bad)
            r = self.verify(svc, reid(bad))
            self.assertEqual((r["status"], checks(r)[check]), ("FAILED", "FAIL"), name)
        # A clause claimed for a NotebookLM passage must be the clause that contains it in the file.
        good = copy.deepcopy(ev)
        good["CLAUSE"] = self.ev["CLAUSE"]
        self.assertEqual(self.verify(svc, reid(good))["status"], "VERIFIED")

    def test_lookup_to_verify_round_trip_never_upgrades(self):
        fake = FakeNotebookLM(answers(("src-qcvn01-2024", "Bảng 1 - Hệ số giả lập")))
        svc, _ = make_service(self.fx.config, client=fake)
        runs = [(dict(query="QCVN FAKE 01 mục 2.1"), ELEC), (dict(query="chiều cao ổ cắm", document_id="QCVN-FAKE-01"), ELEC),
                (dict(query="x", document_id="LUAT-FAKE-99", clause="khoản 2 Điều 2"), GEN),
                (dict(query="TCVN FAKE 8888 mục 2.2"), ELEC), (dict(query="hệ số giả lập"), ELEC),
                (dict(query="QCVN FAKE 01 mục 2.1"), {"work_code": "ELEC-LV-FAKE"})]
        seen = set()
        for args, ctx in runs:
            for ev in lookup(svc, **args, **ctx)["results"]:
                status = self.verify(svc, ev, ctx)["status"]
                if ev["STATUS"] == "VERIFIED":
                    self.assertEqual(status, "VERIFIED", args)
                else:
                    self.assertNotEqual(status, "VERIFIED", args)
                seen.add(ev["STATUS"])
        self.assertEqual(seen, {"VERIFIED", "UNKNOWN"})


class F2NoExcerptIsNotVerified(Base):
    """F2: a skipped/failed excerpt check never yields VERIFIED (lookup -> verify, unmodified evidence)."""

    def test_sources_used_without_passage(self):
        fake = FakeNotebookLM(answers(sources_used=["src-qcvn01-2024"]))
        svc, _ = make_service(self.fx.config, client=fake)
        ev = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)["results"][0]
        self.assertEqual(ev["STATUS"], "UNKNOWN")
        self.assertIn("NO_PASSAGE", [u["code"] for u in ev["UNCERTAINTY"]])
        r = self.verify(svc, ev)
        self.assertEqual(r["status"], "UNKNOWN")
        self.assertEqual(checks(r)["EXCERPT_MATCH"], "UNKNOWN")
        self.assertNotIn("SKIPPED", [v for k, v in checks(r).items() if k != "MAPPING"])

    def test_passage_not_found(self):
        svc, _ = make_service(self.fx.config, client=FakeNotebookLM(answers(
            ("src-qcvn01-2024", "Bảng 9 - nội dung không có trong tệp gốc"))))
        ev = lookup(svc, query="bảng 9", **ELEC)["results"][0]
        self.assertIn("PASSAGE_NOT_FOUND", [u["code"] for u in ev["UNCERTAINTY"]])
        r = self.verify(svc, ev)
        self.assertEqual((r["status"], checks(r)["EXCERPT_MATCH"]), ("UNKNOWN", "UNKNOWN"))

    def test_failed_local_reread(self):
        svc, _ = make_service(self.fx.config, client=FakeNotebookLM(answers(
            ("src-qcvn01-2024", "Bảng 1 - Hệ số giả lập"))))
        p = self.fx.library / QCVN_2024
        original = p.read_bytes()
        p.write_bytes(original + b"\n")                       # reread fails (drift) during lookup
        ev = lookup(svc, query="hệ số giả lập", **ELEC)["results"][0]
        self.assertIn("LOCAL_REREAD_FAILED", [u["code"] for u in ev["UNCERTAINTY"]])
        p.write_bytes(original)                               # file restored: identity checks pass again
        r = self.verify(svc, ev)
        self.assertEqual(checks(r)["SOURCE_HASH"], "PASS")
        self.assertEqual((r["status"], checks(r)["EXCERPT_MATCH"]), ("UNKNOWN", "UNKNOWN"))


class F3ExplicitVersionEligibility(Base):
    """F3: an explicit version names the file to read; it never establishes eligibility or effectivity."""

    def test_withdrawn_and_draft_explicit_version(self):
        for status in ("withdrawn", "draft"):
            fx = FixtureCopy()
            try:
                fx.edit_index('version: "2024"\n        status: active', f'version: "2024"\n        status: {status}')
                svc, _ = make_service(fx.config)
                ev = lookup(svc, query="QCVN FAKE 01 mục 2.1", version="2024", **ELEC)["results"][0]
                self.assertEqual(ev["STATUS"], "UNKNOWN", status)
                self.assertIn("VERSION_UNRESOLVED", [u["code"] for u in ev["UNCERTAINTY"]])
                self.assertIsNone(ev["VERIFIED_AT"])
                r = self.verify(svc, ev)
                self.assertEqual((r["status"], checks(r)["VERSION_RESOLVED"]), ("FAILED", "FAIL"), status)
            finally:
                fx.cleanup()

    def test_overlapping_effectivity_with_explicit_version(self):
        svc, _ = make_service(self.fx.config)
        r = lookup(svc, query="TCVN FAKE 9999 mục 1", **GEN)
        self.assertEqual(r["error"]["code"], "VERSION_AMBIGUOUS")
        for ver in ("2021", "2022"):
            ev = lookup(svc, query="TCVN FAKE 9999 mục 1", version=ver, **GEN)["results"][0]
            self.assertEqual(ev["STATUS"], "UNKNOWN", ver)
            self.assertIn("VERSION_UNRESOLVED", [u["code"] for u in ev["UNCERTAINTY"]])
            v = self.verify(svc, ev, GEN)
            self.assertEqual((v["status"], checks(v)["VERSION_RESOLVED"]), ("UNKNOWN", "UNKNOWN"), ver)

    def test_explicit_version_that_is_eligible_still_works(self):
        svc, _ = make_service(self.fx.config)
        ev = lookup(svc, query="QCVN FAKE 01 mục 2.1", version="2024", **ELEC)["results"][0]
        self.assertEqual(ev["STATUS"], "VERIFIED")
        old = dict(work_code="ELEC-LV-FAKE", assessment_date="2024-06-01")
        ev = lookup(svc, query="QCVN FAKE 01 mục 2.1", version="2019", **old)["results"][0]
        self.assertEqual((ev["STATUS"], ev["VERSION"]), ("VERIFIED", "2019"))
        ev = lookup(svc, query="QCVN FAKE 01 mục 2.1", version="2019", **ELEC)["results"][0]
        self.assertEqual(ev["STATUS"], "NOT_APPLICABLE")


class F4PointLetters(Base):
    """F4: Vietnamese points d) and đ) are different clauses."""

    LINES = ("Điều 4. Giá trị giả lập", "1. Các giá trị sau:", "c) Giá trị 5 mm.", "d) Giá trị 10 mm.",
             "đ) Giá trị 20 mm.", "e) Giá trị 30 mm.")

    def test_parser_and_canonical_keep_d_and_dstroke_apart(self):
        ids = [s.id for s in parse_sections(self.LINES, "article")]
        self.assertEqual(ids[3:5], ["Điều 4 khoản 1 điểm d", "Điều 4 khoản 1 điểm đ"])
        self.assertEqual(len(ids), len(set(ids)))
        for ref, want in [("Điều 4 khoản 1 điểm đ", "Điều 4 khoản 1 điểm đ"),
                          ("điểm Đ khoản 1 Điều 4", "Điều 4 khoản 1 điểm đ"),
                          ("dieu 4 khoan 1 diem d", "Điều 4 khoản 1 điểm d"),
                          ("Điều 4 khoản 1 điểm d", "Điều 4 khoản 1 điểm d")]:
            self.assertEqual(canonical_clause(ref, "article"), want, ref)
        self.assertEqual(canonical_clause("LUAT FAKE 99 Điều 4 khoản 1 điểm đ về giá trị", "article", strict=False),
                         "Điều 4 khoản 1 điểm đ")

    def test_end_to_end_lookup_returns_the_requested_point(self):
        extra = ("\n\n" + "\n".join(self.LINES) + "\n").encode("utf-8")
        rehash(self.fx, "01_PHAP_LUAT/LUAT-FAKE-99-2025.txt", lambda b: b + extra)
        svc, _ = make_service(self.fx.config)
        for args, want, other in [
                (dict(document_id="LUAT-FAKE-99", clause="Điều 4 khoản 1 điểm đ", query="x"), "20 mm", "10 mm"),
                (dict(document_id="LUAT-FAKE-99", clause="Điều 4 khoản 1 điểm d", query="x"), "10 mm", "20 mm"),
                (dict(query="LUAT FAKE 99 Điều 4 khoản 1 điểm đ"), "20 mm", "10 mm")]:
            ev = lookup(svc, **args, **GEN)["results"][0]
            self.assertEqual(ev["STATUS"], "VERIFIED", args)
            self.assertIn(want, ev["EVIDENCE"]["text"], args)
            self.assertNotIn(other, ev["EVIDENCE"]["text"], args)
            self.assertEqual(self.verify(svc, ev, GEN)["status"], "VERIFIED")


class F5NotebookWhitelistRevocation(Base):
    """F5: verify re-checks the current notebook whitelist for NOTEBOOKLM and reread evidence."""

    def test_revoked_notebook_fails_verification(self):
        fake = FakeNotebookLM(answers(("src-qcvn01-2024", QCVN_PASSAGE)))
        svc, _ = make_service(self.fx.config, client=fake)
        direct = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)["results"][0]
        fake.answers = answers(("src-qcvn01-2024", "Bảng 1 - Hệ số giả lập"))
        reread = lookup(svc, query="hệ số giả lập", **ELEC)["results"][0]
        self.assertEqual([e["RETRIEVAL_PATH"]["route"] for e in (direct, reread)],
                         ["NOTEBOOKLM", "NOTEBOOKLM_LOCAL_REREAD"])
        for ev in (direct, reread):
            self.assertEqual(self.verify(svc, ev)["status"], "VERIFIED")
        self.fx.edit_index("notebooklm_notebooks: [nb-fixture-001]", "notebooklm_notebooks: []")
        for ev in (direct, reread):
            r = self.verify(svc, ev)
            self.assertEqual((r["status"], checks(r)["MAPPING"]), ("FAILED", "FAIL"), ev["RETRIEVAL_PATH"]["route"])
        r = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)  # new lookups exclude it as well
        self.assertIn({"document_id": "QCVN-FAKE-01", "reason": "NOTEBOOK_NOT_WHITELISTED"}, r["excluded"])


class F6SemanticSourceIdentity(Base):
    """F6: semantic results (cache hit or miss) require the authoritative file to still be the INDEX version."""

    def test_cache_hit_after_local_drift_is_not_served(self):
        fake = FakeNotebookLM(answers(("src-qcvn01-2024", QCVN_PASSAGE)))
        svc, _ = make_service(self.fx.config, client=fake)
        q = dict(query="khoảng cách trước tủ điện", **ELEC)
        self.assertEqual(lookup(svc, **q)["results"][0]["STATUS"], "VERIFIED")
        hit = lookup(svc, **q)["results"][0]
        self.assertTrue(hit["RETRIEVAL_PATH"]["cache_hit"])
        self.assertEqual(len(fake.calls), 1)
        p = self.fx.library / QCVN_2024
        original = p.read_bytes()
        p.write_bytes(original.replace(b"1111", b"2222"))   # INDEX unchanged
        r = lookup(svc, **q)
        ev = r["results"][0]
        self.assertFalse(ev["RETRIEVAL_PATH"]["cache_hit"])
        self.assertEqual(ev["STATUS"], "UNKNOWN")
        self.assertIn("SOURCE_DRIFT", [u["code"] for u in ev["UNCERTAINTY"]])
        self.assertIsNone(ev["VERIFIED_AT"])
        self.assertEqual(len(fake.calls), 2)                 # stale entry invalidated, fresh query
        self.assertGreaterEqual(svc.cache.invalidations, 1)
        again = lookup(svc, **q)["results"][0]                # still drifted: never VERIFIED
        self.assertEqual(again["STATUS"], "UNKNOWN")
        self.assertEqual(self.verify(svc, ev)["status"], "FAILED")
        p.write_bytes(original)                               # restored: identity changes back
        back = lookup(svc, **q)["results"][0]
        self.assertEqual((back["STATUS"], back["RETRIEVAL_PATH"]["cache_hit"]), ("VERIFIED", False))

    def test_cold_lookup_with_drifted_or_missing_file(self):
        p = self.fx.library / QCVN_2024
        p.write_bytes(p.read_bytes().replace(b"1111", b"2222"))
        svc, _ = make_service(self.fx.config, client=FakeNotebookLM(answers(("src-qcvn01-2024", QCVN_PASSAGE))))
        ev = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)["results"][0]
        self.assertEqual(ev["STATUS"], "UNKNOWN")
        self.assertIn("SOURCE_DRIFT", [u["code"] for u in ev["UNCERTAINTY"]])
        p.unlink()
        svc2, _ = make_service(self.fx.config, client=FakeNotebookLM(answers(("src-qcvn01-2024", QCVN_PASSAGE))))
        ev = lookup(svc2, query="khoảng cách trước tủ điện", **ELEC)["results"][0]
        self.assertEqual(ev["STATUS"], "UNKNOWN")
        self.assertIn("LOCAL_IDENTITY_UNAVAILABLE", [u["code"] for u in ev["UNCERTAINTY"]])


class F7McpStartupReadiness(unittest.TestCase):
    """F7: only a fully initialized, surface-validated MCP process is ever used."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "server.log"

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, *options: str) -> McpStdioNotebookLMClient:
        cfg = self.dir / "mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"gemini-notebook-mcp": {
            "command": sys.executable,
            "args": [str(HERE / "fake_mcp_server.py"), "--log", str(self.log), *options]}}}), encoding="utf-8")
        c = McpStdioNotebookLMClient(cfg, start_timeout_s=0.5)
        self.addCleanup(c.close)
        return c

    def log_lines(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def assertCode(self, fn, code: str) -> GatewayError:
        with self.assertRaises(GatewayError) as cm:
            fn()
        self.assertEqual(cm.exception.code, code)
        return cm.exception

    def test_initialize_timeout_never_leaves_a_usable_process(self):
        c = self.client("--init-delay", "5", "--extra-tool")
        self.assertCode(c.notebook_list, "TIMEOUT")
        self.assertIsNone(c._proc)
        self.assertFalse(c._ready)
        self.assertCode(c.notebook_list, "TIMEOUT")          # the second call restarts; it does not reuse
        self.assertEqual(self.log_lines(), ["start", "start"])

    def test_restart_after_initialize_timeout_still_checks_the_surface(self):
        c = self.client("--init-delay", "5", "--delay-once", str(self.dir / "once"), "--extra-tool")
        self.assertCode(c.notebook_list, "TIMEOUT")
        e = self.assertCode(c.notebook_list, "BACKEND_UNAVAILABLE")
        self.assertIn("four M01-approved", e.message)
        self.assertEqual(self.log_lines(), ["start", "start"])   # no tools/call ever reached the server
        self.assertFalse(c._ready)

    def test_tools_list_timeout_then_clean_validated_restart(self):
        c = self.client("--list-delay", "5", "--delay-once", str(self.dir / "once"))
        self.assertCode(c.notebook_list, "TIMEOUT")
        self.assertIsNone(c._proc)
        self.assertEqual(c.notebook_list()["status"], "success")
        self.assertTrue(c._ready)
        self.assertEqual(c.notebook_list()["status"], "success")  # validated process is reused
        self.assertEqual(self.log_lines(), ["start", "start", "call notebook_list", "call notebook_list"])

    def test_dead_process_is_replaced_and_revalidated(self):
        c = self.client()
        self.assertEqual(c.notebook_list()["status"], "success")
        c._proc.kill()
        c._proc.wait(timeout=10)
        self.assertEqual(c.notebook_list()["status"], "success")
        self.assertEqual(self.log_lines(), ["start", "call notebook_list", "start", "call notebook_list"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
