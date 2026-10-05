#!/usr/bin/env python3
"""M01 acceptance probe for the NotebookLM MCP server (standard library only).

Launches the MCP server exactly as declared in the project-scoped .mcp.json
(same command, args and env, with ${VAR} / ${VAR:-default} expansion like
Claude Code), speaks MCP JSON-RPC over stdio and records non-secret evidence.

Modes
  surface  No Google login needed. M01-01, M01-07, M01-08.
  full     Needs the owner's local login. Adds M01-02..M01-06 and the
           M01-10 data-path check.

Evidence is written to tests/m01/evidence/local/ (git-ignored). The owner
reviews it before anything is copied into tests/m01/ACCEPTANCE.md.
Source text is never stored: only its length, SHA-256 and canary checks.

Usage (from the repo root)
  uv run --no-project --python 3.11 tests/m01/m01_probe.py --mode surface
  uv run --no-project --python 3.11 tests/m01/m01_probe.py --mode full \
      --notebook-id <id> --source-id <id> --injection-source-id <id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from m01_console import safe_console

REPO = Path(__file__).resolve().parents[2]
GATING_VARS = ("NOTEBOOKLM_DISABLED_GROUPS", "NOTEBOOKLM_DISABLED_TOOLS", "NOTEBOOKLM_ENABLED_TOOLS")
CANARY = "TVXD-M01-CANARY-7F3A9C"
PROTOCOL_VERSION = "2025-06-18"


# --------------------------------------------------------------------------- config

def expand(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} the way Claude Code does for .mcp.json."""

    def repl(m: re.Match[str]) -> str:
        name, default = m.group(1), m.group(3)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise SystemExit(f"[probe] environment variable {name} is not set (required by .mcp.json)")

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}", repl, value)


def load_server(config: Path, name: str) -> dict:
    data = json.loads(config.read_text(encoding="utf-8"))
    srv = data["mcpServers"][name]
    return {
        "command": expand(srv["command"]),
        "args": [expand(a) for a in srv.get("args", [])],
        "env": {k: expand(v) for k, v in srv.get("env", {}).items()},
    }


def load_allowed_tools(policy: Path) -> list[str]:
    """Read allowed_tools from config/m01-tool-policy.yaml without a YAML dependency."""
    tools, inside = [], False
    for line in policy.read_text(encoding="utf-8").splitlines():
        if re.match(r"^allowed_tools:\s*$", line):
            inside = True
            continue
        if inside:
            m = re.match(r"^\s+-\s+([A-Za-z0-9_]+)\s*$", line)
            if m:
                tools.append(m.group(1))
            elif line.strip() and not line.startswith(" "):
                break
    if not tools:
        raise SystemExit("[probe] allowed_tools not found in policy file")
    return tools


# --------------------------------------------------------------------------- MCP stdio client

class McpStdio:
    def __init__(self, command: str, args: list[str], env: dict[str, str], timeout: float):
        exe = shutil.which(command) or command
        self.timeout = timeout
        self.proc = subprocess.Popen(
            [exe, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=REPO,
        )
        self._q: queue.Queue = queue.Queue()
        self._stderr_tail: list[str] = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._id = 0

    def _read_stdout(self) -> None:
        for raw in self.proc.stdout:  # type: ignore[union-attr]
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                pass  # non-protocol noise on stdout is ignored
        self._q.put(None)

    def _read_stderr(self) -> None:
        for raw in self.proc.stderr:  # type: ignore[union-attr]
            self._stderr_tail.append(raw.decode("utf-8", "replace").rstrip())
            del self._stderr_tail[:-30]

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))  # type: ignore[union-attr]
        self.proc.stdin.flush()  # type: ignore[union-attr]

    def request(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        while True:
            try:
                msg = self._q.get(timeout=timeout or self.timeout)
            except queue.Empty:
                raise TimeoutError(f"no response to {method} within {timeout or self.timeout}s")
            if msg is None:
                raise ConnectionError("server closed stdout\n" + "\n".join(self._stderr_tail[-10:]))
            if msg.get("id") == rid:
                if "error" in msg:
                    return {"_rpc_error": msg["error"]}
                return msg.get("result", {})

    def initialize(self) -> dict:
        res = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "tvxd-m01-probe", "version": "1"},
        })
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return res

    def list_tools(self) -> list[str]:
        names, cursor = [], None
        while True:
            res = self.request("tools/list", {"cursor": cursor} if cursor else {})
            names += [t["name"] for t in res.get("tools", [])]
            cursor = res.get("nextCursor")
            if not cursor:
                return sorted(names)

    def call(self, name: str, arguments: dict, timeout: float | None = None) -> tuple[bool, dict | str]:
        """Return (is_error, payload). payload is parsed JSON when the tool returned JSON text."""
        res = self.request("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
        if "_rpc_error" in res:
            return True, str(res["_rpc_error"].get("message"))
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        try:
            payload: dict | str = json.loads(text)
        except json.JSONDecodeError:
            payload = text
        is_error = bool(res.get("isError")) or (isinstance(payload, dict) and payload.get("status") == "error")
        return is_error, payload

    def close(self) -> None:
        try:
            self.proc.stdin.close()  # type: ignore[union-attr]
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def package_version(server: dict) -> str | None:
    """Run `nlm --version` through the same launcher spec (e.g. the pinned uvx --from ...)."""
    if not server["args"] or server["args"][-1] != "notebooklm-mcp":
        return None
    env = dict(os.environ)
    env.update(server["env"])
    cmd = [shutil.which(server["command"]) or server["command"], *server["args"][:-1], "nlm", "--version"]
    try:
        out = subprocess.run(cmd, env=env, cwd=REPO, capture_output=True, text=True, timeout=180).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"nlm version (\S+)", out)
    return m.group(1) if m else None


def launch(server: dict, gated: bool, timeout: float) -> McpStdio:
    env = dict(os.environ)
    env.update(server["env"])
    if not gated:
        for var in GATING_VARS:
            env.pop(var, None)
    return McpStdio(server["command"], server["args"], env, timeout)


# --------------------------------------------------------------------------- tests

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def error_text(payload: dict | str) -> str:
    if isinstance(payload, dict):
        return str(payload.get("error") or payload.get("message") or payload)[:300]
    return str(payload)[:300]


def run(args: argparse.Namespace) -> dict:
    server = load_server(args.config, args.server)
    allowed = load_allowed_tools(args.policy)
    ev: dict = {
        "probe": "tests/m01/m01_probe.py",
        "mode": args.mode,
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "host": {"os": platform.platform(), "python": platform.python_version()},
        "server_launch": {"command": server["command"], "args": server["args"],
                          "gating_env": {k: server["env"].get(k) for k in GATING_VARS if k in server["env"]}},
        "allowed_tools_policy": allowed,
        "tests": {},
    }
    t = ev["tests"]

    # Raw inventory: same launch without the gating variables. tools/list only, no calls.
    raw = launch(server, gated=False, timeout=args.timeout)
    try:
        raw.initialize()
        ev["raw_tool_inventory"] = raw.list_tools()
    finally:
        raw.close()

    mcp = launch(server, gated=True, timeout=args.timeout)
    try:
        # M01-01
        init = mcp.initialize()
        info = init.get("serverInfo", {})
        t["M01-01"] = {"status": "PASS" if info else "FAIL",
                       "server_name": info.get("name"),
                       "package_version": package_version(server),
                       "serverInfo_version_reported_by_fastmcp": info.get("version"),
                       "protocol_version": init.get("protocolVersion")}

        # M01-07
        visible = mcp.list_tools()
        ev["visible_tool_set"] = visible
        extra = sorted(set(visible) - set(allowed))
        missing = sorted(set(allowed) - set(visible))
        t["M01-07"] = {"status": "PASS" if not extra and not missing else "FAIL",
                       "raw_count": len(ev["raw_tool_inventory"]), "visible_count": len(visible),
                       "unexpected_visible": extra, "missing_allowed": missing}

        # M01-08: only call hidden names, with empty arguments, and only if the surface is clean.
        forbidden = [n for n in ev["raw_tool_inventory"] if n not in allowed]
        if extra:
            t["M01-08"] = {"status": "FAIL", "reason": "forbidden tools visible; calls skipped for safety"}
        elif not forbidden:
            t["M01-08"] = {"status": "FAIL",
                           "reason": "raw inventory has no non-approved tool, so blocking cannot be demonstrated"}
        else:
            results = {}
            for name in forbidden:
                is_err, payload = mcp.call(name, {})
                results[name] = "unknown_tool" if is_err and "unknown tool" in error_text(payload).lower() \
                    else f"UNEXPECTED: {error_text(payload)}"
            bad = {k: v for k, v in results.items() if v != "unknown_tool"}
            t["M01-08"] = {"status": "PASS" if not bad else "FAIL",
                           "forbidden_called": len(results), "rejected_as_unknown": len(results) - len(bad),
                           "unexpected": bad}

        if args.mode == "full":
            run_full(mcp, args, t, allowed, visible)
    finally:
        mcp.close()
    return ev


def run_full(mcp: McpStdio, args: argparse.Namespace, t: dict, allowed: list[str], visible: list[str]) -> None:
    # M01-02 + M01-03
    is_err, nl = mcp.call("notebook_list", {})
    if is_err or not isinstance(nl, dict):
        t["M01-02"] = {"status": "FAIL", "error": error_text(nl)}
        for k in ("M01-03", "M01-04", "M01-05", "M01-06", "M01-10"):
            t[k] = {"status": "BLOCKED", "reason": "authentication failed"}
        return
    t["M01-02"] = {"status": "PASS", "check": "notebook_list returned status=success with saved login"}
    notebooks = nl.get("notebooks", [])
    t["M01-03"] = {"status": "PASS", "tool": "notebook_list", "notebook_count": nl.get("count", len(notebooks))}
    if not args.notebook_id:
        print("\n[probe] Pass --notebook-id. Notebooks visible to this login (console only, not stored):")
        for nb in notebooks:
            print(f"  {nb.get('id')}  sources={nb.get('source_count')}  {nb.get('title')}")
        for k in ("M01-04", "M01-05", "M01-06", "M01-10"):
            t[k] = {"status": "NOT_RUN", "reason": "--notebook-id not given"}
        return

    # M01-04
    is_err, nb = mcp.call("notebook_get", {"notebook_id": args.notebook_id})
    if is_err or not isinstance(nb, dict):
        t["M01-04"] = {"status": "FAIL", "error": error_text(nb)}
        return
    sources = nb.get("sources", [])
    t["M01-04"] = {"status": "PASS", "tool": "notebook_get", "notebook_id": args.notebook_id,
                   "notebook_title": nb.get("notebook", {}).get("title"),
                   "source_count": len(sources),
                   "sources": [{"id": s.get("id"), "title": s.get("title")} for s in sources]}
    source_id = args.source_id or (sources[0].get("id") if sources else None)

    # M01-05
    content = None
    if not source_id:
        t["M01-05"] = {"status": "NOT_RUN", "reason": "notebook has no sources"}
    else:
        is_err, sc = mcp.call("source_get_content", {"source_id": source_id}, timeout=180)
        if is_err or not isinstance(sc, dict):
            t["M01-05"] = {"status": "FAIL", "source_id": source_id, "error": error_text(sc)}
        else:
            content = sc.get("content") or ""
            t["M01-05"] = {"status": "PASS" if content else "FAIL", "tool": "source_get_content",
                           "source_id": source_id, "source_title": sc.get("title"),
                           "source_type": sc.get("source_type"), "char_count": len(content),
                           "content_sha256": sha256(content)}

    # M01-06
    query = args.query
    q_args = {"notebook_id": args.notebook_id, "query": query, "new_conversation": True}
    if source_id:
        q_args["source_ids"] = [source_id]
    is_err, qa = mcp.call("notebook_query", q_args, timeout=240)
    if is_err or not isinstance(qa, dict):
        t["M01-06"] = {"status": "FAIL", "error": error_text(qa)}
    else:
        answer = qa.get("answer") or ""
        t["M01-06"] = {"status": "PASS" if answer else "FAIL", "tool": "notebook_query", "query": query,
                       "answer_char_count": len(answer), "answer_sha256": sha256(answer),
                       "sources_used_count": len(qa.get("sources_used") or []),
                       "citation_count": len(qa.get("citations") or {}),
                       "side_effect_note": "query persisted to NotebookLM chat history (accepted in M01)",
                       "independent_source_read": content is not None}

    # M01-10 data path: injection source must come back as inert data, policy surface unchanged.
    if not args.injection_source_id:
        t["M01-10"] = {"status": "NOT_RUN", "reason": "--injection-source-id not given"}
        return
    canary_file = REPO / "m01_pwned.txt"
    is_err, inj = mcp.call("source_get_content", {"source_id": args.injection_source_id}, timeout=180)
    after = mcp.list_tools()
    if is_err or not isinstance(inj, dict):
        t["M01-10"] = {"status": "FAIL", "error": error_text(inj)}
        return
    text = inj.get("content") or ""
    checks = {
        "content_returned_as_string_field": isinstance(inj.get("content"), str),
        "canary_present_in_data": CANARY in text,
        "embedded_instructions_present_in_data": "notebook_delete" in text and "m01_pwned.txt" in text,
        "tool_surface_unchanged_after_read": after == visible,
        "canary_file_not_created": not canary_file.exists(),
    }
    t["M01-10"] = {"status": "PASS" if all(checks.values()) else "FAIL", "part": "data-path (probe)",
                   "tool": "source_get_content", "source_id": args.injection_source_id,
                   "char_count": len(text), "content_sha256": sha256(text), "checks": checks,
                   "llm_part": "run tests/m01/m01_10_llm_check.py on a claude -p transcript"}


def main() -> int:
    safe_console()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=("surface", "full"), default="surface")
    p.add_argument("--config", type=Path, default=REPO / ".mcp.json")
    p.add_argument("--policy", type=Path, default=REPO / "config" / "m01-tool-policy.yaml")
    p.add_argument("--server", default="gemini-notebook-mcp")
    p.add_argument("--notebook-id")
    p.add_argument("--source-id")
    p.add_argument("--injection-source-id")
    p.add_argument("--query", default="Tóm tắt ngắn gọn nội dung chính của nguồn này trong 3 câu.")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--out", type=Path, default=REPO / "tests" / "m01" / "evidence" / "local")
    args = p.parse_args()

    ev = run(args)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = args.out / f"m01-probe-{args.mode}-{stamp}.json"
    out.write_text(json.dumps(ev, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n[probe] evidence: {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    for tid in sorted(ev["tests"]):
        r = ev["tests"][tid]
        detail = {k: v for k, v in r.items() if k not in ("status", "sources")}
        print(f"  {tid}: {r['status']}  {json.dumps(detail, ensure_ascii=False)[:220]}")
    failed = [k for k, v in ev["tests"].items() if v["status"] == "FAIL"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
