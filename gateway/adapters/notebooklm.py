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
    Every wait uses one absolute deadline per request (notifications do not extend
    it), bounded by the retry attempt's Deadline: an expired or cancelled attempt
    never sends, and a request that times out in flight is cancelled and its
    process retired, so no late work of a timed-out attempt remains. Writes to the
    server's stdin go through a per-process writer thread, so a server that stops
    reading can never block the caller past its deadline; teardown kills the process
    first and never waits on that pipe.
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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..errors import GatewayError
from ..retry import Deadline, call_with_retry, current_deadline

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

class _WriteItem:
    __slots__ = ("data", "done", "error")

    def __init__(self, data: bytes):
        self.data, self.done, self.error = data, threading.Event(), False


class _StdinWriter:
    """Owns one process's stdin. Callers wait for a write with a deadline instead of blocking in it."""

    def __init__(self, stream):
        self._stream = stream
        self._q: queue.Queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True, name="gateway-mcp-stdin")
        self.thread.start()

    def submit(self, data: bytes) -> _WriteItem:
        item = _WriteItem(data)
        self._q.put(item)
        return item

    def stop(self) -> None:
        self._q.put(None)

    def _run(self) -> None:
        broken = False
        while True:
            item = self._q.get()
            if item is None:
                return
            if not broken:
                try:
                    self._stream.write(item.data)
                    self._stream.flush()
                except (OSError, ValueError):   # process killed or pipe closed: fail this and later items
                    broken = True
            item.error = broken
            item.done.set()


class McpStdioNotebookLMClient:
    """Minimal MCP stdio client for the M01 gated server (four read tools only, fail closed)."""

    PROTOCOL_VERSION = "2025-06-18"
    POLL_S = 0.05   # how often a waiting request re-checks cancellation of its attempt
    CANCEL_NOTICE_S = 0.05   # at most this long to hand notifications/cancelled to a live writer

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
        self._writer: _StdinWriter | None = None

    @staticmethod
    def _bounded(timeout: float, dl: Deadline | None) -> float:
        """Step timeout, never beyond the attempt's deadline."""
        return timeout if dl is None else min(timeout, dl.remaining())

    def _start(self, dl: Deadline | None = None) -> None:
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
        self._writer = _StdinWriter(proc.stdin)
        threading.Thread(target=self._reader, args=(proc, self._q), daemon=True).start()
        try:
            self._request("initialize", {"protocolVersion": self.PROTOCOL_VERSION, "capabilities": {},
                                         "clientInfo": {"name": "tvxd-standards-gateway", "version": "0.1.0"}},
                          timeout=self._bounded(self._start_timeout, dl), dl=dl)
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"},
                       time.monotonic() + self._bounded(self._start_timeout, dl), dl)
            tools = sorted(str(t.get("name")) for t in self._request(
                "tools/list", {}, timeout=self._bounded(self._start_timeout, dl), dl=dl).get("tools", []))
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

    def _send(self, msg: dict, deadline: float, dl: Deadline | None = None, request_id: int | None = None) -> None:
        """Hand one message to the writer thread and wait for it until `deadline` (absolute, monotonic).

        A server that stops reading stdin cannot hold the caller: on expiry or cancellation this
        raises TIMEOUT (with request_id, so the caller retires the process) while the blocked
        write stays in the writer thread until the process is killed.
        """
        if self._writer is None:
            raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM MCP server is not running", retryable=True)
        item = self._writer.submit((json.dumps(msg) + "\n").encode("utf-8"))
        while not item.done.wait(max(0.0, min(deadline - time.monotonic(), self.POLL_S))):
            if time.monotonic() >= deadline or (dl is not None and dl.cancelled.is_set()):
                raise GatewayError("TIMEOUT", "NotebookLM MCP server is not reading its input", retryable=True,
                                   details={"request_id": request_id})
        if item.error:
            raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM MCP server input closed", retryable=True,
                               details={"request_id": request_id})

    def _request(self, method: str, params: dict, timeout: float, dl: Deadline | None = None) -> dict:
        """Send one request and wait for its response until a single absolute deadline.

        Notifications and other messages never extend the wait; a cancelled attempt stops it.
        """
        if timeout <= 0 or (dl is not None and dl.done()):
            raise GatewayError("TIMEOUT", f"NotebookLM MCP {method}: deadline passed before sending", retryable=True)
        deadline = time.monotonic() + timeout
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}, deadline, dl, rid)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or (dl is not None and dl.cancelled.is_set()):
                raise GatewayError("TIMEOUT", f"NotebookLM MCP {method} timed out", retryable=True,
                                   details={"request_id": rid})
            try:
                msg = self._q.get(timeout=min(remaining, self.POLL_S))
            except queue.Empty:
                continue
            if msg is None:
                raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM MCP server exited", retryable=True)
            if msg.get("id") == rid:
                if "error" in msg:
                    raise classify_backend_error(str(msg["error"].get("message", "")))
                return msg.get("result", {})

    def _tool(self, name: str, arguments: dict, timeout: float = 240.0) -> dict:
        if name not in M01_READ_TOOLS:
            raise GatewayError("SOURCE_NOT_ALLOWED", f"tool {name!r} is not an M01-approved read tool")
        dl = current_deadline()   # set when called from a retry attempt
        if dl is None:
            self._lock.acquire()
        elif dl.done() or not self._lock.acquire(timeout=max(dl.remaining(), 0.001)):
            raise GatewayError("TIMEOUT", "attempt expired while waiting for the NotebookLM client", retryable=True)
        try:
            if dl is not None and dl.done():   # expired while queued: never send
                raise GatewayError("TIMEOUT", "attempt expired before sending", retryable=True)
            self._start(dl)
            try:
                res = self._request("tools/call", {"name": name, "arguments": arguments},
                                    timeout=self._bounded(timeout, dl), dl=dl)
            except GatewayError as e:
                # Retire only work that is in flight (request sent, then timed out) or a server that exited;
                # a request refused before sending leaves the validated process in place.
                if e.details.get("request_id") is not None or (e.code == "BACKEND_UNAVAILABLE" and e.retryable):
                    self._retire(e.details.get("request_id"))
                raise
        finally:
            self._lock.release()
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

    def _retire(self, request_id: int | None) -> None:
        """Timed-out or broken in-flight call: ask the server to cancel it, then kill the process.

        The next call starts and validates a fresh process (F7), so no late response or work
        of the timed-out request survives into a later attempt.
        """
        if request_id is not None and self._writer is not None:
            # Best effort and bounded: if stdin is stalled the notice is simply dropped by the kill below.
            try:
                self._send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                            "params": {"requestId": request_id, "reason": "timeout"}},
                           time.monotonic() + self.CANCEL_NOTICE_S)
            except GatewayError:
                pass
        self._terminate()

    def _terminate(self) -> None:
        """Kill the current process (startup failure or replacement) and forget it."""
        self._ready = False
        proc, self._proc = self._proc, None
        writer, self._writer = self._writer, None
        if proc is None:
            return
        try:
            proc.kill()   # first: this also unblocks a writer stuck on a full stdin pipe
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        self._release_streams(proc, writer)

    @staticmethod
    def _release_streams(proc: subprocess.Popen, writer: _StdinWriter | None) -> None:
        stdin_free = True
        if writer is not None:
            writer.stop()
            writer.thread.join(timeout=2)
            stdin_free = not writer.thread.is_alive()
        # Closing stdin while the writer still holds it could block; leaking the handle is the safe choice.
        for stream in ((proc.stdin, proc.stdout) if stdin_free else (proc.stdout,)):
            try:
                if stream:
                    stream.close()
            except (OSError, ValueError):
                pass

    def close(self) -> None:
        """Graceful stop: drain pending writes and let the server exit on EOF, killing it if it does not."""
        self._ready = False
        proc, self._proc = self._proc, None
        writer, self._writer = self._writer, None
        if proc is None:
            return
        if writer is not None:
            writer.stop()
            writer.thread.join(timeout=2)
            if writer.thread.is_alive():   # stdin stalled: do not wait on it
                proc.kill()
        try:
            if not (writer and writer.thread.is_alive()) and proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()
            proc.wait(timeout=10)
        self._release_streams(proc, None if writer is None else writer)


def _expand(value: str) -> str:
    def repl(m: re.Match[str]) -> str:
        name, default = m.group(1), m.group(3)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise GatewayError("BACKEND_UNAVAILABLE", f"MCP config needs environment variable {name}")
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}", repl, value)
