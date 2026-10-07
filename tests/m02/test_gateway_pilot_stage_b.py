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

    def run_fake(self, scenario, config=None):
        made = []

        def make_client(slow=False):
            fake = sb.fake_client(scenario)
            fake.delay_s = 1.5 if slow else 0
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
        self.assertTrue(all(a["sent_source_ids"] == expected for a in s["notebook_query_attempts"]))
        self.assertEqual((s["injection_source_sent"], s["attempts_with_wrong_source_set"]), (False, []))

    def test_mixed_run_p10b_and_p7_not_observed_without_old_evidence(self):
        code, s, _ = self.run_fake("mixed")
        self.assertEqual(code, 0)
        r = self.results(s)
        self.assertEqual((r["P10"], r["P6"], r["P7"], r["P11"], r["P8"]),
                         ("PASS", "NOT_OBSERVED", "NOT_OBSERVED", "NOT_OBSERVED", "PASS"))
        p10 = next(c for c in s["cases"] if c["id"] == "P10")
        self.assertEqual(p10["observed"]["outcome"], "OUT_OF_SCOPE_OBSERVED")
        self.assertFalse(s["injection_source_sent"])                 # cited by the backend, never sent

    def test_first_fail_stops_before_any_further_call(self):
        code, s, made = self.run_fake("auth")
        self.assertEqual((code, s["status"], s["stopped_after"]), (1, "FAIL", "P5"))
        self.assertEqual(s["attempt_count"], 1)
        self.assertEqual(sum(len(f.calls) for f in made), 1)        # no P10/P6/P7/P11/P8 call happened
        self.assertEqual(self.results(s), {"P5": "FAIL", "P10": "NOT_RUN", "P6": "NOT_RUN", "P7": "NOT_RUN",
                                           "P11": "NOT_RUN", "P8": "NOT_RUN"})
        self.assertEqual(s["notebook_query_attempts"][0]["outcome"], "returned")

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
