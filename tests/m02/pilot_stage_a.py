#!/usr/bin/env python3
"""M02 bounded pilot, stage A (local only, notebooklm.mode=disabled). docs/M02_PILOT_PLAN.md §6, §6a.

Runs on the owner's machine, non-elevated, after the owner's direct approval and a PASS from
scripts/m02/pilot/stage-a-preflight.ps1. It reads only the three files named in the pilot INDEX, through the
Gateway's own read-only local adapter. It never writes under the source root, never calls NotebookLM and never
edits the pilot INDEX (P4 uses a temporary copy).

  discover  load each pilot document; record extraction status, line/section counts and section IDs; run Q-S1
            (TCVN 8794 by document_id -> CANDIDATES; without document_id -> UNKNOWN, every document excluded as
            MAPPING_MISSING, 0 NotebookLM calls).
            Gives the clause IDs the owner picks the P1 clauses from. Candidates are never exact clauses.
  run       P1-P4 with owner-confirmed clauses:  --p1 DOC_ID=CLAUSE (once per document)

Two outputs per run, both under tests/m02/evidence/local/ (git-ignored):
  stage-a-<mode>-<ts>.raw.json      full Gateway responses, including excerpts (local only, never committed)
  stage-a-<mode>-<ts>.summary.json  IDs, statuses, codes, check results, counts, hashes and timings only;
                                    no source text, excerpt, heading or answer. Only this file may be committed.
Exit code: 0 all cases PASS, 1 any FAIL, 2 refused to start (config/INDEX/hash precondition).

  uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z \
      tests/m02/pilot_stage_a.py discover
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import io
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from gateway.clauses import canonical_clause  # noqa: E402
from gateway.config import load_config  # noqa: E402
from gateway.errors import GatewayError  # noqa: E402
from gateway.index import load_index  # noqa: E402
from gateway.logs import JsonLogger  # noqa: E402
from gateway.service import GatewayService  # noqa: E402

CONFIG = REPO / "docs" / "m02-pilot" / "gateway.pilot.stage-a.json"
PILOT_DOCS = ("LUAT-135-2025-QH15", "TCVN-5575-2024", "TCVN-8794-2011")
WORK_CODE = "THIET-KE-DAN-DUNG"
DAY = "2026-10-06"
Q_S1 = "Tiêu chuẩn thiết kế chiếu sáng lớp học trường trung học"
# Only owner-confirmed condition answers (plan §3). COND-KET-CAU-THEP is unknown and is never set.
CONTEXT = {"TCVN-8794-2011": {"conditions": {"COND-TRUONG-TRUNG-HOC": True}}}
EXPECTED_P1 = {"LUAT-135-2025-QH15": "VERIFIED", "TCVN-5575-2024": "UNKNOWN", "TCVN-8794-2011": "VERIFIED"}
TEXT_KEYS = ("EVIDENCE", "ANSWER")   # carry source/answer text: never in the summary


class Refused(Exception):
    pass


def git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              timeout=30).stdout.strip() or None
    except OSError:
        return None


def make_service(config: Path) -> tuple[GatewayService, io.StringIO]:
    logs = io.StringIO()
    svc = GatewayService(load_config(config), logger=JsonLogger(stream=logs, level="info"))
    return svc, logs


def preconditions(config: Path) -> tuple[dict, dict[str, str]]:
    """Refuse unless the config is the disabled, three-document pilot and every file hash equals INDEX."""
    cfg = load_config(config)
    if cfg.notebooklm.mode != "disabled":
        raise Refused(f"notebooklm.mode is {cfg.notebooklm.mode!r}; stage A requires 'disabled'")
    index = load_index(cfg.index_path)
    docs = index.documents
    if tuple(sorted(docs)) != tuple(sorted(PILOT_DOCS)) or not all(index.is_whitelisted(d) for d in PILOT_DOCS):
        raise Refused("pilot INDEX must hold and whitelist exactly the three pilot documents")
    svc, _ = make_service(config)
    observed, expected = {}, {}
    for doc_id in PILOT_DOCS:
        (version,) = docs[doc_id].versions
        expected[version.path] = version.sha256
        try:
            observed[version.path] = svc.local.file_sha256(version.path)   # confinement checks apply
        except GatewayError as e:
            raise Refused(f"{doc_id}: {e.code}") from None
    if observed != expected:
        raise Refused("a pilot file hash differs from the pilot INDEX; stop and report")
    meta = {"config": config.relative_to(REPO).as_posix() if config.is_relative_to(REPO) else config.name,
            "notebooklm_mode": cfg.notebooklm.mode, "index_version": index.index_version,
            "index_sha256": index.sha256, "documents": list(PILOT_DOCS),
            "limits": {"max_source_bytes": cfg.limits.max_source_bytes,
                       "max_docx_uncompressed_bytes": cfg.limits.max_docx_uncompressed_bytes}}
    return meta, observed


def strip_text(obj):
    """Summary view: drop every text-bearing field (excerpts, answers, headings, details with text)."""
    if isinstance(obj, list):
        return [strip_text(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if k in TEXT_KEYS:
            out[k] = {"present": v is not None and bool(v.get("text")) if isinstance(v, dict) else v is not None}
        elif k in ("detail", "disclaimer", "notes", "message", "heading", "basis"):
            continue
        else:
            out[k] = strip_text(v)
    return out


def ev_summary(ev: dict) -> dict:
    return {"EVIDENCE_ID": ev["EVIDENCE_ID"], "STATUS": ev["STATUS"], "DOCUMENT": (ev["DOCUMENT"] or {}).get("id"),
            "VERSION": ev["VERSION"], "CLAUSE": (ev["CLAUSE"] or {}).get("id"), "SOURCE_HASH": ev["SOURCE_HASH"],
            "APPLICABILITY": ev["APPLICABILITY"]["status"],
            "missing": list(ev["APPLICABILITY"].get("missing", [])),
            "route": ev["RETRIEVAL_PATH"]["route"], "cache_hit": ev["RETRIEVAL_PATH"]["cache_hit"],
            "uncertainty": [u["code"] for u in ev["UNCERTAINTY"]],
            "truncated": ev["EVIDENCE"]["truncated"], "layout_dependent": ev["EVIDENCE"]["layout_dependent"]}


def resp_summary(r: dict) -> dict:
    out = {"status": r["status"], "notebooklm_calls": r.get("notebooklm_calls"), "timing_ms": r.get("timing_ms"),
           "error": (r.get("error") or {}).get("code"), "missing_inputs_count": len(r.get("missing_inputs", []))}
    if r.get("excluded"):
        out["excluded"] = [{"document_id": x["document_id"], "reason": x["reason"]} for x in r["excluded"]]
    if "results" in r:
        out["results"] = [ev_summary(e) for e in r["results"]]
    if "checks" in r:
        out["checks"] = {c["name"]: c["result"] for c in r["checks"]}
    return out


class Run:
    def __init__(self, mode: str, config: Path):
        self.mode, self.config = mode, config
        self.cases: list[dict] = []
        self.raw: list[dict] = []

    def case(self, cid: str, desc: str, ok: bool, expected: str, observed: dict) -> None:
        self.cases.append({"id": cid, "case": desc, "result": "PASS" if ok else "FAIL", "expected": expected,
                           "observed": observed})

    def keep(self, label: str, payload: dict) -> None:
        self.raw.append({"label": label, "response": payload})


def lookup_args(doc_id: str | None, **extra) -> dict:
    args = {"work_code": WORK_CODE, "assessment_date": DAY}
    if doc_id:
        args["document_id"] = doc_id
        if doc_id in CONTEXT:
            args["project_context"] = copy.deepcopy(CONTEXT[doc_id])
    args.update(extra)
    return {k: v for k, v in args.items() if v is not None}


def discover(run: Run) -> None:
    svc, _ = make_service(run.config)
    index = load_index(load_config(run.config).index_path)
    for doc in index.documents.values():
        (version,) = doc.versions
        try:
            local = svc.local.load(version)
        except GatewayError as e:
            run.case(f"D-{doc.id}", "load and parse the pilot document", False, "document loads",
                     {"error": e.code})
            continue
        levels: dict[int, int] = {}
        for s in local.sections:
            levels[s.level] = levels.get(s.level, 0) + 1
        ids = [s.id for s in local.sections]
        run.keep(f"outline {doc.id}", {"sections": [{"id": s.id, "level": s.level, "heading": s.heading}
                                                   for s in local.sections]})
        run.case(f"D-{doc.id}", "load and parse the pilot document", bool(ids), "document loads, >=1 section",
                 {"format": version.format, "clause_scheme": version.clause_scheme, "bytes": local.size,
                  "lines": len(local.text.lines), "layout_lines": len(local.text.layout_lines),
                  "sections": len(ids), "sections_by_level": levels, "section_ids": ids})
    r = svc.call("standards_lookup", lookup_args("TCVN-8794-2011", query=Q_S1, max_results=5))
    run.keep("Q-S1 TCVN-8794-2011", r)
    run.case("Q-S1-doc", "Q-S1 with document_id TCVN-8794-2011 (keyword heuristic)",
             r["status"] in ("CANDIDATES", "UNKNOWN") and r["notebooklm_calls"] == 0,
             "CANDIDATES (or UNKNOWN if nothing matches), 0 NotebookLM calls; candidates are not exact clauses",
             resp_summary(r))
    r = svc.call("standards_lookup", lookup_args(None, query=Q_S1))
    run.keep("Q-S1 no document", r)
    run.case("Q-S1-nodoc", "Q-S1 without document_id while NotebookLM is disabled",
             r["status"] == "UNKNOWN" and not r["results"] and r["notebooklm_calls"] == 0
             and sorted(x["document_id"] for x in r["excluded"] if x["reason"] == "MAPPING_MISSING") == sorted(PILOT_DOCS),
             "UNKNOWN, no results, all three documents excluded as MAPPING_MISSING, 0 NotebookLM calls",
             resp_summary(r))


def p_run(run: Run, p1: dict[str, str]) -> None:
    svc, _ = make_service(run.config)
    docs = load_index(load_config(run.config).index_path).documents
    evidence: dict[str, dict] = {}

    # P1: exact/local lookup of each owner-confirmed clause
    for doc_id, clause in p1.items():
        canon = canonical_clause(clause, docs[doc_id].versions[0].clause_scheme)
        r = svc.call("standards_lookup", lookup_args(doc_id, query=f"{doc_id} {clause}", clause=clause))
        run.keep(f"P1 {doc_id}", r)
        res = r.get("results") or []
        ok = (r["status"] == "FOUND" and len(res) == 1 and (res[0]["CLAUSE"] or {}).get("id") == canon and r["notebooklm_calls"] == 0
              and res[0]["RETRIEVAL_PATH"]["route"] == "LOCAL" and res[0]["STATUS"] == EXPECTED_P1[doc_id])
        if doc_id == "TCVN-5575-2024" and res:
            ok = ok and any("COND-KET-CAU-THEP" in m for m in res[0]["APPLICABILITY"].get("missing", []))
        run.case(f"P1-{doc_id}", f"exact/local lookup of owner-confirmed clause {canon}", ok,
                 f"FOUND, CLAUSE {canon}, route LOCAL, 0 NotebookLM calls, STATUS {EXPECTED_P1[doc_id]}"
                 + (" (COND-KET-CAU-THEP unknown)" if doc_id == "TCVN-5575-2024" else ""), resp_summary(r))
        if res:
            evidence[doc_id] = res[0]

    # P2: verify the genuine evidence, then tampered copies (in memory only)
    for doc_id, ev in evidence.items():
        ctx = {k: v for k, v in lookup_args(doc_id).items() if k != "document_id"}
        r = svc.call("standards_verify", {"evidence": copy.deepcopy(ev), **ctx})
        run.keep(f"P2 genuine {doc_id}", r)
        identity_ok = all(c["result"] in ("PASS", "SKIPPED") for c in r["checks"] if c["name"] != "APPLICABILITY")
        run.case(f"P2-genuine-{doc_id}", "standards_verify on the genuine P1 evidence",
                 r["status"] == EXPECTED_P1[doc_id] and identity_ok,
                 f"{EXPECTED_P1[doc_id]}; every identity check PASS (MAPPING SKIPPED for LOCAL)", resp_summary(r))
        r = svc.call("standards_verify", {"evidence_id": ev["EVIDENCE_ID"], **ctx})
        run.keep(f"P2 by id {doc_id}", r)
        run.case(f"P2-by-id-{doc_id}", "standards_verify by evidence_id", r["status"] == EXPECTED_P1[doc_id],
                 EXPECTED_P1[doc_id], resp_summary(r))
    target = evidence.get("TCVN-8794-2011") or next(iter(evidence.values()), None)
    if target is not None:
        ctx = {k: v for k, v in lookup_args(target["DOCUMENT"]["id"]).items() if k != "document_id"}
        other = "0" if target["CLAUSE"]["id"] != "0" else "1"
        tampers = {
            "clause": lambda e: e["CLAUSE"].__setitem__("id", other),
            "source_hash": lambda e: e["SOURCE_HASH"].update(expected="0" * 64, observed="0" * 64),
            "excerpt": lambda e: e["EVIDENCE"].__setitem__("text", (e["EVIDENCE"]["text"] or "") + " x"),
            "version": lambda e: e.__setitem__("VERSION", "1999"),
        }
        for name, edit in tampers.items():
            bad = copy.deepcopy(target)
            edit(bad)
            r = svc.call("standards_verify", {"evidence": bad, **ctx})
            run.keep(f"P2 tampered {name}", r)
            run.case(f"P2-tampered-{name}", f"standards_verify on evidence with a tampered {name} (JSON copy)",
                     r["status"] == "FAILED", "FAILED", resp_summary(r))

    # P3: missing inputs / unknown conditions stay UNKNOWN
    if "TCVN-8794-2011" in p1:
        clause = p1["TCVN-8794-2011"]
        variants = {
            "no-work-code": (lookup_args("TCVN-8794-2011", query=f"TCVN-8794-2011 {clause}", clause=clause,
                                         work_code=None), "work_code"),
            "no-condition": ({"query": f"TCVN-8794-2011 {clause}", "clause": clause, "document_id": "TCVN-8794-2011",
                              "work_code": WORK_CODE, "assessment_date": DAY}, "COND-TRUONG-TRUNG-HOC"),
        }
        no_wc = variants["no-work-code"][0]
        no_wc.pop("work_code", None)
        for name, (args, needle) in variants.items():
            r = svc.call("standards_lookup", args)
            run.keep(f"P3 {name}", r)
            res = r.get("results") or []
            ok = bool(res) and res[0]["STATUS"] == "UNKNOWN" and any(
                needle in m for m in res[0]["APPLICABILITY"].get("missing", []))
            run.case(f"P3-{name}", f"TCVN 8794 clause lookup with {name.replace('-', ' ')}", ok,
                     f"STATUS UNKNOWN, missing lists {needle}", resp_summary(r))
    if "TCVN-5575-2024" in evidence:
        ev = evidence["TCVN-5575-2024"]
        run.case("P3-cond-ket-cau-thep-unknown", "TCVN 5575 with COND-KET-CAU-THEP unknown (from P1)",
                 ev["STATUS"] == "UNKNOWN", "STATUS UNKNOWN, never VERIFIED", {"result": ev_summary(ev)})

    # P4: drift simulated in a temporary copy of the pilot INDEX (real INDEX and files untouched)
    if evidence:
        doc_id = "TCVN-8794-2011" if "TCVN-8794-2011" in evidence else next(iter(evidence))
        ev = evidence[doc_id]
        cfg = load_config(run.config)
        real_sha = docs[doc_id].versions[0].sha256
        with tempfile.TemporaryDirectory(prefix="m02-stage-a-p4-") as tmp:
            tmp_index = Path(tmp) / "INDEX.pilot.p4.yaml"
            text = cfg.index_path.read_text(encoding="utf-8")
            assert text.count(real_sha) == 1
            tmp_index.write_text(text.replace(real_sha, "f" * 64), encoding="utf-8")
            tmp_cfg = Path(tmp) / "gateway.pilot.p4.json"
            data = json.loads(run.config.read_text(encoding="utf-8-sig"))
            data["index_path"] = str(tmp_index)
            data["source_root"] = str(cfg.source_root)
            tmp_cfg.write_text(json.dumps(data), encoding="utf-8")
            drift_svc, _ = make_service(tmp_cfg)
            clause = p1[doc_id]
            r = drift_svc.call("standards_lookup", lookup_args(doc_id, query=f"{doc_id} {clause}", clause=clause))
            run.keep("P4 lookup", r)
            run.case("P4-lookup", "lookup after INDEX hash drift (temporary INDEX copy)",
                     r["status"] == "ERROR" and (r["error"] or {}).get("code") == "SOURCE_DRIFT" and not r["results"],
                     "ERROR SOURCE_DRIFT, no results", resp_summary(r))
            ctx = {k: v for k, v in lookup_args(doc_id).items() if k != "document_id"}
            r = drift_svc.call("standards_verify", {"evidence": copy.deepcopy(ev), **ctx})
            run.keep("P4 verify", r)
            run.case("P4-verify", "verify P1 evidence against the drifted INDEX copy",
                     r["status"] not in ("VERIFIED",) and r["status"] in ("FAILED", "ERROR"),
                     "FAILED or ERROR, never VERIFIED", resp_summary(r))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("discover", "run"))
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--p1", action="append", default=[], metavar="DOC_ID=CLAUSE")
    ap.add_argument("--out", type=Path, default=HERE / "evidence" / "local")
    args = ap.parse_args()
    config = args.config.resolve()
    p1 = {}
    for item in args.p1:
        doc_id, _, clause = item.partition("=")
        if doc_id not in PILOT_DOCS or not clause:
            ap.error(f"--p1 {item!r}: expected DOC_ID=CLAUSE with DOC_ID in {PILOT_DOCS}")
        p1[doc_id] = clause
    if args.mode == "run" and not p1:
        ap.error("run needs at least one --p1 DOC_ID=CLAUSE (owner-confirmed)")

    started = dt.datetime.now(dt.timezone.utc)
    summary = {"check": f"m02-stage-a-{args.mode}", "kind": "M02 pilot stage A, local only, NotebookLM disabled",
               "head": git_head(), "utc_start": started.isoformat(timespec="seconds"),
               "python": platform.python_version(), "platform": platform.platform(), "assessment_date": DAY,
               "work_code": WORK_CODE, "p1_clauses": p1}
    run = Run(args.mode, config)
    try:
        meta, before = preconditions(config)
    except (Refused, GatewayError) as e:
        summary.update(status="REFUSED", reason=getattr(e, "code", None) or str(e))
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 2
    summary.update(meta, hashes_before=before)
    if args.mode == "discover":
        discover(run)
    else:
        p_run(run, p1)
    try:
        _, after = preconditions(config)
    except (Refused, GatewayError) as e:
        after = {"error": getattr(e, "code", None) or str(e)}
    unchanged = after == before
    run.case("SOURCE-UNCHANGED", "pilot file hashes after the run equal the hashes before and INDEX", unchanged,
             "identical", {"hashes_after": after})
    summary.update(hashes_after=after, source_unchanged=unchanged, cases=run.cases,
                   status="PASS" if all(c["result"] == "PASS" for c in run.cases) else "FAIL",
                   utc_end=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    summary = strip_text(summary)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    raw_path = args.out / f"stage-a-{args.mode}-{stamp}.raw.json"
    sum_path = args.out / f"stage-a-{args.mode}-{stamp}.summary.json"
    raw_path.write_text(json.dumps({"head": summary["head"], "responses": run.raw}, indent=2, ensure_ascii=False)
                        + "\n", encoding="utf-8")
    sum_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(errors="backslashreplace")
    for c in run.cases:
        print(f"{c['result']:4}  {c['id']:32} {c['case']}")
    print(f"STATUS: {summary['status']}")
    print(f"[stage-a] summary (committable): {sum_path}")
    print(f"[stage-a] raw (local only, contains source text): {raw_path}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
