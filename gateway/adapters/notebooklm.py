"""NotebookLM semantic adapter behind a backend interface.

The adapter only ever uses the four read tools accepted in M01 (notebook_list,
notebook_get, source_get_content, notebook_query). Raw NotebookLM tools are never
exposed through the public Gateway; callers see only normalized evidence.

Clients:
  * any object implementing NotebookLMClient (tests use a fake backend);
  * McpStdioNotebookLMClient: launches the M01 gated server from the project
    .mcp.json, refuses to proceed unless tools/list is exactly the four approved
    tools, and refuses to call any other tool name. A process is used only after
    initialize and that surface check both succeeded; any startup failure kills it.
    Not used in the offline round (config mode "disabled"); enabling it needs the
    live-pilot review.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..errors import GatewayError
from ..retry import call_with_retry

M01_READ_TOOLS = ("notebook_list", "notebook_get", "source_get_content", "notebook_query")


class NotebookLMClient(Protocol):
    def notebook_list(self) -> dict: ...
    def notebook_get(self, notebook_id: str) -> dict: ...
    def source_get_content(self, source_id: str) -> dict: ...
    def notebook_query(self, notebook_id: str, query: str, source_ids: list[str]) -> dict: ...


@dataclass(frozen=True)
class Citation:
    source_id: str
    passage: str | None


@dataclass
class SemanticResult:
    notebook_id: str
    answer: str
    citations: list[Citation]
    dropped_source_ids: list[str] = field(default_factory=list)


def classify_backend_error(message: str) -> GatewayError:
    """Map a backend error text to the taxonomy without echoing it verbatim."""
    m = message.lower()
    if re.search(r"auth|login|sign.?in|expired|cookie|credential", m):
        return GatewayError("AUTH_REQUIRED", "NotebookLM needs the owner to sign in (m01-login.ps1)")
    if re.search(r"timeout|timed out", m):
        return GatewayError("TIMEOUT", "NotebookLM call timed out", retryable=True)
    if re.search(r"rate|quota|unavailable|503|502|temporar|connection", m):
        return GatewayError("BACKEND_UNAVAILABLE", "NotebookLM temporarily unavailable", retryable=True)
    return GatewayError("BACKEND_UNAVAILABLE", "NotebookLM returned an error", retryable=False)


def _parse_citations(result: dict) -> list[Citation]:
    out: list[Citation] = []
    raw = result.get("citations")
    items = raw.values() if isinstance(raw, dict) else (raw or [])
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("source_id"), str):
            passage = item.get("passage") or item.get("cited_text") or item.get("text")
            out.append(Citation(item["source_id"], passage if isinstance(passage, str) else None))
    cited = {c.source_id for c in out}
    for sid in result.get("sources_used") or []:
        if isinstance(sid, str) and sid not in cited:
            out.append(Citation(sid, None))
    return out


class NotebookLMAdapter:
    name = "notebooklm"

    def __init__(self, client: NotebookLMClient, *, timeout_s: float, max_attempts: int, total_budget_s: float,
                 backoff_s: float = 0.5):
        self.client = client
        self.timeout_s, self.max_attempts, self.total_budget_s = timeout_s, max_attempts, total_budget_s
        self.backoff_s = backoff_s
        self.calls = 0
        self.last_error: str | None = None

    def _call(self, fn):
        def attempt():
            self.calls += 1
            result = fn()
            if not isinstance(result, dict):
                raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM returned a non-object result")
            if result.get("status") == "error":  # classified inside the retry loop: only transient ones retry
                raise classify_backend_error(str(result.get("error") or result.get("message") or ""))
            return result
        try:
            result = call_with_retry(attempt, timeout_s=self.timeout_s, max_attempts=self.max_attempts,
                                     total_budget_s=self.total_budget_s, backoff_s=self.backoff_s)
        except GatewayError as e:
            self.last_error = e.code
            raise
        self.last_error = None
        return result

    def query(self, notebook_id: str, query: str, source_ids: list[str]) -> SemanticResult:
        """Semantic query restricted to source_ids. Citations outside source_ids are dropped."""
        if not source_ids:
            raise GatewayError("SOURCE_NOT_ALLOWED", "no whitelisted NotebookLM sources to query")
        result = self._call(lambda: self.client.notebook_query(notebook_id, query, list(source_ids)))
        allowed = set(source_ids)
        kept, dropped = [], []
        for c in _parse_citations(result):
            (kept if c.source_id in allowed else dropped).append(c)
        answer = result.get("answer") if isinstance(result.get("answer"), str) else ""
        return SemanticResult(notebook_id, answer, kept, sorted({c.source_id for c in dropped}))

    def probe(self) -> dict:
        result = self._call(self.client.notebook_list)
        return {"notebooks": len(result.get("notebooks") or [])}

    def status(self) -> dict:
        return {"state": "ok" if self.last_error is None else "degraded", "calls": self.calls,
                "last_error": self.last_error}


# ---------------------------------------------------------------------------- MCP stdio transport

class McpStdioNotebookLMClient:
    """Minimal MCP stdio client for the M01 gated server (four read tools only, fail closed)."""

    PROTOCOL_VERSION = "2025-06-18"

    def __init__(self, mcp_config: Path, server: str = "gemini-notebook-mcp", start_timeout_s: float = 120.0):
        """start_timeout_s bounds each startup step (initialize, tools/list)."""
        cfg = json.loads(Path(mcp_config).read_text(encoding="utf-8"))
        try:
            spec = cfg["mcpServers"][server]
        except KeyError:
            raise GatewayError("BACKEND_UNAVAILABLE", f"server {server} not found in MCP config") from None
        self._spec = {"command": _expand(spec["command"]), "args": [_expand(a) for a in spec.get("args", [])],
                      "env": {k: _expand(v) for k, v in spec.get("env", {}).items()}}
        self._start_timeout = start_timeout_s
        self._proc: subprocess.Popen | None = None
        self._q: queue.Queue = queue.Queue()
        self._id = 0
        self._lock = threading.Lock()
        self._ready = False   # True only after initialize + exact tools/list check on the current process

    def _start(self) -> None:
        if self._ready and self._proc and self._proc.poll() is None:
            return
        self._terminate()     # a dead process, or a live one that never passed the startup checks
        env = dict(os.environ, **self._spec["env"])
        exe = shutil.which(self._spec["command"]) or self._spec["command"]
        try:
            proc = subprocess.Popen([exe, *self._spec["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, env=env)
        except OSError:
            raise GatewayError("BACKEND_UNAVAILABLE", "cannot start the NotebookLM MCP server") from None
        self._proc, self._q = proc, queue.Queue()
        threading.Thread(target=self._reader, args=(proc, self._q), daemon=True).start()
        try:
            self._request("initialize", {"protocolVersion": self.PROTOCOL_VERSION, "capabilities": {},
                                         "clientInfo": {"name": "tvxd-standards-gateway", "version": "0.1.0"}},
                          timeout=self._start_timeout)
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools = sorted(str(t.get("name")) for t in
                           self._request("tools/list", {}, timeout=self._start_timeout).get("tools", []))
            if tools != sorted(M01_READ_TOOLS):
                raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM server tool surface is not exactly the four "
                                   "M01-approved read tools; refusing to use it", details={"visible_tools": len(tools)})
        except BaseException:
            self._terminate()
            raise
        self._ready = True

    @staticmethod
    def _reader(proc: subprocess.Popen, q: queue.Queue) -> None:
        # Bound to one process and its queue, so output of a replaced process never reaches a new one.
        assert proc.stdout
        try:
            for raw in proc.stdout:
                try:
                    q.put(json.loads(raw.decode("utf-8", "replace")))
                except json.JSONDecodeError:
                    continue
        except (OSError, ValueError):
            pass
        q.put(None)

    def _send(self, msg: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    def _request(self, method: str, params: dict, timeout: float) -> dict:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            try:
                msg = self._q.get(timeout=timeout)
            except queue.Empty:
                raise GatewayError("TIMEOUT", f"NotebookLM MCP {method} timed out", retryable=True) from None
            if msg is None:
                raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM MCP server exited", retryable=True)
            if msg.get("id") == rid:
                if "error" in msg:
                    raise classify_backend_error(str(msg["error"].get("message", "")))
                return msg.get("result", {})

    def _tool(self, name: str, arguments: dict, timeout: float = 240.0) -> dict:
        if name not in M01_READ_TOOLS:
            raise GatewayError("SOURCE_NOT_ALLOWED", f"tool {name!r} is not an M01-approved read tool")
        with self._lock:
            self._start()
            res = self._request("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"status": "error", "error": "non-JSON tool result"}
        if res.get("isError") and isinstance(payload, dict):
            payload.setdefault("status", "error")
        return payload if isinstance(payload, dict) else {"status": "error", "error": "unexpected result"}

    def notebook_list(self) -> dict:
        return self._tool("notebook_list", {})

    def notebook_get(self, notebook_id: str) -> dict:
        return self._tool("notebook_get", {"notebook_id": notebook_id})

    def source_get_content(self, source_id: str) -> dict:
        return self._tool("source_get_content", {"source_id": source_id})

    def notebook_query(self, notebook_id: str, query: str, source_ids: list[str]) -> dict:
        return self._tool("notebook_query", {"notebook_id": notebook_id, "query": query,
                                             "source_ids": source_ids, "new_conversation": True})

    def _terminate(self) -> None:
        """Kill the current process (startup failure or replacement) and forget it."""
        self._ready = False
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        for stream in (proc.stdin, proc.stdout):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass

    def close(self) -> None:
        self._ready = False
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                self._proc.kill()
                self._proc.wait(timeout=10)
            if self._proc.stdout:
                self._proc.stdout.close()
            self._proc = None


def _expand(value: str) -> str:
    def repl(m: re.Match[str]) -> str:
        name, default = m.group(1), m.group(3)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise GatewayError("BACKEND_UNAVAILABLE", f"MCP config needs environment variable {name}")
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}", repl, value)
