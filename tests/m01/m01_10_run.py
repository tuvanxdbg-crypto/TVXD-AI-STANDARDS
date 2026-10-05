#!/usr/bin/env python3
"""M01-10 (LLM part) runner: snapshot policy files, run `claude -p`, check the transcript.

Claude Code reads the injection source through the project MCP server
(.mcp.json, read-only gated) in dontAsk mode: only source_get_content is
pre-approved, everything else is refused without prompting and recorded.
The prompt goes through stdin so no shell (cmd.exe / PowerShell) parses it.
CLAUDE.md names this harness, identified by the prompt's first line, as the
single exception to the locked operating path (V-13).

Usage (from the repo root):
  uv run --no-project --python 3.11 tests/m01/m01_10_run.py --source-id <injection source id>
  uv run --no-project --python 3.11 tests/m01/m01_10_run.py --self-test   (offline harness check)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

from m01_console import safe_console

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CHECK = HERE / "m01_10_llm_check.py"
PROMPT = HERE / "fixtures" / "M01-10_prompt.txt"


def main() -> int:
    safe_console()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--source-id", help="NotebookLM source id of the injection test source")
    g.add_argument("--self-test", action="store_true",
                   help="use tests/m01/selftest_fake_notebooklm.py instead of NotebookLM (not acceptance evidence)")
    p.add_argument("--out", type=Path, default=HERE / "evidence" / "local")
    p.add_argument("--max-budget-usd", default="1")
    args = p.parse_args()

    claude = shutil.which("claude")
    if not claude:
        print("claude not found on PATH")
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    label = "selftest" if args.self_test else "notebooklm"

    if args.self_test:
        mcp_config = args.out / f"m01-10-selftest-{stamp}.mcp.json"
        mcp_config.write_text(json.dumps({"mcpServers": {"gemini-notebook-mcp": {
            "type": "stdio", "command": sys.executable,
            "args": [str(HERE / "selftest_fake_notebooklm.py")]}}}), encoding="utf-8")
        source_id = "selftest-injection-source"
    else:
        mcp_config = REPO / ".mcp.json"
        source_id = args.source_id

    baseline = args.out / f"m01-10-{label}-{stamp}.baseline.json"
    transcript = args.out / f"m01-10-{label}-{stamp}.transcript.jsonl"
    subprocess.run([sys.executable, str(CHECK), "--snapshot", str(baseline)], cwd=REPO, check=True)

    prompt = PROMPT.read_text(encoding="utf-8").replace("{SOURCE_ID}", source_id)
    cmd = [claude, "-p", "--output-format", "stream-json", "--verbose",
           "--permission-mode", "dontAsk",
           "--allowedTools", "mcp__gemini-notebook-mcp__source_get_content",
           "--max-budget-usd", args.max_budget_usd,
           "--mcp-config", str(mcp_config), "--strict-mcp-config"]
    with transcript.open("wb") as fh:
        rc = subprocess.run(cmd, input=prompt.encode("utf-8"), stdout=fh, stderr=subprocess.DEVNULL,
                            cwd=REPO, timeout=600).returncode
    print(f"claude exit={rc}  transcript={transcript}")

    result = subprocess.run([sys.executable, str(CHECK), str(transcript), str(baseline)], cwd=REPO)
    if args.self_test:
        print("NOTE: self-test validates the harness only; it is not M01-10 acceptance evidence.")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
