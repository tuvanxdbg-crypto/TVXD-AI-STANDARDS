"""Build the report dictionary (D5) and the bytes that get written. Deterministic: rules in file order, objects in
input order, fixed key order. generated_at is the only time-dependent field and is passed in by the caller.
"""
import json

from . import __version__, _schema
from .errors import CadAuditError
from .evaluator import RuleResult
from .loader import Drawing
from .model import VERDICTS
from .rules import RuleSet

NOTICE = "Báo cáo này không kết luận bản vẽ đạt tiêu chuẩn, tính hợp pháp hay sự phù hợp thiết kế."


def build_report(drawing: Drawing, ruleset: RuleSet, results: list, generated_at: str) -> dict:
    rules_out, rows_out = [], []
    for res in results:
        r = res.rule
        rules_out.append({
            "rule_id": r.id, "title": r.title, "rule_status": r.status, "classification": r.classification,
            "classification_reason": r.classification_reason, "standard_hint": r.standard_hint,
            "applies_to": r.applies_to, "reads_groups": list(r.reads_groups), "verdict": res.verdict,
            "reasons": list(res.reasons), "coverage_complete": res.coverage_complete,
            "objects_in_scope": len(res.rows), "counts": dict(res.counts), "evidence_ids": list(res.evidence_ids),
        })
        for row in res.rows:
            rows_out.append({
                "rule_id": row.rule_id, "rule_status": row.rule_status, "classification": row.classification,
                "handle": row.handle, "verdict": row.verdict, "reason": row.reason,
                "evidence_ids": list(row.evidence_ids), "actual": row.actual, "expected": row.expected,
                "standard_hint": row.standard_hint,
            })
    by_rule = {v: sum(1 for x in rules_out if x["verdict"] == v) for v in VERDICTS}
    by_result = {v: sum(1 for x in rows_out if x["verdict"] == v) for v in VERDICTS}
    by_status = {s: sum(1 for x in rules_out if x["rule_status"] == s) for s in ("FIXTURE", "PROPOSED", "APPROVED")}
    if by_rule["FAIL"]:
        overall = "HAS_FAIL"
    elif by_rule["UNKNOWN"]:
        overall = "HAS_UNKNOWN"
    else:
        overall = "ALL_RULES_PASS"
    all_approved = bool(rules_out) and by_status["APPROVED"] == len(rules_out)
    report = {
        "schema": "tvxd.cadaudit.report/v1",
        "cadaudit_version": __version__,
        "generated_at": generated_at,
        "notice": NOTICE,
        "input": {"file_id": drawing.file_id, "input_sha256": drawing.input_sha256, "dwg_sha256": drawing.dwg_sha256},
        "rules_file": {"sha256": ruleset.sha256, "rules_version": ruleset.rules_version},
        "rules": rules_out,
        "results": rows_out,
        "summary": {"rules_by_verdict": by_rule, "results_by_verdict": by_result, "rules_by_status": by_status,
                    "overall": overall, "all_rules_approved": all_approved},
    }
    if overall == "ALL_RULES_PASS" and not all_approved:
        report["summary"]["overall_note"] = "RULES_NOT_APPROVED"   # a pass against FIXTURE/PROPOSED rules is not a pass
    problems = _self_check(report)
    if problems:
        raise CadAuditError("INTERNAL_REPORT_INVALID", problems[0], exit_code=70)
    return report


def _self_check(report: dict) -> list:
    """The report must satisfy its own schema; every FAIL/UNKNOWN has evidence; PASS is never mixed with STD."""
    problems = _schema.check(report, "cad_audit_report.v1.json")
    for x in report["rules"] + report["results"]:
        if x["verdict"] in ("FAIL", "UNKNOWN") and not x["evidence_ids"]:
            problems.append(f"{x['rule_id']}: {x['verdict']} without evidence id")
        if x["classification"] == "STANDARD_REQUIRED" and x["verdict"] != "UNKNOWN":
            problems.append(f"{x['rule_id']}: STANDARD_REQUIRED must be UNKNOWN")
    return problems


def report_bytes(report: dict) -> bytes:
    return (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
