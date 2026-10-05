#!/usr/bin/env python3
"""M02 resilience: timeout, bounded retry, unavailable backend, auth, no fallback/whitelist widening."""
from __future__ import annotations

import time
import unittest

from helpers import TODAY, lookup, make_service

from fake_notebooklm import FakeNotebookLM
from gateway.adapters.notebooklm import NotebookLMAdapter
from gateway.errors import GatewayError
from gateway.retry import call_with_retry

ELEC = {"work_code": "ELEC-LV-FAKE", "assessment_date": TODAY}
OK = {"nb-fixture-001": {"answer": "a", "citations": [
    {"source_id": "src-qcvn01-2024",
     "passage": "Khoảng cách thông thủy giả lập phía trước tủ điện hạ thế không nhỏ hơn 1111 mm."}]}}
UNAVAILABLE = {"status": "error", "error": "Service temporarily unavailable (503)"}


def adapter(fake, **kw):
    return NotebookLMAdapter(fake, timeout_s=kw.get("timeout_s", 1.0), max_attempts=kw.get("max_attempts", 3),
                             total_budget_s=kw.get("total_budget_s", 5.0), backoff_s=0.0)


class Retry(unittest.TestCase):
    def test_timeout_is_bounded(self):
        fake = FakeNotebookLM(OK)
        fake.delay_s = 0.5
        t0 = time.monotonic()
        with self.assertRaises(GatewayError) as cm:
            adapter(fake, timeout_s=0.1, max_attempts=2, total_budget_s=2).query("nb-fixture-001", "q",
                                                                                  ["src-qcvn01-2024"])
        self.assertEqual(cm.exception.code, "TIMEOUT")
        self.assertEqual(cm.exception.details["attempts"], 2)
        self.assertLess(time.monotonic() - t0, 1.0)

    def test_transient_retry_exhaustion(self):
        fake = FakeNotebookLM(OK)
        fake.fail_with = [dict(UNAVAILABLE) for _ in range(5)]
        a = adapter(fake, max_attempts=3)
        with self.assertRaises(GatewayError) as cm:
            a.query("nb-fixture-001", "q", ["src-qcvn01-2024"])
        self.assertEqual((cm.exception.code, cm.exception.retryable), ("BACKEND_UNAVAILABLE", True))
        self.assertEqual(len(fake.calls), 3)

    def test_transient_then_success(self):
        fake = FakeNotebookLM(OK)
        fake.fail_with = [dict(UNAVAILABLE)]
        res = adapter(fake).query("nb-fixture-001", "q", ["src-qcvn01-2024"])
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(res.citations[0].source_id, "src-qcvn01-2024")

    def test_auth_and_permanent_errors_are_not_retried(self):
        for payload, code in [({"status": "error", "error": "Authentication expired, run nlm login"}, "AUTH_REQUIRED"),
                              ({"status": "error", "error": "Source not found"}, "BACKEND_UNAVAILABLE")]:
            fake = FakeNotebookLM(OK)
            fake.fail_with = [payload, payload]
            with self.assertRaises(GatewayError) as cm:
                adapter(fake).query("nb-fixture-001", "q", ["src-qcvn01-2024"])
            self.assertEqual((cm.exception.code, cm.exception.retryable), (code, False))
            self.assertEqual(len(fake.calls), 1)
            self.assertNotIn("nlm login", cm.exception.message)

    def test_unexpected_exception_reports_type_only(self):
        fake = FakeNotebookLM(OK)
        fake.raise_with = [RuntimeError("cookie=SECRET-VALUE")]
        with self.assertRaises(GatewayError) as cm:
            adapter(fake).query("nb-fixture-001", "q", ["src-qcvn01-2024"])
        self.assertEqual(cm.exception.code, "BACKEND_UNAVAILABLE")
        self.assertNotIn("SECRET", cm.exception.message)

    def test_total_budget_caps_attempts(self):
        calls = []

        def slow():
            calls.append(1)
            time.sleep(0.3)

        t0 = time.monotonic()
        with self.assertRaises(GatewayError) as cm:
            call_with_retry(slow, timeout_s=0.2, max_attempts=10, total_budget_s=0.5, backoff_s=0.0)
        self.assertEqual(cm.exception.code, "TIMEOUT")
        self.assertLessEqual(len(calls), 3)
        self.assertLess(time.monotonic() - t0, 1.2)

    def test_empty_source_list_is_refused_before_any_call(self):
        fake = FakeNotebookLM(OK)
        with self.assertRaises(GatewayError) as cm:
            adapter(fake).query("nb-fixture-001", "q", [])
        self.assertEqual(cm.exception.code, "SOURCE_NOT_ALLOWED")
        self.assertEqual(fake.calls, [])


class ServiceLevel(unittest.TestCase):
    def test_auth_error_has_no_fallback_and_no_whitelist_widening(self):
        fake = FakeNotebookLM(OK)
        fake.fail_with = [{"status": "error", "error": "login required"}]
        svc, _ = make_service(client=fake)
        reads = svc.local.reads
        r = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)
        self.assertEqual((r["status"], r["error"]["code"]), ("ERROR", "AUTH_REQUIRED"))
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(svc.local.reads, reads)          # no silent switch to another backend
        (_, _, _, sent), = fake.calls
        self.assertNotIn("src-qcvn02", sent)

    def test_unavailable_backend_after_retries_is_structured(self):
        fake = FakeNotebookLM(OK)
        fake.fail_with = [dict(UNAVAILABLE) for _ in range(5)]
        svc, _ = make_service(client=fake)
        r = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)
        self.assertEqual(r["error"]["code"], "BACKEND_UNAVAILABLE")
        self.assertTrue(r["error"]["retryable"])
        self.assertEqual(r["error"]["details"]["attempts"], 2)   # config default max_attempts=2
        self.assertEqual(r["notebooklm_calls"], 2)

    def test_status_probe_reports_unavailable(self):
        fake = FakeNotebookLM(OK)
        fake.fail_with = [{"status": "error", "error": "login required"}]
        svc, _ = make_service(client=fake)
        r = svc.call("standards_status", {"scope": ["notebooklm"], "probe_backend": True})
        self.assertEqual(r["status"], "DEGRADED")
        self.assertEqual(r["components"]["notebooklm"]["error"], "AUTH_REQUIRED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
