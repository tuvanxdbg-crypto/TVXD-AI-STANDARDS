#!/usr/bin/env python3
"""Offline regressions for the stage-B runner tests/m02/pilot_stage_b.py (GPT_REVIEW_V1 at 32b8705).

Synthetic stand-in files and the fake NotebookLM backend only; nothing contacts Google.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import pilot_stage_b as sb  # noqa: E402


class StageBRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="m02-synb-")
        cls.root = Path(cls._tmp.name)
        subprocess.run([sys.executable, str(HERE / "make_pilot_synthetic.py"), str(cls.root / "syn")], check=True,
                       capture_output=True)
        cls.config = cls.root / "syn" / "gateway.pilot.stage-b.json"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def tearDown(self):
        sb.P11_EXTRA_INDEX_EDIT = None
        sb.Audit.FINALIZE_WAIT_S = 10.0

    def run_fake(self, scenario, config=None, prepare=None, slow_delay=1.5):
        made = []

        def make_client(slow=False):
            fake = sb.fake_client(scenario)
            fake.delay_s = slow_delay if slow else 0
            if prepare:
                prepare(fake)
            made.append(fake)
            return fake
        code, summary = sb.execute(config or self.config, make_client, kind=f"fake:{scenario}",
                                   out=self.root / "out")
        return code, summary, made

    def results(self, summary):
        return {c["id"]: c["result"] for c in summary["cases"]}

    def test_clean_run_audits_every_attempt_including_p8(self):
        code, s, made = self.run_fake("clean")
        self.assertEqual((code, s["status"]), (0, "PASS"))
        self.assertEqual(self.results(s), {"P5": "PASS", "P10": "PASS", "P6": "PASS", "P7": "PASS",
                                           "P11": "PASS", "P8": "PASS"})
        backend_calls = sum(len([c for c in f.calls if c[0] == "notebook_query"]) for f in made)
        self.assertEqual(s["attempt_count"], backend_calls)          # audit covers every call of every client
        self.assertEqual([a["client"] for a in s["notebook_query_attempts"]], ["main", "main", "p8", "p8"])
        expected = sorted(s["mapped_source_ids"].values())
        self.assertTrue(all(a["requested_source_ids"] == expected for a in s["notebook_query_attempts"]))
        self.assertEqual((s["injection_source_requested"], s["attempts_with_wrong_source_set"], s["source_gate"]),
                         (False, [], None))
        self.assertEqual(s["sent_to_backend_count"], 4)

    def test_mixed_run_p10b_and_p7_not_observed_without_old_evidence(self):
        code, s, _ = self.run_fake("mixed")
        self.assertEqual(code, 0)
        r = self.results(s)
        self.assertEqual((r["P10"], r["P6"], r["P7"], r["P11"], r["P8"]),
                         ("PASS", "NOT_OBSERVED", "NOT_OBSERVED", "NOT_OBSERVED", "PASS"))
        p10 = next(c for c in s["cases"] if c["id"] == "P10")
        self.assertEqual(p10["observed"]["outcome"], "OUT_OF_SCOPE_OBSERVED")
        self.assertFalse(s["injection_source_requested"])            # cited by the backend, never sent

    def test_first_fail_stops_before_any_further_call(self):
        code, s, made = self.run_fake("auth")
        self.assertEqual((code, s["status"], s["stopped_after"]), (1, "FAIL", "P5"))
        self.assertEqual(s["attempt_count"], 1)
        self.assertEqual(sum(len(f.calls) for f in made), 1)        # no P10/P6/P7/P11/P8 call happened
        self.assertEqual(self.results(s), {"P5": "FAIL", "P10": "NOT_RUN", "P6": "NOT_RUN", "P7": "NOT_RUN",
                                           "P11": "NOT_RUN", "P8": "NOT_RUN"})
        self.assertEqual(s["notebook_query_attempts"][0]["outcome"], "returned")

    def test_wrong_source_set_after_p5_is_blocked_before_transport_and_stops(self):
        # P11's temporary INDEX maps TCVN 5575 to the injection source: the attempt must never reach the backend.
        sb.P11_EXTRA_INDEX_EDIT = lambda t: t.replace("d54bb084-5c50-4cef-8979-6e909f791c1e", sb.INJECTION_SOURCE)
        code, s, made = self.run_fake("clean")
        self.assertEqual((code, s["status"], s["stopped_after"]), (1, "FAIL", "SOURCE_GATE"))
        self.assertIn("attempt 2", s["source_gate"])
        last = s["notebook_query_attempts"][-1]
        self.assertEqual((last["outcome"], last["sent_to_backend"]), ("blocked_wrong_source_set", False))
        self.assertIn(sb.INJECTION_SOURCE, last["requested_source_ids"])
        self.assertEqual(sum(len(f.calls) for f in made), 1)        # only P5 reached the backend
        self.assertEqual(len(made), 1)                               # the P8 client was never created
        r = self.results(s)
        self.assertEqual((r["P5"], r["P10"], r["P6"], r["P7"], r["P11"], r["P8"]),
                         ("PASS", "PASS", "PASS", "PASS", "NOT_RUN", "NOT_RUN"))
        self.assertEqual((s["injection_source_requested"], s["sent_to_backend_count"]), (True, 1))

    def test_timeout_attempt_has_a_terminal_outcome_with_code_and_timing(self):
        _, s, _ = self.run_fake("clean")
        self.assertNotIn("in_flight", [a["outcome"] for a in s["notebook_query_attempts"]])
        tight = s["notebook_query_attempts"][2]
        self.assertEqual((tight["client"], tight["caller_outcome"], tight["outcome"]),
                         ("p8", "ERROR:TIMEOUT", "returned_after_caller_timeout"))
        self.assertGreaterEqual(tight["elapsed_ms"], 1000)
        self.assertTrue(all("elapsed_ms" in a for a in s["notebook_query_attempts"]))

    def test_worker_outliving_finalize_fails_closed_and_snapshot_is_immutable(self):
        import time as _time
        sb.Audit.FINALIZE_WAIT_S = 0.3        # the P8 tight worker (4 s) outlives the finalize window
        code, s, made = self.run_fake("clean", slow_delay=4.0)
        self.assertEqual((code, s["status"]), (1, "FAIL"))
        tight = s["notebook_query_attempts"][2]
        self.assertEqual((tight["client"], tight["outcome"], tight["sent_to_backend"], tight["caller_outcome"]),
                         ("p8", "abandoned_unfinished", "not_confirmed", "ERROR:TIMEOUT"))
        self.assertEqual(s["unfinished_attempts"], [3])
        before_file = Path(s["summary_file"]).read_text(encoding="utf-8")
        frozen = json.dumps(s, sort_keys=True, ensure_ascii=False)
        calls = sum(len(f.calls) for f in made)
        _time.sleep(4.5)                      # let the abandoned worker finish
        self.assertEqual(Path(s["summary_file"]).read_text(encoding="utf-8"), before_file)
        self.assertEqual(json.dumps(s, sort_keys=True, ensure_ascii=False), frozen)
        self.assertEqual(sum(len(f.calls) for f in made), calls)   # no call after the snapshot

    def test_exception_attempt_has_a_terminal_outcome_and_stops(self):
        from gateway.errors import GatewayError

        def prepare(fake):
            fake.raise_with = [GatewayError("BACKEND_UNAVAILABLE", "fake transport failure", retryable=False)]
        code, s, made = self.run_fake("clean", prepare=prepare)
        self.assertEqual((code, s["stopped_after"]), (1, "P5"))
        (a,) = s["notebook_query_attempts"]
        self.assertEqual((a["outcome"], a["exception"], a["sent_to_backend"], a["caller_outcome"]),
                         ("exception", "BACKEND_UNAVAILABLE", "not_confirmed", "ERROR:BACKEND_UNAVAILABLE"))
        self.assertIn("elapsed_ms", a)
        self.assertEqual(sum(len(f.calls) for f in made), 1)

    def test_refuses_before_any_client_when_injection_source_is_mapped(self):
        bad = self.root / "bad"
        bad.mkdir(exist_ok=True)
        idx = (self.root / "syn" / "INDEX.pilot.stage-b.yaml").read_text(encoding="utf-8")
        (bad / "INDEX.yaml").write_text(idx.replace("8ccb8115-f552-4ecb-b42a-f0ee093f1d08", sb.INJECTION_SOURCE),
                                        encoding="utf-8")
        cfg = json.loads(self.config.read_text(encoding="utf-8"))
        cfg["index_path"] = str(bad / "INDEX.yaml")
        cfg["source_root"] = str(self.root / "syn" / "library")
        (bad / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        code, s, made = self.run_fake("clean", config=bad / "cfg.json")
        self.assertEqual((code, s["status"], made), (2, "REFUSED", []))

    def test_summary_carries_no_answer_or_passage_text(self):
        for scenario in ("clean", "mixed"):
            _, s, _ = self.run_fake(scenario)
            text = Path(s["summary_file"]).read_text(encoding="utf-8")
            for leak in ("câu trả lời giả lập", "chiếu sáng lớp học trường trung học.", "chỉ dẫn nhúng"):
                self.assertNotIn(leak, text, scenario)


if __name__ == "__main__":
    unittest.main(verbosity=2)
