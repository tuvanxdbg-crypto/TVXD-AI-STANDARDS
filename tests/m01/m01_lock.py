#!/usr/bin/env python3
"""M01 locked operating path for NotebookLM retrieval, plus Claude Code tool-surface checks.

The locked path starts Claude Code with:
  --permission-mode dontAsk      nothing outside the allow list runs, nothing prompts
  --tools=                       no built-in tools at all (no Bash, PowerShell, Read,
                                 Grep, Glob, Write, Edit, WebFetch ...). Written as one
                                 non-empty argument because Windows PowerShell 5.1 drops
                                 empty "" arguments to native programs.
  --allowedTools <4 tools>       the four approved NotebookLM MCP tools
  --mcp-config .mcp.json --strict-mcp-config
                                 only the pinned, gated server; user/local/plugin MCP
                                 servers and connectors are not loaded

Subcommands
  args                    print the locked argument list, one per line
                          (scripts/m01/m01-session.ps1 launches `claude` with it)
  surface --mode locked   start Claude Code with the locked arguments (-p, a one-word
                          prompt), read the system/init event and PASS only if the model
                          sees exactly the four approved tools and nothing else, served
                          by gemini-notebook-mcp alone
  surface --mode project  start Claude Code the way an ordinary session in this repo
                          starts (no --mcp-config: user, project, local MCP config load).
                          PASS only if no NotebookLM/Gemini MCP server or tool is visible,
                          i.e. NotebookLM is reachable only through the locked path
  setup-local             owner, once per machine: add gemini-notebook-mcp to
                          disabledMcpjsonServers in .claude/settings.local.json (git-ignored)
                          so ordinary sessions never load it. Without this, `claude -p`
                          loads the project .mcp.json server with no approval prompt.
                          The locked path is unaffected: --mcp-config is a separate source.

Evidence goes to tests/m01/evidence/local/ (git-ignored).

Usage (from the repo root):
  uv run --no-project --python 3.11 tests/m01/m01_lock.py surface --mode locked
  uv run --no-project --python 3.11 tests/m01/m01_lock.py surface --mode project
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from m01_console import safe_console

REPO = Path(__file__).resolve().parents[2]
SERVER = "gemini-notebook-mcp"
MCP_CONFIG = REPO / ".mcp.json"
APPROVED = [f"mcp__{SERVER}__{t}" for t in
            ("notebook_list", "notebook_get", "source_get_content", "notebook_query")]
NOTEBOOK_LIKE = re.compile(r"notebook|gemini|nlm", re.I)
REQUIRED_HELP = ("--tools", "--strict-mcp-config", "--mcp-config", "--allowedTools", "dontAsk")
MCP_TIMEOUT_MS = "120000"   # first uvx start may download Python 3.11 + dependencies


def locked_args() -> list[str]:
    return ["--permission-mode", "dontAsk",
            "--tools=",
            "--allowedTools", ",".join(APPROVED),
            "--mcp-config", str(MCP_CONFIG), "--strict-mcp-config"]


def claude_exe() -> str:
    exe = shutil.which("claude")
    if not exe:
        raise SystemExit("[m01_lock] claude not found on PATH")
    return exe


def check_flags(exe: str) -> list[str]:
    """Return required flags missing from this Claude Code version (fail closed if any)."""
    help_text = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=60).stdout
    return [f for f in REQUIRED_HELP if f not in help_text]


def capture_init(exe: str, extra: list[str]) -> tuple[dict | None, str]:
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--max-budget-usd", "0.2", *extra]
    env = dict(os.environ, MCP_TIMEOUT=os.environ.get("MCP_TIMEOUT", MCP_TIMEOUT_MS))
    proc = subprocess.run(cmd, input="Reply with the single word OK.".encode("utf-8"),
                          capture_output=True, cwd=REPO, env=env, timeout=300)
    init = None
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = ev
            break
    return init, proc.stderr.decode("utf-8", "replace")[-500:]


def surface(mode: str, out_dir: Path) -> int:
    exe = claude_exe()
    version = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    ev: dict = {"check": f"claude-code-tool-surface/{mode}", "claude_code": version,
                "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    missing = check_flags(exe)
    if missing:
        ev.update(status="FAIL", reason=f"this Claude Code lacks required flags {missing}; update Claude Code")
        return finish(ev, out_dir)

    init, stderr_tail = capture_init(exe, locked_args() if mode == "locked" else ["--permission-mode", "dontAsk"])
    if init is None:
        ev.update(status="FAIL", reason="no system/init event", stderr_tail=stderr_tail)
        return finish(ev, out_dir)

    tools = sorted(init.get("tools", []))
    servers = [{"name": s.get("name"), "status": s.get("status")} for s in init.get("mcp_servers", [])]
    ev["mcp_servers"] = servers

    if mode == "locked":
        extra = sorted(set(tools) - set(APPROVED))
        missing_tools = sorted(set(APPROVED) - set(tools))
        other_servers = [s for s in servers if s["name"] != SERVER]
        ours = [s for s in servers if s["name"] == SERVER]
        ok = (not extra and not missing_tools and not other_servers
              and len(ours) == 1 and ours[0]["status"] == "connected")
        ev.update(status="PASS" if ok else "FAIL", tools_visible_to_model=tools,
                  unexpected_tools=extra, missing_tools=missing_tools, other_servers=other_servers)
    else:
        nb_tools = [t for t in tools if t.startswith("mcp__") and NOTEBOOK_LIKE.search(t)]
        nb_servers = [s for s in servers if NOTEBOOK_LIKE.search(s["name"] or "")]
        ok = not nb_tools and not [s for s in nb_servers if s["status"] == "connected"]
        ev.update(status="PASS" if ok else "FAIL",
                  notebook_tools_visible=nb_tools, notebook_servers=nb_servers,
                  total_tools_visible=len(tools),
                  other_mcp_server_names=sorted(s["name"] for s in servers if s not in nb_servers))
        if not ok:
            ev["hint"] = ("NotebookLM tools are reachable in an ordinary session. For this project, decline "
                          "gemini-notebook-mcp (claude mcp reset-project-choices, then answer No) or list it in "
                          "disabledMcpjsonServers in .claude/settings.local.json; remove any other NotebookLM/"
                          "Gemini server from user/local scope for this project.")
    return finish(ev, out_dir)


def finish(ev: dict, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = ev["check"].split("/")[-1]
    out = out_dir / f"m01-tool-surface-{mode}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(ev, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(ev, indent=2, ensure_ascii=False))
    print(f"[m01_lock] evidence: {out}")
    return 0 if ev["status"] == "PASS" else 1


def setup_local() -> int:
    path = REPO / ".claude" / "settings.local.json"
    data: dict = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8-sig") or "{}")
    disabled = data.setdefault("disabledMcpjsonServers", [])
    if SERVER in disabled:
        print(f"[m01_lock] {path}: {SERVER} already in disabledMcpjsonServers")
        return 0
    disabled.append(SERVER)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"[m01_lock] {path}: added {SERVER} to disabledMcpjsonServers (other keys kept)")
    return 0


def main() -> int:
    safe_console()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("args")
    sub.add_parser("setup-local")
    s = sub.add_parser("surface")
    s.add_argument("--mode", choices=("locked", "project"), required=True)
    s.add_argument("--out", type=Path, default=REPO / "tests" / "m01" / "evidence" / "local")
    args = p.parse_args()
    if args.cmd == "args":
        print("\n".join(locked_args()))
        return 0
    if args.cmd == "setup-local":
        return setup_local()
    return surface(args.mode, args.out)


if __name__ == "__main__":
    sys.exit(main())
