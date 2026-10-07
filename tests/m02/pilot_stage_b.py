#!/usr/bin/env python3
"""M02 bounded pilot, stage B (B2): the Gateway's semantic route against NotebookLM. docs/M02_PILOT_PLAN.md §6b.

NOT AUTHORIZED TO RUN LIVE until GPT review of this script and the owner's direct approval of B2.

The committed config `docs/m02-pilot/gateway.pilot.stage-b.json` keeps `notebooklm.mode: disabled`. With `--live`
the runner writes a temporary copy with `mode: mcp_stdio` (never committed); the Gateway then starts the M01 gated
server from the project `.mcp.json` and refuses any tool surface other than the four M01 read tools. The runner
itself only calls `standards_lookup` / `standards_verify`; the Gateway sends `notebook_query` with the mapped source
ids only. No notebook_get, source_get_content, upload or change. `--fake clean|mixed` runs the same cases offline
against tests/m02/fake_notebooklm.py (no Google contact), for dry runs on make_pilot_synthetic.py output.

Cases (plan §6b): P5 citation shape, P6 cold vs cache, P7 revoked notebook whitelist, P8 timeout recovery,
P10 out-of-scope boundary (P10-A OUT_OF_SCOPE_NOT_OBSERVED or P10-B OUT_OF_SCOPE_OBSERVED), P11 no sync identity.
P9 (model surface) and the preflights are separate commands (see the plan). A case whose precondition did not occur
(e.g. no FOUND result to re-use for P6) is reported NOT_OBSERVED, never PASS.

Recorded per notebook_query (summary): sent source ids, result key names, citation item key names, citation and
sources_used counts, cited / used source ids, whether a citation lacked a source id, answer length. Never the answer
text, passages or excerpts. Outputs under tests/m02/evidence/local/ (git-ignored): stage-b-<ts>.summary.json (ids,
statuses, codes, counts, key names, timings) and stage-b-<ts>.raw.json (full Gateway responses; local only).
Exit code: 0 no FAIL, 1 any FAIL, 2 refused to start.

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
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from gateway.adapters.notebooklm import McpStdioNotebookLMClient  # noqa: E402
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


class Recorder:
    """Wraps the NotebookLM client; records the response shape (ids, key names, counts), never text."""

    def __init__(self, inner):
        self.inner = inner
        self.queries: list[dict] = []

    def notebook_query(self, notebook_id, query, source_ids):
        sent = sorted(source_ids)
        t0 = time.monotonic()
        result = self.inner.notebook_query(notebook_id, query, source_ids)
        raw = result.get("citations") if isinstance(result, dict) else None
        items = list(raw.values()) if isinstance(raw, dict) else list(raw or [])
        cited, unattributed, item_keys = set(), False, set()
        for it in items:
            if isinstance(it, dict):
                item_keys.update(it.keys())
                sid = it.get("source_id")
                if isinstance(sid, str) and sid:
                    cited.add(sid)
                else:
                    unattributed = True
            else:
                unattributed = True
        used = result.get("sources_used") if isinstance(result, dict) else None
        used_ids = sorted({u for u in (used or []) if isinstance(u, str) and u})
        unattributed = unattributed or any(not (isinstance(u, str) and u) for u in (used or []))
        outside = sorted((cited | set(used_ids)) - set(sent))
        self.queries.append({
            "notebook_id": notebook_id, "sent_source_ids": sent, "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "status": result.get("status") if isinstance(result, dict) else None,
            "result_keys": sorted(result.keys()) if isinstance(result, dict) else [],
            "citations_container": type(raw).__name__, "citation_item_keys": sorted(item_keys),
            "citation_count": len(items), "cited_source_ids": sorted(cited), "sources_used": used_ids,
            "unattributed_citation": unattributed, "out_of_scope_source_ids": outside,
            "answer_chars": len(result.get("answer") or "") if isinstance(result, dict) else 0,
        })
        return result

    def notebook_list(self):                       # not used by the stage B cases
        raise GatewayError("SOURCE_NOT_ALLOWED", "stage B runner does not list notebooks")

    def notebook_get(self, notebook_id):
        raise GatewayError("SOURCE_NOT_ALLOWED", "stage B runner does not call notebook_get (B0 is separate)")

    def source_get_content(self, source_id):
        raise GatewayError("SOURCE_NOT_ALLOWED", "stage B runner never reads NotebookLM source content")


def fake_client(scenario: str):
    """Offline stand-in for the synthetic library: cites the mapped TCVN 8794 source (and, for 'mixed', the M01
    injection source too)."""
    from fake_notebooklm import FakeNotebookLM
    cites = [{"source_id": "8ccb8115-f552-4ecb-b42a-f0ee093f1d08",
              "passage": "Yêu cầu giả lập về chiếu sáng lớp học trường trung học."}]
    if scenario == "mixed":
        cites.append({"source_id": INJECTION_SOURCE, "passage": "(fake) chỉ dẫn nhúng"})
    return FakeNotebookLM({NOTEBOOK: {"answer": "(fake) câu trả lời giả lập", "citations": cites}})


class Run:
    def __init__(self):
        self.cases: list[dict] = []
        self.raw: list[dict] = []

    def case(self, cid, desc, result, expected, observed):
        self.cases.append({"id": cid, "case": desc, "result": result, "expected": expected, "observed": observed})

    def keep(self, label, payload):
        self.raw.append({"label": label, "response": payload})


def service(config: Path, client) -> GatewayService:
    return GatewayService(load_config(config), notebooklm_client=client,
                          logger=JsonLogger(stream=io.StringIO(), level="info"))


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


def run_cases(run: Run, config: Path, tmp: Path, make_client, mode: str, recorder: Recorder) -> None:
    main_cfg = write_temp(tmp, config, mode=mode)
    svc = service(main_cfg, recorder)

    # P5: citation shape (Q-S1 without document_id, semantic route over the three mapped sources)
    n0 = len(recorder.queries)
    r = svc.call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
    run.keep("P5", r)
    ok_status = r["status"] in ("FOUND", "UNKNOWN") or (r.get("error") or {}).get("code") == "CITED_SOURCE_NOT_WHITELISTED"
    run.case("P5", "citation shape of a live semantic lookup (Q-S1)",
             "PASS" if ok_status and len(recorder.queries) == n0 + 1 else "FAIL",
             "one notebook_query with the 3 mapped source ids; status FOUND/UNKNOWN or CITED_SOURCE_NOT_WHITELISTED",
             {**resp_summary(r), "query_shape": recorder.queries[n0:]})
    p5 = r

    # P10: out-of-scope boundary, classified from every notebook_query of the run so far
    shapes = recorder.queries[n0:]
    observed = any(q["out_of_scope_source_ids"] or q["unattributed_citation"] for q in shapes)
    if not observed:
        run.case("P10", "out-of-scope boundary (P10-A OUT_OF_SCOPE_NOT_OBSERVED)", "PASS",
                 "every cited/used id is in the sent source_ids; live F12 branch not triggered (offline regressions apply)",
                 {"outcome": "OUT_OF_SCOPE_NOT_OBSERVED", "sent": [q["sent_source_ids"] for q in shapes],
                  "cited": [q["cited_source_ids"] for q in shapes], "used": [q["sources_used"] for q in shapes]})
    else:
        before = len(recorder.queries)
        again = svc.call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
        run.keep("P10 repeat", again)
        discarded = all(x["status"] == "ERROR" and (x.get("error") or {}).get("code") == "CITED_SOURCE_NOT_WHITELISTED"
                        and not x.get("results") for x in (p5, again))
        run.case("P10", "out-of-scope boundary (P10-B OUT_OF_SCOPE_OBSERVED)",
                 "PASS" if discarded and len(recorder.queries) == before + 1 else "FAIL",
                 "CITED_SOURCE_NOT_WHITELISTED, no answer/evidence, not cached (repeat queries again), 0 VERIFIED",
                 {"outcome": "OUT_OF_SCOPE_OBSERVED", "first": resp_summary(p5), "repeat": resp_summary(again),
                  "out_of_scope": [q["out_of_scope_source_ids"] for q in shapes]})

    # P6: cold vs cache hit (needs a FOUND result from P5)
    if p5["status"] == "FOUND":
        before = len(recorder.queries)
        hit = svc.call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
        run.keep("P6", hit)
        ok = (len(recorder.queries) == before and hit["status"] == "FOUND"
              and all(e["RETRIEVAL_PATH"]["cache_hit"] for e in hit["results"])
              and [e["EVIDENCE_ID"] for e in hit["results"]] == [e["EVIDENCE_ID"] for e in p5["results"]])
        run.case("P6", "same lookup again: cache hit, identity re-checked, no backend call", "PASS" if ok else "FAIL",
                 "FOUND, cache_hit true, same EVIDENCE_IDs, no extra notebook_query", resp_summary(hit))
    else:
        run.case("P6", "cache hit", "NOT_OBSERVED", "needs a FOUND result in P5", {"p5_status": p5["status"]})

    # P7: notebook removed from the whitelist (temporary INDEX copy)
    revoked = write_temp(tmp, config, mode=mode, index_edit=lambda t: t.replace(f'notebooklm_notebooks: ["{NOTEBOOK}"]',
                                                                            "notebooklm_notebooks: []"))
    svc7 = service(revoked, recorder)
    before = len(recorder.queries)
    r7 = svc7.call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
    run.keep("P7 lookup", r7)
    reasons = {x["document_id"]: x["reason"] for x in r7.get("excluded", [])}
    ok = (r7["status"] == "UNKNOWN" and not r7["results"] and len(recorder.queries) == before
          and all(reasons.get(d) == "NOTEBOOK_NOT_WHITELISTED" for d in PILOT_DOCS))
    obs = {"lookup": resp_summary(r7)}
    nb_ev = [e for e in p5.get("results") or [] if e["RETRIEVAL_PATH"]["route"] != "LOCAL"]
    if nb_ev:
        v7 = svc7.call("standards_verify", {"evidence": copy.deepcopy(nb_ev[0]),
                                             **{k: v for k, v in CTX.items()}})
        run.keep("P7 verify", v7)
        ok = ok and v7["status"] == "FAILED" and {c["name"]: c["result"] for c in v7["checks"]}.get("MAPPING") == "FAIL"
        obs["verify"] = resp_summary(v7)
    run.case("P7", "revoked notebook whitelist: excluded, no backend call; old evidence FAILED (MAPPING)",
             "PASS" if ok else "FAIL", "UNKNOWN, all NOTEBOOK_NOT_WHITELISTED, 0 calls; verify FAILED", obs)

    # P11: no sync identity for TCVN 8794 (temporary INDEX copy)
    sha8794 = load_index(load_config(config).index_path).documents["TCVN-8794-2011"].versions[0].sha256

    def drop_sync(t: str) -> str:
        return t.replace(f'sync: {{sha256: "{sha8794}", synced_at: "2026-10-06T00:00:00Z"}}', "sync: null", 1)
    nosync = write_temp(tmp, config, mode=mode, index_edit=drop_sync)
    r11 = service(nosync, recorder).call("standards_lookup", {"query": Q_S1, **copy.deepcopy(CTX)})
    run.keep("P11", r11)
    hits = [e for e in r11.get("results") or [] if e["DOCUMENT"]["id"] == "TCVN-8794-2011"]
    if hits:
        ok = all(e["STATUS"] != "VERIFIED" and "SYNC_IDENTITY_MISSING" in [u["code"] for u in e["UNCERTAINTY"]]
                 for e in hits)
        run.case("P11", "source without sync identity is never VERIFIED", "PASS" if ok else "FAIL",
                 "TCVN 8794 results UNKNOWN with SYNC_IDENTITY_MISSING", resp_summary(r11))
    else:
        run.case("P11", "source without sync identity", "NOT_OBSERVED" if r11["status"] != "ERROR" or
                 (r11.get("error") or {}).get("code") == "CITED_SOURCE_NOT_WHITELISTED" else "FAIL",
                 "needs a TCVN 8794 citation; none in this response", resp_summary(r11))

    # P8: timeout recovery with a 1 s budget on a fresh client, then the same client with the normal budget
    client8 = make_client()
    rec8 = Recorder(client8)
    tight = write_temp(tmp, config, mode=mode, nb_overrides={"timeout_s": 1, "max_attempts": 1, "total_budget_s": 1})
    r8 = service(tight, rec8).call("standards_lookup", {"query": Q_S1 + " (P8)", **copy.deepcopy(CTX)})
    run.keep("P8 tight", r8)
    timed_out = (r8.get("error") or {}).get("code") == "TIMEOUT"
    proc = getattr(client8, "_proc", None)
    retired = proc is None or proc.poll() is not None
    r8b = service(main_cfg, rec8).call("standards_lookup", {"query": Q_S1 + " (P8)", **copy.deepcopy(CTX)})
    run.keep("P8 recover", r8b)
    recovered = r8b["status"] in ("FOUND", "UNKNOWN") or (r8b.get("error") or {}).get("code") == "CITED_SOURCE_NOT_WHITELISTED"
    if timed_out:
        result = "PASS" if retired and recovered else "FAIL"
    else:
        result = "NOT_OBSERVED" if r8["status"] != "ERROR" else "FAIL"
    run.case("P8", "1 s budget: structured TIMEOUT, process retired; next call on a fresh validated server", result,
             "TIMEOUT, server process gone, next lookup completes", {"tight": resp_summary(r8),
             "process_retired": retired, "recover": resp_summary(r8b)})
    close = getattr(client8, "close", None)
    if close:
        close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=CONFIG)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true", help="real NotebookLM via the M01 gated server (needs approval)")
    g.add_argument("--fake", choices=("clean", "mixed"), help="offline fake backend (dry run)")
    ap.add_argument("--out", type=Path, default=HERE / "evidence" / "local")
    args = ap.parse_args()
    config = args.config.resolve()
    started = dt.datetime.now(dt.timezone.utc)
    summary = {"check": "m02-stage-b", "kind": "live NotebookLM (M01 gated server)" if args.live else f"fake:{args.fake}",
               "head": git_head(), "utc_start": started.isoformat(timespec="seconds"),
               "python": platform.python_version(), "platform": platform.platform(), "query": "Q-S1",
               "assessment_date": DAY, "work_code": WORK_CODE}
    try:
        summary.update(preconditions(config))
    except (Refused, GatewayError) as e:
        summary.update(status="REFUSED", reason=getattr(e, "code", None) or str(e))
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 2
    cfg = load_config(config)
    if args.live:
        def make_client():
            return McpStdioNotebookLMClient(cfg.notebooklm.mcp_config, cfg.notebooklm.server)
    else:
        def make_client():
            fake = fake_client(args.fake)
            fake.delay_s = 0
            return fake
    run = Run()
    main_client = make_client()
    recorder = Recorder(main_client)
    with tempfile.TemporaryDirectory(prefix="m02-stage-b-") as tmp:
        if not args.live:   # make the fake slow only for the tight-budget P8 call
            orig = make_client

            def make_client():
                fake = orig()
                fake.delay_s = 1.5
                return fake
        try:
            run_cases(run, config, Path(tmp), make_client, "mcp_stdio", recorder)
        finally:
            close = getattr(main_client, "close", None)
            if close:
                close()
    queries = recorder.queries
    summary.update(cases=run.cases, notebook_queries=queries,
                   injection_source_sent=any(INJECTION_SOURCE in q["sent_source_ids"] for q in queries),
                   status="FAIL" if any(c["result"] == "FAIL" for c in run.cases) else "PASS",
                   utc_end=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    if summary["injection_source_sent"]:
        summary["status"] = "FAIL"
    summary = strip_text(summary)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    (args.out / f"stage-b-{stamp}.raw.json").write_text(json.dumps({"head": summary["head"], "responses": run.raw},
                                                                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sum_path = args.out / f"stage-b-{stamp}.summary.json"
    sum_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(errors="backslashreplace")
    for c in run.cases:
        print(f"{c['result']:12} {c['id']:5} {c['case']}")
    print(f"STATUS: {summary['status']}")
    print(f"[stage-b] summary (committable): {sum_path}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
