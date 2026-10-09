#!/usr/bin/env python3
"""M02 stage B under contract v2: preflight before and after a live run (docs/M02_PILOT_PLAN.md §6c).

Contract v2 (M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE) reads no local library file, so this preflight does not touch
the source root (`C:\\Vanban_XDCB`) or any document: no ACL check, no hash. That was the stage-A/B0/B2 preflight
(pilot_preflight.py), which a contract-v2 run no longer needs. Nothing is written except the summary file; no
network, no NotebookLM, no login state is read.

Checks (each PASS / FAIL):
  HEAD_IS_APPROVED           git HEAD equals --expect-head, the full SHA the owner approved for this run
  TREE_CLEAN                 `git status --porcelain` is empty (git-ignored local evidence does not count)
  COMMITTED_CONFIGS_DISABLED every committed tvxd.gateway.config/v1 file keeps notebooklm.mode disabled
  STAGE_B_SCOPE              pilot_stage_b.preconditions(): exactly the three pilot documents whitelisted, exactly the
                             pilot notebook whitelisted, each document mapped to one distinct source in that notebook,
                             the M01 injection source not mapped
  M01_SERVER_PIN             the project .mcp.json `gemini-notebook-mcp` entry still pins notebooklm-mcp-cli==0.15.1
                             through uvx and enables exactly the four M01 read tools
  TOKEN_NOT_ELEVATED, TOKEN_INTEGRITY_AT_MOST_MEDIUM, NO_ACL_BYPASS_PRIVILEGES
                             Windows only, the same token checks as pilot_preflight.py
Status: PASS only on Windows with every check PASS (exit 0); FAIL if any check fails (exit 1); NOT_A_LIVE_HOST off
Windows, where the token checks are NOT_APPLICABLE (exit 3); CANNOT_RUN when the inputs are unreadable (exit 2).
Output: tests/m02/evidence/local/stage-b-v2-preflight-<phase>-<ts>.summary.json (no SID, user name or path).

  uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z \\
      tests/m02/pilot_stage_b_v2_preflight.py --phase before --expect-head <approved full SHA>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import pilot_stage_b as sb  # noqa: E402
from gateway.adapters.notebooklm import M01_READ_TOOLS  # noqa: E402
from m02_surface import committed_configs_disabled  # noqa: E402

PIN = "notebooklm-mcp-cli==0.15.1"
SERVER = "gemini-notebook-mcp"


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=60,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def windows_token_facts() -> dict:
    """elevated, integrity_rid, integrity and held privilege names of this process (pilot_preflight.Win)."""
    import pilot_preflight as pf
    win = pf.Win()
    facts = win.token_facts(win.process_token())
    return {"elevated": facts["elevated"], "integrity_rid": facts["integrity_rid"], "integrity": facts["integrity"],
            "privileges": sorted(p["name"] for p in facts["privileges"])}


def check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "result": "PASS" if ok else "FAIL", "detail": detail}


def server_pin_problems(mcp_json: Path) -> list[str]:
    try:
        spec = json.loads(mcp_json.read_text(encoding="utf-8"))["mcpServers"][SERVER]
    except (OSError, ValueError, KeyError, TypeError):
        return [f"{SERVER} entry missing or unreadable"]
    problems = []
    if spec.get("command") != "uvx" or PIN not in (spec.get("args") or []):
        problems.append(f"not started as uvx --from {PIN}")
    enabled = str((spec.get("env") or {}).get("NOTEBOOKLM_ENABLED_TOOLS", ""))
    if sorted(t for t in enabled.split(",") if t) != sorted(M01_READ_TOOLS):
        problems.append("NOTEBOOKLM_ENABLED_TOOLS is not exactly the four M01 read tools")
    return problems


def run_checks(config: Path, expect_head: str, *, git_fn=git, configs_disabled=committed_configs_disabled,
               mcp_json: Path = REPO / ".mcp.json", token_facts=None) -> tuple[str, list[dict], dict]:
    """(status, checks, facts). token_facts: a callable returning the Windows token facts, or None off Windows."""
    head = git_fn("rev-parse", "HEAD")
    porcelain = git_fn("status", "--porcelain")
    checks = [check("HEAD_IS_APPROVED", bool(expect_head) and head == expect_head,
                    f"head={head} expected={expect_head}"),
              check("TREE_CLEAN", porcelain == "", "clean" if porcelain == "" else "uncommitted changes or git error"),
              check("COMMITTED_CONFIGS_DISABLED", configs_disabled(), "every committed Gateway config: mode disabled")]
    facts: dict = {"head": head}
    try:
        pre = sb.preconditions(config)
        facts.update(notebook=pre["notebook"], mapped_source_ids=pre["mapped_source_ids"],
                     index_sha256=pre["index_sha256"])
        checks.append(check("STAGE_B_SCOPE", True, f"3 documents, notebook {pre['notebook']}"))
    except Exception as e:  # noqa: BLE001 - Refused, or an unreadable / invalid config or INDEX
        checks.append(check("STAGE_B_SCOPE", False, f"{type(e).__name__}: {e}"))
    problems = server_pin_problems(mcp_json)
    checks.append(check("M01_SERVER_PIN", not problems, "; ".join(problems) or f"uvx {PIN}, four read tools"))
    if token_facts is None:
        for name in ("TOKEN_NOT_ELEVATED", "TOKEN_INTEGRITY_AT_MOST_MEDIUM", "NO_ACL_BYPASS_PRIVILEGES"):
            checks.append({"name": name, "result": "NOT_APPLICABLE", "detail": "not Windows"})
    else:
        t = token_facts()
        bad = sorted(set(t["privileges"]) & dangerous_privileges())
        checks += [check("TOKEN_NOT_ELEVATED", not t["elevated"], f"elevated={t['elevated']}"),
                   check("TOKEN_INTEGRITY_AT_MOST_MEDIUM", t["integrity_rid"] <= 0x2000, str(t["integrity"])),
                   check("NO_ACL_BYPASS_PRIVILEGES", not bad, ",".join(bad) or "none held")]
    if any(c["result"] == "FAIL" for c in checks):
        status = "FAIL"
    elif token_facts is None:
        status = "NOT_A_LIVE_HOST"
    else:
        status = "PASS"
    return status, checks, facts


def dangerous_privileges() -> set[str]:
    """The ACL-bypassing privileges of pilot_preflight.py (one definition for both preflights)."""
    import pilot_preflight as pf
    return set(pf.DANGEROUS_PRIVILEGES)


EXIT = {"PASS": 0, "FAIL": 1, "NOT_A_LIVE_HOST": 3}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=("before", "after"), required=True)
    ap.add_argument("--expect-head", required=True, help="the full commit SHA the owner approved for this run")
    ap.add_argument("--config", type=Path, default=sb.CONFIG)
    ap.add_argument("--out", type=Path, default=HERE / "evidence" / "local")
    args = ap.parse_args()
    started = dt.datetime.now(dt.timezone.utc)
    try:
        status, checks, facts = run_checks(args.config.resolve(), args.expect_head.strip(),
                                           token_facts=windows_token_facts if sys.platform == "win32" else None)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"status": "CANNOT_RUN", "reason": f"{type(e).__name__}: {e}"}, indent=2))
        return 2
    summary = {"check": f"m02-stage-b-v2-preflight-{args.phase}", "utc": started.isoformat(timespec="seconds"),
               "expect_head": args.expect_head.strip(), **facts, "python": platform.python_version(),
               "platform": platform.platform(), "status": status, "checks": checks,
               "local_library_accessed": False}
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"stage-b-v2-preflight-{args.phase}-{started.strftime('%Y%m%d-%H%M%S')}.summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(errors="backslashreplace")
    for c in checks:
        print(f"{c['result']:14} {c['name']:30} {c['detail']}")
    print(f"STAGE B v2 PREFLIGHT {args.phase.upper()}: {status}")
    print(f"[preflight-v2] summary (committable): {out}")
    return EXIT[status]


if __name__ == "__main__":
    sys.exit(main())
