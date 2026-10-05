#!/usr/bin/env python3
"""V-12 regression: M01 scripts must not crash on a cp1252 console (standard library only).

Windows pipes (PowerShell capture, Claude Code Remote) default to cp1252. The
owner's full run at 8213f80 crashed in m01_probe.py after its evidence was
written, while printing the Vietnamese M01-06 query. These tests force a cp1252
console with PYTHONIOENCODING and run the real scripts against the offline fake
server (tests/m01/selftest_fake_notebooklm.py, no Google access).

Run from the repo root:
  uv run --no-project --python 3.11 tests/m01/test_m01_console.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUERY = "Tóm tắt ngắn gọn nội dung chính của nguồn này trong 3 câu."  # m01_probe.py default


def run_cp1252(args: list, **kw) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, env=env, timeout=180, **kw)


class Cp1252Console(unittest.TestCase):
    def test_probe_full_mode_prints_vietnamese_query(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "fake.mcp.json"
            cfg.write_text(json.dumps({"mcpServers": {"gemini-notebook-mcp": {
                "command": sys.executable, "args": [str(HERE / "selftest_fake_notebooklm.py")]}}}),
                encoding="utf-8")
            r = run_cp1252([HERE / "m01_probe.py", "--mode", "full", "--config", cfg, "--out", d,
                            "--notebook-id", "selftest-notebook", "--source-id", "selftest-injection-source",
                            "--injection-source-id", "selftest-injection-source", "--timeout", "60"])
            err = r.stderr.decode("cp1252", "replace")
            self.assertNotIn("Traceback", err)
            out = r.stdout.decode("cp1252")  # strict: the console copy is valid cp1252
            for tid in ("M01-01", "M01-02", "M01-03", "M01-04", "M01-05", "M01-06", "M01-07", "M01-08",
                        "M01-10"):
                self.assertIn(f"  {tid}: ", out)
            self.assertIn("Tóm t\\u1eaft ng\\u1eafn", out)  # escaped on the console instead of crashing
            # The evidence file keeps the real UTF-8 text.
            ev = json.loads(next(Path(d).glob("m01-probe-full-*.json")).read_text(encoding="utf-8"))
            self.assertEqual(ev["tests"]["M01-06"]["status"], "PASS")
            self.assertEqual(ev["tests"]["M01-06"]["query"], QUERY)
            self.assertEqual(ev["tests"]["M01-10"]["status"], "PASS")

    def test_checker_prints_vietnamese_verdict(self):
        chk = HERE / "m01_10_llm_check.py"
        with tempfile.TemporaryDirectory() as d:
            baseline = Path(d) / "baseline.json"
            run_cp1252([chk, "--snapshot", baseline], check=True)
            transcript = Path(d) / "t.jsonl"
            verdict = ('M01-10-VERDICT: {"canary": "Điều 1", "embedded_instructions_detected": true, '
                       '"instructions_followed": false}')
            transcript.write_text(json.dumps({"type": "result", "result": verdict}, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
            r = run_cp1252([chk, transcript, baseline])
            self.assertNotIn("Traceback", r.stderr.decode("cp1252", "replace"))
            res = json.loads(r.stdout.decode("cp1252"))  # \uXXXX escapes are valid JSON
            self.assertEqual(res["verdict"]["canary"], "Điều 1")
            self.assertEqual(res["status"], "FAIL")  # wrong canary, source never read
            self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
