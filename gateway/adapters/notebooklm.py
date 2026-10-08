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
    F14: the server and every descendant are contained (Windows job object, POSIX
    process group); teardown kills and then verifies the whole tree, and every start,
    validated start and teardown is recorded (process_state()). Errors carry the MCP
    method, phase and whether the request was written (details "sent").
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
    number: int | None = None   # NotebookLM citation number, when the response gave one


@dataclass
class SemanticResult:
    notebook_id: str
    answer: str
    citations: list[Citation]
    # Non-empty when the response cited anything outside the queried source ids, or had a missing, malformed or
    # contradictory citation entry (markers UNATTRIBUTED / INCONSISTENT). Then answer and citations are already
    # discarded: the whole response is out of scope (F12, F13).
    out_of_scope_source_ids: list[str] = field(default_factory=list)


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


UNATTRIBUTED = "<unattributed>"    # a citation, reference or sources_used entry without a usable source id
INCONSISTENT = "<inconsistent>"    # containers that disagree, or a malformed citation number / container


@dataclass
class CitationCheck:
    """Strict normalization of one notebook_query result's citations (F13), against the queried source ids.

    Accepted shapes:
      * notebooklm-mcp-cli 0.15.1: `citations` {citation_number: source_id}, `references`
        [{source_id, citation_number, cited_text}], `sources_used` [source_id] (the unique citation values);
      * the earlier object shape: `citations` [{source_id, passage}] or {key: {source_id, passage}}.
    Every entry is checked on its own; `sources_used` never vouches for a malformed citation. `problems` lists
    what makes the response unusable; `discard` is then non-empty and the whole response must be discarded (F12).
    Ids, counts and key names only: no answer or passage text is kept outside `citations`.
    """
    citations: list[Citation] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)       # from `citations`
    reference_ids: list[str] = field(default_factory=list)   # from `references`
    used_ids: list[str] = field(default_factory=list)        # from `sources_used`
    out_of_scope: list[str] = field(default_factory=list)    # real ids outside the queried source ids
    problems: list[str] = field(default_factory=list)        # codes, see _problem below
    shape: dict = field(default_factory=dict)                 # container types, value kinds, key names, counts

    @property
    def discard(self) -> list[str]:
        markers = []
        if any(p.startswith("MISSING_") for p in self.problems):
            markers.append(UNATTRIBUTED)
        if any(not p.startswith("MISSING_") for p in self.problems):
            markers.append(INCONSISTENT)
        return sorted(set(self.out_of_scope)) + markers


_NUMBER = re.compile(r"[1-9][0-9]*")


def _citation_number(value) -> int | None:
    """A positive citation number given as an int or a decimal string (JSON object keys are strings)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and _NUMBER.fullmatch(value):
        return int(value)
    return None


def _source_id(value) -> str | None:
    return value if isinstance(value, str) and value.strip() == value and value else None


def check_citations(result: dict, requested) -> CitationCheck:
    """Normalize `citations`, `references` and `sources_used` of one result strictly (see CitationCheck)."""
    chk = CitationCheck()
    allowed = set(requested)
    problems: list[str] = []

    def problem(code: str) -> None:
        if code not in problems:
            problems.append(code)

    # citations: number -> (source_id, passage)
    raw = result.get("citations")
    numbered: dict[int, tuple[str, str | None]] = {}
    unnumbered: list[tuple[str, str | None]] = []
    value_kinds: set[str] = set()
    item_keys: set[str] = set()
    if raw is None:
        entries = []
    elif isinstance(raw, dict):
        entries = list(raw.items())
    elif isinstance(raw, list):
        entries = [(None, v) for v in raw]
    else:
        entries = []
        problem("MALFORMED_CITATIONS_CONTAINER")
    for key, value in entries:
        if isinstance(value, dict):
            value_kinds.add("object")
            item_keys.update(str(k) for k in value)
            sid = _source_id(value.get("source_id"))
            passage = next((value[k] for k in ("passage", "cited_text", "text") if isinstance(value.get(k), str)), None)
        else:
            value_kinds.add("string" if isinstance(value, str) else type(value).__name__)
            sid, passage = _source_id(value), None
        if sid is None:
            problem("MISSING_CITATION_SOURCE_ID")
            continue
        chk.cited_ids.append(sid)
        if key is None:
            unnumbered.append((sid, passage))
            continue
        n = _citation_number(key)
        if n is None:
            problem("MALFORMED_CITATION_NUMBER")
        elif n in numbered:
            problem("DUPLICATE_CITATION_NUMBER")
        else:
            numbered[n] = (sid, passage)

    # references: [{source_id, citation_number, cited_text}]
    refs = result.get("references")
    ref_keys: set[str] = set()
    ref_passages: dict[int, str] = {}
    ref_unnumbered: list[tuple[str, str | None]] = []
    ref_numbers: dict[int, str] = {}
    if refs is not None and not isinstance(refs, list):
        problem("MALFORMED_REFERENCES_CONTAINER")
        refs = []
    for ref in refs or []:
        if not isinstance(ref, dict):
            problem("MISSING_REFERENCE_SOURCE_ID")
            continue
        ref_keys.update(str(k) for k in ref)
        sid = _source_id(ref.get("source_id"))
        if sid is None:
            problem("MISSING_REFERENCE_SOURCE_ID")
            continue
        chk.reference_ids.append(sid)
        text = ref.get("cited_text")
        if text is not None and not isinstance(text, str):
            problem("MALFORMED_REFERENCE_TEXT")
            text = None
        if "citation_number" not in ref:
            ref_unnumbered.append((sid, text))
            continue
        n = _citation_number(ref["citation_number"])
        if n is None:
            problem("MALFORMED_REFERENCE_NUMBER")
            continue
        if ref_numbers.get(n, sid) != sid:
            problem("CONFLICT_REFERENCE_NUMBER")
        ref_numbers[n] = sid
        if numbered or unnumbered:
            # a numbered reference must name the same source as the citation with that number
            target = numbered.get(n) or (unnumbered[n - 1] if not numbered and n <= len(unnumbered) else None)
            if target is None or target[0] != sid:
                problem("CONFLICT_CITATION_REFERENCE")
                continue
        if text:
            ref_passages.setdefault(n, text)

    # sources_used: [source_id]
    used = result.get("sources_used")
    if used is not None and not isinstance(used, list):
        problem("MALFORMED_SOURCES_USED_CONTAINER")
        used = []
    for sid in used or []:
        if _source_id(sid) is None:
            problem("MISSING_SOURCES_USED_ID")
        else:
            chk.used_ids.append(sid)

    # every id, from every container, is checked against the queried ids
    every = set(chk.cited_ids) | set(chk.reference_ids) | set(chk.used_ids)
    chk.out_of_scope = sorted(every - allowed)
    # in-scope ids must agree across containers: a cited/referenced id missing from a non-empty sources_used, an
    # in-scope sources_used id that nothing cites, or a reference to a source that no citation names
    cited, referenced = set(chk.cited_ids) & allowed, set(chk.reference_ids) & allowed
    used_set = set(chk.used_ids) & allowed
    if chk.used_ids and (cited | referenced) - set(chk.used_ids):
        problem("CONFLICT_SOURCES_USED")
    if (chk.cited_ids or chk.reference_ids) and used_set - set(chk.cited_ids) - set(chk.reference_ids):
        problem("CONFLICT_SOURCES_USED")
    if chk.cited_ids and referenced - set(chk.cited_ids):
        problem("CONFLICT_CITATION_REFERENCE")

    chk.problems = problems
    chk.shape = {"citations_container": type(raw).__name__, "citation_value_kinds": sorted(value_kinds),
                 "citation_item_keys": sorted(item_keys), "citation_count": len(entries),
                 "references_container": type(result.get("references")).__name__,
                 "reference_item_keys": sorted(ref_keys), "reference_count": len(refs or []),
                 "sources_used_count": len(used or [])}
    if chk.discard:
        return chk

    # usable: one Citation per citation entry (passage from the object or the matching reference), then
    # references / sources_used ids that no citation names (only possible when there are no citations)
    for n in sorted(numbered):
        sid, passage = numbered[n]
        chk.citations.append(Citation(sid, passage or ref_passages.get(n), n))
    for i, (sid, passage) in enumerate(unnumbered, start=1):
        chk.citations.append(Citation(sid, passage or ref_passages.get(i)))
    named = {c.source_id for c in chk.citations}
    for sid, text, num in ([(s, t, None) for s, t in ref_unnumbered]
                           + [(ref_numbers[n], ref_passages.get(n), n) for n in sorted(ref_numbers)]):
        if sid not in named:
            chk.citations.append(Citation(sid, text or None, num))
            named.add(sid)
    for sid in chk.used_ids:
        if sid not in named:
            chk.citations.append(Citation(sid, None))
            named.add(sid)
    return chk


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
        """Semantic query restricted to source_ids.

        If the response cites any source outside source_ids, or any citation, reference or sources_used entry is
        missing, malformed or contradicts another (check_citations, F13), the backend's scope cannot be trusted:
        the whole response is discarded (no answer, no citations) and only the out-of-scope ids and markers are
        returned.
        """
        if not source_ids:
            raise GatewayError("SOURCE_NOT_ALLOWED", "no whitelisted NotebookLM sources to query")
        result = self._call(lambda: self.client.notebook_query(notebook_id, query, list(source_ids)))
        chk = check_citations(result, source_ids)
        if chk.discard:
            return SemanticResult(notebook_id, "", [], chk.discard)
        answer = result.get("answer") if isinstance(result.get("answer"), str) else ""
        return SemanticResult(notebook_id, answer, chk.citations)

    def probe(self) -> dict:
        result = self._call(self.client.notebook_list)
        return {"notebooks": len(result.get("notebooks") or [])}

    def status(self) -> dict:
        return {"state": "ok" if self.last_error is None else "degraded", "calls": self.calls,
                "last_error": self.last_error}


# ---------------------------------------------------------------------------- process containment (F14)

class _ProcessTree:
    """Containment of one server process and all its descendants, so teardown can kill and verify the whole tree.

    Windows: a job object (KILL_ON_JOB_CLOSE, no breakaway) assigned right after start; descendants created later
    are in it, and escaped() finds any descendant created before the assignment outside it. POSIX: the server is
    started in a new session, so it and its descendants share one process group, killed as a group. `kind` is
    "job", "process_group" or "none" (containment unavailable: tree_empty() is None, teardown is unverified).
    """

    VERIFY_S = 5.0

    @staticmethod
    def popen_kwargs() -> dict:
        return {} if os.name == "nt" else {"start_new_session": True}

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.kind = "none"
        self._job = None
        if os.name == "nt":
            self._job = _win_job_assign(proc)
            if self._job is not None:
                self.kind = "job"
        else:
            self.kind = "process_group"

    def escaped(self) -> int | None:
        """Live descendants outside the containment (None: cannot be checked on this platform)."""
        try:
            if self.kind == "job":
                return _win_escaped(self.proc, self._job)
            if self.kind == "process_group" and os.path.isdir("/proc"):
                procs = _proc_table()
                return sum(1 for pid in _descendants(self.proc.pid, procs) if procs[pid][1] != self.proc.pid)
        except Exception:  # noqa: BLE001
            return None
        return None

    def kill(self) -> None:
        try:
            if self.kind == "job":
                _win_k32().TerminateJobObject(self._job, 1)
            elif self.kind == "process_group":
                os.killpg(self.proc.pid, 9)
        except (OSError, ProcessLookupError):
            pass

    def _empty_now(self) -> bool | None:
        if self.kind == "job":
            active = _win_job_active(self._job)
            return None if active is None else active == 0
        if self.kind == "process_group":
            try:
                os.killpg(self.proc.pid, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            if os.path.isdir("/proc"):      # a signal reaches zombies too: only live members count
                return not any(pgrp == self.proc.pid and state != "Z" for _ppid, pgrp, state in _proc_table().values())
            return False
        return None

    def tree_empty(self, timeout: float | None = None) -> bool | None:
        """True once neither the server nor any descendant is alive (bounded wait); None when unverifiable."""
        deadline = time.monotonic() + (self.VERIFY_S if timeout is None else timeout)
        while True:
            try:
                state = self._empty_now()
            except Exception:  # noqa: BLE001
                return None
            if state is None or state:
                return state
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def close(self) -> None:
        if self._job is not None:
            try:
                _win_k32().CloseHandle(self._job)
            except OSError:
                pass
            self._job = None


def _proc_table() -> dict[int, tuple[int, int, str]]:
    """Linux /proc: pid -> (ppid, pgrp, state)."""
    out = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as fh:
                stat = fh.read().decode("ascii", "replace")
        except OSError:
            continue
        fields = stat[stat.rindex(")") + 2:].split()
        out[int(entry)] = (int(fields[1]), int(fields[2]), fields[0])
    return out


def _descendants(root: int, procs: dict[int, tuple]) -> list[int]:
    children: dict[int, list[int]] = {}
    for pid, info in procs.items():
        if info[2] != "Z":
            children.setdefault(info[0], []).append(pid)
    out, todo = [], [root]
    while todo:
        for child in children.get(todo.pop(), []):
            out.append(child)
            todo.append(child)
    return out


_K32 = None


def _win_k32():
    """kernel32 with explicit signatures (handles are pointer-sized)."""
    global _K32
    if _K32 is not None:
        return _K32
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    H, B, D = wintypes.HANDLE, wintypes.BOOL, wintypes.DWORD
    sig = {"CreateJobObjectW": (H, [ctypes.c_void_p, wintypes.LPCWSTR]),
           "SetInformationJobObject": (B, [H, ctypes.c_int, ctypes.c_void_p, D]),
           "QueryInformationJobObject": (B, [H, ctypes.c_int, ctypes.c_void_p, D, ctypes.POINTER(D)]),
           "AssignProcessToJobObject": (B, [H, H]),
           "TerminateJobObject": (B, [H, ctypes.c_uint]),
           "IsProcessInJob": (B, [H, H, ctypes.POINTER(B)]),
           "OpenProcess": (H, [D, B, D]),
           "GetProcessTimes": (B, [H] + [ctypes.POINTER(wintypes.FILETIME)] * 4),
           "CreateToolhelp32Snapshot": (H, [D, D]),
           "Process32FirstW": (B, [H, ctypes.c_void_p]),
           "Process32NextW": (B, [H, ctypes.c_void_p]),
           "CloseHandle": (B, [H])}
    for name, (res, args) in sig.items():
        fn = getattr(k, name)
        fn.restype, fn.argtypes = res, args
    _K32 = k
    return k


def _win_structs():
    import ctypes
    from ctypes import wintypes

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class BASIC_ACCOUNTING(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                    ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    return BASIC_LIMIT, EXTENDED_LIMIT, BASIC_ACCOUNTING, PROCESSENTRY32W


def _win_job_assign(proc: subprocess.Popen):
    """A kill-on-close job holding proc, or None if the job cannot be created or assigned."""
    import ctypes
    k = _win_k32()
    _, EXTENDED_LIMIT, _, _ = _win_structs()
    job = k.CreateJobObjectW(None, None)
    if not job:
        return None
    info = EXTENDED_LIMIT()
    info.BasicLimitInformation.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway allowed
    ok = k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))   # ExtendedLimitInformation
    if not ok or not k.AssignProcessToJobObject(job, int(proc._handle)):  # noqa: SLF001 - Popen's process handle
        k.CloseHandle(job)
        return None
    return job


def _win_job_active(job) -> int | None:
    import ctypes
    from ctypes import wintypes
    _, _, BASIC_ACCOUNTING, _ = _win_structs()
    acct = BASIC_ACCOUNTING()
    if not _win_k32().QueryInformationJobObject(job, 1, ctypes.byref(acct), ctypes.sizeof(acct),
                                                ctypes.byref(wintypes.DWORD())):
        return None
    return int(acct.ActiveProcesses)


def _win_escaped(proc: subprocess.Popen, job) -> int | None:
    """Live descendants of proc (by parent pid, created after their parent) that are not in the job."""
    import ctypes
    from ctypes import wintypes
    k = _win_k32()
    _, _, _, PROCESSENTRY32W = _win_structs()

    def created(pid: int) -> int | None:
        h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not k.GetProcessTimes(h, *[ctypes.byref(x) for x in times]):
                return None
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        finally:
            k.CloseHandle(h)

    snap = k.CreateToolhelp32Snapshot(0x2, 0)   # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        return None
    pairs = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            pairs.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
            ok = k.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k.CloseHandle(snap)
    children: dict[int, list[int]] = {}
    for pid, ppid in pairs:
        if pid != ppid:
            children.setdefault(ppid, []).append(pid)
    root_created = created(proc.pid)
    if root_created is None:
        return None
    escaped, todo = 0, [(proc.pid, root_created)]
    while todo:
        parent, parent_created = todo.pop()
        for child in children.get(parent, []):
            child_created = created(child)
            if child_created is None or child_created < parent_created:
                continue   # gone, or a stale parent id from before the parent existed
            h = k.OpenProcess(0x1000, False, child)
            if not h:
                continue
            try:
                inside = wintypes.BOOL()
                if not k.IsProcessInJob(h, job, ctypes.byref(inside)) or not inside.value:
                    escaped += 1
            finally:
                k.CloseHandle(h)
            todo.append((child, child_created))
    return escaped


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
        self._tree: _ProcessTree | None = None
        # F14 records (pids, flags, timings only): every spawned process, every process that passed initialize +
        # the exact tools/list check, and every teardown with its verification
        self._generation = 0
        self.spawned: list[dict] = []
        self.validated_starts: list[dict] = []
        self.teardowns: list[dict] = []

    def process_state(self) -> dict:
        proc = self._proc
        return {"alive": proc is not None and proc.poll() is None, "ready": self._ready,
                "spawned": [dict(x) for x in self.spawned],
                "validated_starts": [dict(x) for x in self.validated_starts],
                "teardowns": [dict(x) for x in self.teardowns]}

    @staticmethod
    def _bounded(timeout: float, dl: Deadline | None) -> float:
        """Step timeout, never beyond the attempt's deadline."""
        return timeout if dl is None else min(timeout, dl.remaining())

    def _start(self, dl: Deadline | None = None) -> None:
        if self._ready and self._proc and self._proc.poll() is None:
            return
        self._terminate("replace")   # a dead process, or a live one that never passed the startup checks
        env = dict(os.environ, **self._spec["env"])
        exe = shutil.which(self._spec["command"]) or self._spec["command"]
        try:
            proc = subprocess.Popen([exe, *self._spec["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, env=env, **_ProcessTree.popen_kwargs())
        except OSError:
            raise GatewayError("BACKEND_UNAVAILABLE", "cannot start the NotebookLM MCP server",
                               details={"phase": "startup", "method": None, "sent": False}) from None
        self._tree = _ProcessTree(proc)
        self._generation += 1
        self.spawned.append({"generation": self._generation, "pid": proc.pid, "containment": self._tree.kind})
        self._proc, self._q = proc, queue.Queue()
        self._writer = _StdinWriter(proc.stdin)
        threading.Thread(target=self._reader, args=(proc, self._q), daemon=True).start()
        try:
            self._request("initialize", {"protocolVersion": self.PROTOCOL_VERSION, "capabilities": {},
                                         "clientInfo": {"name": "tvxd-standards-gateway", "version": "0.1.0"}},
                          timeout=self._bounded(self._start_timeout, dl), dl=dl)
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"},
                       time.monotonic() + self._bounded(self._start_timeout, dl), dl,
                       method="notifications/initialized")
            tools = sorted(str(t.get("name")) for t in self._request(
                "tools/list", {}, timeout=self._bounded(self._start_timeout, dl), dl=dl).get("tools", []))
            if tools != sorted(M01_READ_TOOLS):
                raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM server tool surface is not exactly the four "
                                   "M01-approved read tools; refusing to use it",
                                   details={"visible_tools": len(tools), "method": "tools/list", "sent": True})
            outside = self._tree.escaped()
            if outside:
                raise GatewayError("BACKEND_UNAVAILABLE", "a NotebookLM MCP server process is outside its "
                                   "containment; refusing to use it", details={"escaped_processes": outside,
                                                                               "method": None, "sent": False})
        except BaseException as e:
            if isinstance(e, GatewayError):
                e.details = {**e.details, "phase": "startup"}
            self._terminate("startup_failure")
            raise
        self._ready = True
        self.validated_starts.append({"generation": self._generation, "pid": proc.pid, "tools": len(tools),
                                      "containment": self._tree.kind, "escaped_processes": outside})

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

    def _send(self, msg: dict, deadline: float, dl: Deadline | None = None, request_id: int | None = None,
              method: str | None = None) -> None:
        """Hand one message to the writer thread and wait for it until `deadline` (absolute, monotonic).

        A server that stops reading stdin cannot hold the caller: on expiry or cancellation this
        raises TIMEOUT (with request_id, so the caller retires the process) while the blocked
        write stays in the writer thread until the process is killed.
        """
        if self._writer is None:
            raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM MCP server is not running", retryable=True,
                               details={"method": method, "sent": False})
        item = self._writer.submit((json.dumps(msg) + "\n").encode("utf-8"))
        # from here on the message may be partly written: "sent" is only True once the write completed
        while not item.done.wait(max(0.0, min(deadline - time.monotonic(), self.POLL_S))):
            if time.monotonic() >= deadline or (dl is not None and dl.cancelled.is_set()):
                raise GatewayError("TIMEOUT", "NotebookLM MCP server is not reading its input", retryable=True,
                                   details={"request_id": request_id, "method": method, "sent": "not_confirmed"})
        if item.error:
            raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM MCP server input closed", retryable=True,
                               details={"request_id": request_id, "method": method, "sent": "not_confirmed"})

    def _request(self, method: str, params: dict, timeout: float, dl: Deadline | None = None) -> dict:
        """Send one request and wait for its response until a single absolute deadline.

        Notifications and other messages never extend the wait; a cancelled attempt stops it.
        """
        if timeout <= 0 or (dl is not None and dl.done()):
            raise GatewayError("TIMEOUT", f"NotebookLM MCP {method}: deadline passed before sending", retryable=True,
                               details={"request_id": None, "method": method, "sent": False})
        deadline = time.monotonic() + timeout
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}, deadline, dl, rid, method)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or (dl is not None and dl.cancelled.is_set()):
                raise GatewayError("TIMEOUT", f"NotebookLM MCP {method} timed out", retryable=True,
                                   details={"request_id": rid, "method": method, "sent": True})
            try:
                msg = self._q.get(timeout=min(remaining, self.POLL_S))
            except queue.Empty:
                continue
            if msg is None:
                raise GatewayError("BACKEND_UNAVAILABLE", "NotebookLM MCP server exited", retryable=True,
                                   details={"method": method, "sent": True})
            if msg.get("id") == rid:
                if "error" in msg:
                    err = classify_backend_error(str(msg["error"].get("message", "")))
                    err.details = {**err.details, "method": method, "sent": True, "responded": True}
                    raise err
                return msg.get("result", {})

    def _tool(self, name: str, arguments: dict, timeout: float = 240.0) -> dict:
        if name not in M01_READ_TOOLS:
            raise GatewayError("SOURCE_NOT_ALLOWED", f"tool {name!r} is not an M01-approved read tool")
        dl = current_deadline()   # set when called from a retry attempt
        if dl is None:
            self._lock.acquire()
        elif dl.done() or not self._lock.acquire(timeout=max(dl.remaining(), 0.001)):
            raise GatewayError("TIMEOUT", "attempt expired while waiting for the NotebookLM client", retryable=True,
                               details={"method": "tools/call", "tool": name, "phase": "queue", "sent": False})
        try:
            if dl is not None and dl.done():   # expired while queued: never send
                raise GatewayError("TIMEOUT", "attempt expired before sending", retryable=True,
                                   details={"method": "tools/call", "tool": name, "phase": "queue", "sent": False})
            self._start(dl)
            try:
                res = self._request("tools/call", {"name": name, "arguments": arguments},
                                    timeout=self._bounded(timeout, dl), dl=dl)
            except GatewayError as e:
                e.details = {**e.details, "tool": name, "phase": "call"}
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
                           time.monotonic() + self.CANCEL_NOTICE_S, method="notifications/cancelled")
            except GatewayError:
                pass
        self._terminate("retire")

    def _terminate(self, reason: str) -> None:
        """Kill the current process tree (startup failure, retirement or replacement), verify it, and forget it."""
        self._ready = False
        proc, self._proc = self._proc, None
        writer, self._writer = self._writer, None
        tree, self._tree = self._tree, None
        if proc is None:
            return
        t0 = time.monotonic()
        try:
            if tree is not None:
                tree.kill()   # first: the whole tree; this also unblocks a writer stuck on a full stdin pipe
            proc.kill()
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        self._record_teardown(proc, tree, reason, t0)
        self._release_streams(proc, writer)

    def _record_teardown(self, proc: subprocess.Popen, tree: _ProcessTree | None, reason: str, t0: float) -> None:
        empty = tree.tree_empty() if tree is not None else None
        wrapper_exited = proc.poll() is not None
        self.teardowns.append({"generation": next((s["generation"] for s in reversed(self.spawned)
                                                   if s["pid"] == proc.pid), None),
                               "pid": proc.pid, "reason": reason,
                               "containment": tree.kind if tree is not None else "none",
                               "wrapper_exited": wrapper_exited, "tree_empty": empty,
                               "verified": bool(wrapper_exited and empty is True),
                               "elapsed_ms": int((time.monotonic() - t0) * 1000)})
        if tree is not None:
            tree.close()

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
        """Graceful stop: drain pending writes and let the server exit on EOF, killing it if it does not; then kill
        and verify whatever is left of its process tree."""
        self._ready = False
        proc, self._proc = self._proc, None
        writer, self._writer = self._writer, None
        tree, self._tree = self._tree, None
        if proc is None:
            return
        t0 = time.monotonic()
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
        if tree is not None:
            tree.kill()   # descendants that outlived the server's own exit
        self._record_teardown(proc, tree, "close", t0)
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
