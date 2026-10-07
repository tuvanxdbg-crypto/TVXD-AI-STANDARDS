#!/usr/bin/env python3
"""M02 bounded pilot, stage B (B2): the Gateway's semantic route against NotebookLM. docs/M02_PILOT_PLAN.md §6b.

NOT AUTHORIZED TO RUN LIVE until GPT review of this script and the owner's direct approval of B2.

The committed config `docs/m02-pilot/gateway.pilot.stage-b.json` keeps `notebooklm.mode: disabled`. With `--live`
the runner writes a temporary copy with `mode: mcp_stdio` (never committed); the Gateway then starts the M01 gated
server from the project `.mcp.json` and refuses any tool surface other than the four M01 read tools. The runner
itself only calls `standards_lookup` / `standards_verify`; the Gateway sends `notebook_query` with the mapped source
ids only. No notebook_get, source_get_content, upload or change. `--fake clean|mixed|auth` runs the same cases
offline against tests/m02/fake_notebooklm.py (no Google contact), for dry runs on make_pilot_synthetic.py output.

Gates: the first FAIL stops the run before any further NotebookLM call (later cases are NOT_RUN). Every
notebook_query attempt from every client (P8 included) is recorded in one audit before it is sent, so a timeout or
exception still leaves a record; the run FAILs if any attempt sent a source set other than exactly the three mapped
ids, or ever sent the M01 injection source.

Cases (plan §6b): P5 citation shape, P6 cold vs cache, P7 revoked notebook whitelist, P8 timeout recovery,
P10 out-of-scope boundary (P10-A OUT_OF_SCOPE_NOT_OBSERVED or P10-B OUT_OF_SCOPE_OBSERVED), P11 no sync identity.
P9 (model surface) and the preflights are separate commands (see the plan). A case whose precondition did not occur
(e.g. no FOUND result to re-use for P6) is reported NOT_OBSERVED, never PASS.

Recorded per notebook_query (summary), using the Gateway's own strict citation check (check_citations, F13):
sent source ids, result key names, container types, citation value kinds, citation / reference item key names,
counts, cited / referenced / sources_used ids, out-of-scope ids, citation problem codes, answer length. For an
exception: the code, the MCP method and phase it failed in, and whether notebook_query's tools/call was written
(F14). Never the answer text, passages or excerpts. P8 with the real client also records the server processes it
started, validated and tore down (pids, flags, timings). Outputs under tests/m02/evidence/local/ (git-ignored):
stage-b-<ts>.summary.json (ids, statuses, codes, counts, key names, timings) and stage-b-<ts>.raw.json (full
Gateway responses; local only).
Exit code: 0 PASS, 1 any FAIL, 2 refused to start, 3 BLOCKED (no FAIL, but a teardown could not be verified).

  uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z \\
      tests/m02/pilot_stage_b.py --fake clean --config <synthetic>/gateway.pilot.stage-b.json
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import io
import json
import platform
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from gateway.adapters.notebooklm import McpStdioNotebookLMClient, check_citations  # noqa: E402
from gateway.config import load_config  # noqa: E402
from gateway.errors import GatewayError  # noqa: E402
from gateway.index import load_index  # noqa: E402
from gateway.logs import JsonLogger  # noqa: E402
from gateway.service import GatewayService  # noqa: E402
from pilot_stage_a import DAY, PILOT_DOCS, WORK_CODE, Refused, git_head, resp_summary, strip_text  # noqa: E402

CONFIG = REPO / "docs" / "m02-pilot" / "gateway.pilot.stage-b.json"
NOTEBOOK = "8ca84143-c240-4fcb-98fe-e1f8c6cca02d"
INJECTION_SOURCE = "b710e565-91f6-49f1-bea6-a6783cbca9f4"   # M01-10 test source: must never be mapped or sent
Q_S1 = "Tiêu chuẩn thiết kế chiếu sáng lớp học trường trung học"
CTX = {"work_code": WORK_CODE, "assessment_date": DAY,
       "project_context": {"conditions": {"COND-TRUONG-TRUNG-HOC": True}}}   # COND-KET-CAU-THEP stays unset


PLANNED = ("P5", "P10", "P6", "P7", "P11", "P8")
P8_TERMINAL_WAIT_S = 15.0   # bounded wait for the timed-out P8 attempt to reach a terminal outcome before judging
STARTUP_METHODS = ("initialize", "notifications/initialized", "tools/list")
P11_EXTRA_INDEX_EDIT = None   # test seam only (tests/m02/test_gateway_pilot_stage_b.py); None in real runs


class StopPilot(Exception):
    """A case FAILed (or is BLOCKED): the plan stops the pilot before any further NotebookLM call."""


def sent_state(details: dict):
    """Whether a failed notebook_query reached the server, from the client's error details (F14).

    True only when its tools/call request was completely written; False when it failed before that (queued,
    during server startup: initialize / tools/list, or before sending); "not_confirmed" when unknown, e.g. a
    partly written request or a client that does not report the method."""
    method, sent = details.get("method"), details.get("sent")
    if method == "tools/call":
        return True if sent is True else (False if sent is False else "not_confirmed")
    if details.get("phase") in ("startup", "queue") or method in STARTUP_METHODS:
        return False
    return "not_confirmed"


class Audit:
    """Every notebook_query attempt of every client, and the per-attempt source gate."""

    FINALIZE_WAIT_S = 10.0

    def __init__(self, expected_sent: list[str]):
        self.entries: list[dict] = []
        self.expected = sorted(expected_sent)
        self.tripped: str | None = None
        self._done: dict[int, threading.Event] = {}
        self._t0: dict[int, float] = {}
        self._lock = threading.Lock()
        self.sealed = False
        self.late_after_seal = 0     # worker completions that arrived after the snapshot (never written into it)
        self.refused_after_seal = 0  # attempts that tried to open after the seal: refused, never sent

    def open(self, client: str, notebook_id: str, requested: list[str]) -> dict | None:
        """Atomically allocate and append an attempt, or refuse (None) once the audit is sealed. The caller must not
        touch the transport when this returns None."""
        with self._lock:
            if self.sealed:
                self.refused_after_seal += 1
                return None
            entry = {"attempt": len(self.entries) + 1, "client": client, "notebook_id": notebook_id,
                     "requested_source_ids": sorted(requested), "outcome": "in_flight", "sent_to_backend": None}
            self.entries.append(entry)
            self._done[entry["attempt"]] = threading.Event()
            self._t0[entry["attempt"]] = time.monotonic()
            return entry

    def placeholder(self, client: str, caller_outcome: str) -> None:
        """A tool call that returned TIMEOUT before its worker opened any attempt: the worker may still try to send
        later, so record it (fail-closed) instead of letting the run look clean."""
        with self._lock:
            if self.sealed:
                return
            n = len(self.entries) + 1
            self.entries.append({"attempt": n, "client": client, "notebook_id": None, "requested_source_ids": [],
                                 "outcome": "no_attempt_seen_before_caller_timeout",
                                 "sent_to_backend": "not_confirmed", "caller_outcome": caller_outcome,
                                 "elapsed_ms": 0})
            self._done[n] = threading.Event()
            self._done[n].set()
            self._t0[n] = time.monotonic()

    def close(self, entry: dict, **fields) -> None:
        with self._lock:
            if self.sealed:              # a worker finished after the snapshot: count it, never rewrite the audit
                self.late_after_seal += 1
                return
            entry.update(elapsed_ms=int((time.monotonic() - self._t0[entry["attempt"]]) * 1000), **fields)
            self._done[entry["attempt"]].set()

    def wait_terminal(self, attempts: list[int], timeout: float) -> bool:
        """True once every listed attempt has a terminal outcome (bounded by timeout)."""
        deadline = time.monotonic() + timeout
        return all(self._done[n].wait(max(0.0, deadline - time.monotonic())) for n in attempts)

    def finalize(self) -> list[dict]:
        """Wait (bounded by FINALIZE_WAIT_S) for workers that outlived a caller TIMEOUT, then seal the audit and
        return an immutable terminal snapshot. An attempt whose worker has not confirmed completion becomes
        'abandoned_unfinished' with sent_to_backend 'not_confirmed'; it makes the run FAIL (see execute)."""
        deadline = time.monotonic() + self.FINALIZE_WAIT_S
        for e in list(self.entries):
            self._done[e["attempt"]].wait(max(0.0, deadline - time.monotonic()))
        with self._lock:
            self.sealed = True
            snapshot = copy.deepcopy(self.entries)
        now = time.monotonic()
        for e in snapshot:
            if e["outcome"] == "in_flight":
                e.update(outcome="abandoned_unfinished", sent_to_backend="not_confirmed",
                         elapsed_ms=int((now - self._t0[e["attempt"]]) * 1000))
            elif "TIMEOUT" in (e.get("caller_outcome") or "") and e["outcome"] in ("returned", "exception"):
                e["outcome"] = e["outcome"] + "_after_caller_timeout"
        return snapshot


class Recorder:
    """Wraps a NotebookLM client. Every notebook_query attempt is opened in the shared audit before anything is
    sent; the per-attempt gate refuses (before transport) any attempt whose source set is not exactly the three
    mapped ids or that contains the M01 injection source, and every attempt after the gate tripped. The record keeps
    ids, key names, counts and timings only; never answer text, passages or excerpts."""

    def __init__(self, inner, audit: Audit, label: str):
        self.inner, self.audit, self.label = inner, audit, label

    def notebook_query(self, notebook_id, query, source_ids):
        audit = self.audit
        entry = audit.open(self.label, notebook_id, list(source_ids))
        if entry is None:            # the audit is sealed: never reach the transport
            raise GatewayError("SOURCE_NOT_ALLOWED", "stage B audit is sealed; attempt refused before transport")
        requested = entry["requested_source_ids"]
        if audit.tripped:
            audit.close(entry, outcome="blocked_after_stop", sent_to_backend=False)
            raise GatewayError("SOURCE_NOT_ALLOWED", "pilot stopped by the source gate")
        if requested != audit.expected or INJECTION_SOURCE in requested:
            audit.tripped = f"attempt {entry['attempt']} ({self.label}): source set is not exactly the mapped ids"
            audit.close(entry, outcome="blocked_wrong_source_set", sent_to_backend=False)
            raise GatewayError("SOURCE_NOT_ALLOWED", "source set is not exactly the three mapped ids")
        try:
            result = self.inner.notebook_query(notebook_id, query, source_ids)
        except BaseException as e:
            details = getattr(e, "details", None) or {}
            audit.close(entry, outcome="exception", exception=getattr(e, "code", None) or type(e).__name__,
                        sent_to_backend=sent_state(details), failed_method=details.get("method"),
                        failed_phase=details.get("phase"))
            raise
        result = result if isinstance(result, dict) else {}
        chk = check_citations(result, requested)
        audit.close(
            entry, outcome="returned", sent_to_backend=True, status=result.get("status"),
            result_keys=sorted(result.keys()), **chk.shape,
            cited_source_ids=sorted(set(chk.cited_ids)), reference_source_ids=sorted(set(chk.reference_ids)),
            sources_used=sorted(set(chk.used_ids)), out_of_scope_source_ids=chk.out_of_scope,
            citation_problems=chk.problems,
            unattributed_citation=any(x.startswith("MISSING_") for x in chk.problems),
            discarded=bool(chk.discard),
            answer_chars=len(result.get("answer")) if isinstance(result.get("answer"), str) else 0)
        return result

    def notebook_list(self):                       # not used by the stage B cases
        raise GatewayError("SOURCE_NOT_ALLOWED", "stage B runner does not list notebooks")

    def notebook_get(self, notebook_id):
        raise GatewayError("SOURCE_NOT_ALLOWED", "stage B runner does not call notebook_get (B0 is separate)")

    def source_get_content(self, source_id):
        raise GatewayError("SOURCE_NOT_ALLOWED", "stage B runner never reads NotebookLM source content")


TCVN_8794_SOURCE = "8ccb8115-f552-4ecb-b42a-f0ee093f1d08"
FAKE_PASSAGE = "Yêu cầu giả lập về chiếu sáng lớp học trường trung học."


def fake_answer(scenario: str) -> dict:
    """A notebook_query result in the notebooklm-mcp-cli 0.15.1 shape (F13): citations {number: source_id},
    references [{source_id, citation_number, cited_text}], sources_used = the unique citation values. It cites the
    mapped TCVN 8794 source (and, for 'mixed', the M01 injection source too)."""
    cites = [(TCVN_8794_SOURCE, FAKE_PASSAGE)]
    if scenario == "mixed":
        cites.append((INJECTION_SOURCE, "(fake) chỉ dẫn nhúng"))
    return {"answer": "(fake) câu trả lời giả lập", "question": Q_S1, "conversation_id": "fake-conversation",
            "citations": {str(n): sid for n, (sid, _) in enumerate(cites, start=1)},
            "references": [{"source_id": sid, "citation_number": n, "cited_text": text}
                           for n, (sid, text) in enumerate(cites, start=1)],
            "sources_used": list(dict.fromkeys(sid for sid, _ in cites))}


def fake_client(scenario: str):
    """Offline stand-in for the synthetic library (fake_answer)."""
    from fake_notebooklm import FakeNotebookLM
    fake = FakeNotebookLM({NOTEBOOK: fake_answer(scenario)})
    if scenario == "auth":       # every call reports an expired login -> AUTH_REQUIRED (P5 FAIL, pilot stops)
        fake.fail_with = [{"status": "error", "error": "authentication expired, please sign in"}] * 10
    return fake


class Run:
    def __init__(self):
        self.cases: list[dict] = []
        self.raw: list[dict] = []

    def case(self, cid, desc, result, expected, observed):
        self.cases.append({"id": cid, "case": desc, "result": result, "expected": expected, "observed": observed})
        if result in ("FAIL", "BLOCKED"):
            raise StopPilot(cid)

    def keep(self, label, payload):
        self.raw.append({"label": label, "response": payload})


class GatedService(GatewayService):
    """A GatewayService whose every tool call tags the attempts it caused with the caller-visible outcome and
    raises StopPilot as soon as the per-attempt source gate has tripped, before any further call."""

    def __init__(self, config, recorder: Recorder | None):
        super().__init__(config, notebooklm_client=recorder, logger=JsonLogger(stream=io.StringIO(), level="info"))
        self.audit = recorder.audit if recorder is not None else None
        self.label = recorder.label if recorder is not None else None

    def call(self, tool, arguments):
        n0 = len(self.audit.entries) if self.audit else 0
        r = super().call(tool, arguments)
        if self.audit:
            tag = r["status"] + (":" + r["error"]["code"] if r.get("error") else "")
            new = self.audit.entries[n0:]
            for e in new:
                e["caller_outcome"] = tag
            if not new and (r.get("error") or {}).get("code") == "TIMEOUT":
                self.audit.placeholder(self.label, tag)
            if self.audit.tripped:
                raise StopPilot("SOURCE_GATE")
        return r


def service(config: Path, client) -> GatewayService:
    return GatedService(load_config(config), client)


def write_temp(tmp: Path, config: Path, *, mode: str, index_edit=None, nb_overrides: dict | None = None) -> Path:
    """Temporary config (absolute paths) and, if index_edit is given, a temporary INDEX copy."""
    cfg = load_config(config)
    data = json.loads(config.read_text(encoding="utf-8-sig"))
    index_path = cfg.index_path
    if index_edit is not None:
        index_path = tmp / f"INDEX.{len(list(tmp.iterdir()))}.yaml"
        index_path.write_text(index_edit(cfg.index_path.read_text(encoding="utf-8")), encoding="utf-8")
    data["index_path"] = str(index_path)
    data["source_root"] = str(cfg.source_root)
    data["notebooklm"]["mode"] = mode
    if cfg.notebooklm.mcp_config:
        data["notebooklm"]["mcp_config"] = str(cfg.notebooklm.mcp_config)
    data["notebooklm"].update(nb_overrides or {})
    out = tmp / f"gateway.{len(list(tmp.iterdir()))}.json"
    out.write_text(json.dumps(data), encoding="utf-8")
    return out


def preconditions(config: Path) -> dict:
    cfg = load_config(config)
    if cfg.notebooklm.mode != "disabled":
        raise Refused("the committed stage B config must stay notebooklm.mode: disabled (mcp_stdio only in a temp copy)")
    index = load_index(cfg.index_path)
    if sorted(index.documents) != sorted(PILOT_DOCS) or sorted(index.whitelist_documents) != sorted(PILOT_DOCS):
        raise Refused("stage B INDEX must hold and whitelist exactly the three pilot documents")
    if sorted(index.whitelist_notebooks) != [NOTEBOOK]:
        raise Refused("stage B INDEX must whitelist exactly the pilot notebook")
    mapped = {}
    for doc in index.documents.values():
        (v,) = doc.versions
        if v.mapping is None or v.mapping.notebook_id != NOTEBOOK or v.mapping.sync_sha256 != v.sha256:
            raise Refused(f"{doc.id}: mapping missing, in another notebook, or sync identity != INDEX hash")
        mapped[doc.id] = v.mapping.source_id
    if INJECTION_SOURCE in mapped.values() or len(set(mapped.values())) != 3:
        raise Refused("the M01 injection source is mapped, or two documents share a source id")
    svc = GatewayService(cfg, logger=JsonLogger(stream=io.StringIO(), level="info"))
    for doc in index.documents.values():
        (v,) = doc.versions
        try:
            if svc.local.file_sha256(v.path) != v.sha256:
                raise Refused(f"{doc.id}: local file hash differs from INDEX; stop and report")
        except GatewayError as e:
            raise Refused(f"{doc.id}: {e.code}") from None
    return {"index_sha256": index.sha256, "mapped_source_ids": mapped, "notebook": NOTEBOOK,
            "timeouts": {"timeout_s": cfg.notebooklm.timeout_s, "max_attempts": cfg.notebooklm.max_attempts,
                         "total_budget_s": cfg.notebooklm.total_budget_s}}


def lookup_ok(r: dict) -> bool:
    return r["status"] in ("FOUND", "UNKNOWN") or (r.get("error") or {}).get("code") == "CITED_SOURCE_NOT_WHITELISTED"


def run_cases(run: Run, config: Path, tmp: Path, make_client, mode: str, audit_obj: Audit) -> None:
    """The B2 cases in plan order. Run.case raises StopPilot on the first FAIL, before any later call."""
    audit, expected_sent = audit_obj.entries, audit_obj.expected
    main_client = make_client()
    rec = Recorder(main_client, audit_obj, "main")
    main_cfg = write_temp(tmp, config, mode=mode)
    svc = service(main_cfg, rec)
    try:
        # P5: citation shape; the single query must send exactly the three mapped source ids
        n0 = len(audit)
        r = svc.call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
        run.keep("P5", r)
        mine = audit[n0:]
        ok = (lookup_ok(r) and len(mine) == 1 and mine[0]["requested_source_ids"] == expected_sent
              and mine[0]["outcome"] == "returned")
        run.case("P5", "citation shape of a live semantic lookup (Q-S1)", "PASS" if ok else "FAIL",
                 "exactly one notebook_query sending exactly the 3 mapped source ids; status FOUND/UNKNOWN or "
                 "CITED_SOURCE_NOT_WHITELISTED", {**resp_summary(r), "attempts": [e["attempt"] for e in mine]})
        p5 = r

        # P10: out-of-scope boundary, from the P5 attempt
        # P10-B needs a real trigger under the strict check: an out-of-scope id, or a missing / malformed /
        # contradictory citation entry (citation_problems); a shape the Gateway parses is not a trigger (F13)
        trigger = {"out_of_scope_source_ids": sorted({x for e in mine for x in e.get("out_of_scope_source_ids") or []}),
                   "citation_problems": sorted({x for e in mine for x in e.get("citation_problems") or []})}
        observed = bool(trigger["out_of_scope_source_ids"] or trigger["citation_problems"])
        if not observed:
            run.case("P10", "out-of-scope boundary (P10-A OUT_OF_SCOPE_NOT_OBSERVED)",
                     "PASS" if p5_parsed(mine) else "FAIL",
                     "every cited, referenced and sources_used id in the sent source_ids and every entry well formed; "
                     "live F12 branch not triggered (offline regressions apply)",
                     {"outcome": "OUT_OF_SCOPE_NOT_OBSERVED", "trigger": trigger,
                      "attempts": [e["attempt"] for e in mine]})
        else:
            before = len(audit)
            again = svc.call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
            run.keep("P10 repeat", again)
            discarded = all(x["status"] == "ERROR" and (x.get("error") or {}).get("code") == "CITED_SOURCE_NOT_WHITELISTED"
                            and not x.get("results") for x in (p5, again))
            run.case("P10", "out-of-scope boundary (P10-B OUT_OF_SCOPE_OBSERVED)",
                     "PASS" if discarded and len(audit) == before + 1 else "FAIL",
                     "CITED_SOURCE_NOT_WHITELISTED, no answer/evidence, not cached (repeat queries again), 0 VERIFIED",
                     {"outcome": "OUT_OF_SCOPE_OBSERVED", "trigger": trigger, "first": resp_summary(p5),
                      "repeat": resp_summary(again), "attempts": [e["attempt"] for e in audit[n0:]]})

        # P6: cold vs cache hit (needs a FOUND result from P5)
        if p5["status"] == "FOUND":
            before = len(audit)
            hit = svc.call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
            run.keep("P6", hit)
            ok = (len(audit) == before and hit["status"] == "FOUND"
                  and all(e["RETRIEVAL_PATH"]["cache_hit"] for e in hit["results"])
                  and [e["EVIDENCE_ID"] for e in hit["results"]] == [e["EVIDENCE_ID"] for e in p5["results"]])
            run.case("P6", "same lookup again: cache hit, identity re-checked, no backend call", "PASS" if ok else "FAIL",
                     "FOUND, cache_hit true, same EVIDENCE_IDs, no extra notebook_query", resp_summary(hit))
        else:
            run.case("P6", "cache hit", "NOT_OBSERVED", "needs a FOUND result in P5", {"p5_status": p5["status"]})

        # P7: notebook removed from the whitelist (temporary INDEX copy); both halves are required for PASS
        revoked = write_temp(tmp, config, mode=mode, index_edit=lambda t: t.replace(
            f'notebooklm_notebooks: ["{NOTEBOOK}"]', "notebooklm_notebooks: []"))
        svc7 = service(revoked, rec)
        before = len(audit)
        r7 = svc7.call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
        run.keep("P7 lookup", r7)
        reasons = {x["document_id"]: x["reason"] for x in r7.get("excluded", [])}
        lookup_part = (r7["status"] == "UNKNOWN" and not r7["results"] and len(audit) == before
                       and all(reasons.get(d) == "NOTEBOOK_NOT_WHITELISTED" for d in PILOT_DOCS))
        obs = {"lookup": resp_summary(r7)}
        nb_ev = [e for e in p5.get("results") or [] if e["RETRIEVAL_PATH"]["route"] != "LOCAL"]
        if not lookup_part:
            result = "FAIL"
        elif not nb_ev:
            result = "NOT_OBSERVED"   # no old NotebookLM evidence to verify: the MAPPING half did not occur
            obs["verify"] = "no NotebookLM evidence from P5"
        else:
            v7 = svc7.call("standards_verify", {"evidence": copy.deepcopy(nb_ev[0]), **copy.deepcopy(CTX)})
            run.keep("P7 verify", v7)
            mapping = {c["name"]: c["result"] for c in v7["checks"]}.get("MAPPING")
            result = "PASS" if v7["status"] == "FAILED" and mapping == "FAIL" and len(audit) == before else "FAIL"
            obs["verify"] = resp_summary(v7)
        run.case("P7", "revoked notebook whitelist: excluded, no backend call; old evidence FAILED (MAPPING)", result,
                 "UNKNOWN, all NOTEBOOK_NOT_WHITELISTED, 0 calls; old NotebookLM evidence verify FAILED (MAPPING)", obs)

        # P11: no sync identity for TCVN 8794 (temporary INDEX copy)
        sha8794 = load_index(load_config(config).index_path).documents["TCVN-8794-2011"].versions[0].sha256

        def drop_sync(t: str) -> str:
            head, sep, rest = t.partition(f'sync: {{sha256: "{sha8794}"')
            assert sep, "TCVN 8794 sync entry not found"
            return head + "sync: null" + rest[rest.index("}") + 1:]   # first "}" closes the sync object
        edit11 = drop_sync if P11_EXTRA_INDEX_EDIT is None else (lambda t: P11_EXTRA_INDEX_EDIT(drop_sync(t)))
        nosync = write_temp(tmp, config, mode=mode, index_edit=edit11)
        r11 = service(nosync, rec).call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
        run.keep("P11", r11)
        hits = [e for e in r11.get("results") or [] if e["DOCUMENT"]["id"] == "TCVN-8794-2011"]
        if hits:
            ok = all(e["STATUS"] != "VERIFIED" and "SYNC_IDENTITY_MISSING" in [u["code"] for u in e["UNCERTAINTY"]]
                     for e in hits)
            run.case("P11", "source without sync identity is never VERIFIED", "PASS" if ok else "FAIL",
                     "TCVN 8794 results UNKNOWN with SYNC_IDENTITY_MISSING", resp_summary(r11))
        else:
            run.case("P11", "source without sync identity", "NOT_OBSERVED" if lookup_ok(r11) else "FAIL",
                     "needs a TCVN 8794 citation; none in this response", resp_summary(r11))
    finally:
        close = getattr(main_client, "close", None)
        if close:
            close()

    # P8: timeout recovery with a 1 s budget on a fresh client, then the same client with the normal budget (F14)
    client8 = make_client(slow=True)
    rec8 = Recorder(client8, audit_obj, "p8")
    state = getattr(client8, "process_state", None)   # the real MCP client; fake backends have no server process
    try:
        tight = write_temp(tmp, config, mode=mode, nb_overrides={"timeout_s": 1, "max_attempts": 1, "total_budget_s": 1})
        n0 = len(audit)
        before = state() if state else None
        r8 = service(tight, rec8).call("standards_lookup", {"query": Q_S1 + " (P8)", **copy.deepcopy(CTX)})
        run.keep("P8 tight", r8)
        if (r8.get("error") or {}).get("code") != "TIMEOUT":
            run.case("P8", "1 s budget: structured TIMEOUT", "NOT_OBSERVED" if lookup_ok(r8) else "FAIL",
                     "TIMEOUT (the backend answered within 1 s, so the timeout path did not occur)", resp_summary(r8))
            return
        result, obs = p8_judge_teardown(audit_obj, audit[n0:], state, before)
        obs = {"tight": resp_summary(r8), **obs}
        if result != "PASS":
            run.case("P8", P8_CASE, result, P8_EXPECTED, obs)
            return
        if hasattr(client8, "delay_s"):
            client8.delay_s = 0          # fake only: the recovery call answers in time
        mid = state() if state else None
        r8b = service(main_cfg, rec8).call("standards_lookup", {"query": Q_S1 + " (P8)", **copy.deepcopy(CTX)})
        run.keep("P8 recover", r8b)
        obs["recover"] = resp_summary(r8b)
        ok = lookup_ok(r8b)
        if not state:
            obs["process_model"] = "fake backend: no server process (teardown not applicable)"
            run.case("P8", P8_CASE, "PASS" if ok else "FAIL", P8_EXPECTED, obs)
            return
        after = state()
        old_pids = {x["pid"] for x in mid["spawned"]}
        fresh = [x for x in after["validated_starts"][len(mid["validated_starts"]):] if x["pid"] not in old_pids]
        obs["recover_validated_starts"] = fresh
        ok = ok and bool(fresh) and all(x["tools"] == 4 and x["escaped_processes"] in (0, None) for x in fresh)
        # the recovery server is closed and its tree verified BEFORE the case result is decided (GPT_REVIEW_V1 at
        # 8762641): the result covers the teardown of every process this P8 started, not only the timed-out one
        client8.close()
        result, rec_obs = p8_judge_recovery_teardown(state, mid)
        obs.update(rec_obs)
        run.case("P8", P8_CASE, result if ok else "FAIL", P8_EXPECTED, obs)
    finally:
        close = getattr(client8, "close", None)
        if close:
            close()


P8_CASE = "1 s budget: structured TIMEOUT; process tree retired and verified; next call on a fresh validated server"
P8_EXPECTED = ("TIMEOUT; the timed-out attempt terminal; every server process started for it torn down with the "
               "wrapper exited and the whole tree verified empty; recovery on a new process that passed initialize + "
               "the exact tools/list check; recovery lookup completes; the recovery server then closed with the "
               "wrapper exited, containment available and the whole tree verified empty")


def p5_parsed(attempts: list[dict]) -> bool:
    """P10-A also needs the P5 response to have been readable: returned, and not discarded."""
    return bool(attempts) and all(e["outcome"] == "returned" and not e.get("discarded") for e in attempts)


def teardown_verdict(spawned: list[dict], teardowns: dict[int, dict]) -> str:
    """PASS only if every spawned process has a teardown with the wrapper exited, containment available and the
    whole tree verified empty; BLOCKED if containment was unavailable or the tree could not be checked; else FAIL."""
    if any(s["pid"] not in teardowns for s in spawned):
        return "FAIL"
    if any(teardowns[s["pid"]]["containment"] == "none" or teardowns[s["pid"]]["tree_empty"] is None
           for s in spawned):
        return "BLOCKED" if all(teardowns[s["pid"]]["tree_empty"] is not False for s in spawned) else "FAIL"
    return "PASS" if all(teardowns[s["pid"]]["verified"] for s in spawned) else "FAIL"


def p8_judge_recovery_teardown(state, mid: dict) -> tuple[str, dict]:
    """After client8.close(): the processes spawned since `mid` (the recovery server) must all be torn down and
    verified, and nothing may still be alive."""
    now = state()
    spawned = now["spawned"][len(mid["spawned"]):]
    teardowns = {x["pid"]: x for x in now["teardowns"][len(mid["teardowns"]):]}
    obs = {"recover_spawned": spawned, "recover_teardowns": list(teardowns.values()),
           "process_alive_after_close": now["alive"]}
    if now["alive"] or not spawned:
        return "FAIL", obs
    return teardown_verdict(spawned, teardowns), obs


def p8_judge_teardown(audit_obj: Audit, tight_attempts: list[dict], state, before: dict | None) -> tuple[str, dict]:
    """Judge the timed-out P8 attempt only after it is terminal (bounded wait), then its server processes."""
    numbers = [e["attempt"] for e in tight_attempts]
    terminal = audit_obj.wait_terminal(numbers, P8_TERMINAL_WAIT_S)
    obs = {"tight_attempts": numbers, "tight_terminal": terminal,
           "tight_failed_method": [e.get("failed_method") for e in tight_attempts],
           "tight_sent_to_backend": [e.get("sent_to_backend") for e in tight_attempts]}
    if not terminal or not numbers or any(e["outcome"] == "no_attempt_seen_before_caller_timeout"
                                         for e in tight_attempts):
        return "FAIL", obs
    if not state:
        return "PASS", obs
    now = state()
    spawned = now["spawned"][len(before["spawned"]):]
    teardowns = {x["pid"]: x for x in now["teardowns"][len(before["teardowns"]):]}
    obs.update(process_alive=now["alive"], spawned=spawned, teardowns=list(teardowns.values()))
    if now["alive"]:
        return "FAIL", obs
    return teardown_verdict(spawned, teardowns), obs   # BLOCKED: containment unavailable, teardown unprovable


def execute(config: Path, make_client, *, kind: str, out: Path) -> tuple[int, dict]:
    """Preconditions, the cases (stopping at the first FAIL), the audit, and the two output files."""
    started = dt.datetime.now(dt.timezone.utc)
    summary = {"check": "m02-stage-b", "kind": kind, "head": git_head(),
               "utc_start": started.isoformat(timespec="seconds"), "python": platform.python_version(),
               "platform": platform.platform(), "query": "Q-S1", "assessment_date": DAY, "work_code": WORK_CODE}
    try:
        pre = preconditions(config)
    except (Refused, GatewayError) as e:
        summary.update(status="REFUSED", reason=getattr(e, "code", None) or str(e))
        return 2, summary
    summary.update(pre)
    expected_sent = sorted(pre["mapped_source_ids"].values())
    audit_obj = Audit(expected_sent)
    run, stopped = Run(), None
    with tempfile.TemporaryDirectory(prefix="m02-stage-b-") as tmp:
        try:
            run_cases(run, config, Path(tmp), make_client, "mcp_stdio", audit_obj)
        except StopPilot as e:
            stopped = str(e)
    audit = audit_obj.finalize()          # sealed, immutable snapshot; late workers cannot change it
    done = {c["id"] for c in run.cases}
    for cid in PLANNED:
        if cid not in done:
            run.cases.append({"id": cid, "case": "not run", "result": "NOT_RUN",
                              "expected": "-", "observed": {"stopped_after": stopped}})
    injection = any(INJECTION_SOURCE in e["requested_source_ids"] for e in audit)
    unfinished_outcomes = ("in_flight", "abandoned_unfinished", "no_attempt_seen_before_caller_timeout")
    unfinished = [e["attempt"] for e in audit if e["outcome"] in unfinished_outcomes]
    wrong_set = [e["attempt"] for e in audit if e["outcome"] != "no_attempt_seen_before_caller_timeout"
                 and e["requested_source_ids"] != expected_sent]
    failed = (injection or bool(wrong_set) or bool(unfinished) or audit_obj.tripped is not None
              or any(c["result"] == "FAIL" for c in run.cases)
              or (stopped is not None and not any(c["result"] == "BLOCKED" for c in run.cases)))
    blocked = any(c["result"] == "BLOCKED" for c in run.cases)
    summary.update(cases=run.cases, stopped_after=stopped, source_gate=audit_obj.tripped,
                   notebook_query_attempts=audit, attempt_count=len(audit),
                   sent_to_backend_count=sum(1 for e in audit if e["sent_to_backend"] is True),
                   injection_source_requested=injection, attempts_with_wrong_source_set=wrong_set,
                   unfinished_attempts=unfinished,
                   status="FAIL" if failed else ("BLOCKED" if blocked else "PASS"),
                   utc_end=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    summary = strip_text(summary)
    out.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    (out / f"stage-b-{stamp}.raw.json").write_text(json.dumps({"head": summary["head"], "responses": run.raw},
                                                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary["summary_file"] = str(out / f"stage-b-{stamp}.summary.json")
    Path(summary["summary_file"]).write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return (1 if failed else (3 if blocked else 0)), summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=CONFIG)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true", help="real NotebookLM via the M01 gated server (needs approval)")
    g.add_argument("--fake", choices=("clean", "mixed", "auth"), help="offline fake backend (dry run)")
    ap.add_argument("--out", type=Path, default=HERE / "evidence" / "local")
    args = ap.parse_args()
    config = args.config.resolve()
    cfg = load_config(config)
    if args.live:
        def make_client(slow: bool = False):
            return McpStdioNotebookLMClient(cfg.notebooklm.mcp_config, cfg.notebooklm.server)
        kind = "live NotebookLM (M01 gated server)"
    else:
        def make_client(slow: bool = False):
            fake = fake_client(args.fake)
            fake.delay_s = 1.5 if slow else 0
            return fake
        kind = f"fake:{args.fake}"
    code, summary = execute(config, make_client, kind=kind, out=args.out)
    sys.stdout.reconfigure(errors="backslashreplace")
    if code == 2:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 2
    for c in summary["cases"]:
        print(f"{c['result']:12} {c['id']:5} {c['case']}")
    print(f"notebook_query attempts: {summary['attempt_count']} (sent to backend: {summary['sent_to_backend_count']}); "
          f"source gate: {summary['source_gate'] or 'ok'}")
    print(f"STATUS: {summary['status']}" + (f" (stopped after {summary['stopped_after']})" if summary["stopped_after"] else ""))
    print(f"[stage-b] summary (committable): {summary['summary_file']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
