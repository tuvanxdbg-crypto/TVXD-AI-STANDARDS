"""Pure pipeline: bytes in, report dictionary out. No file is written here."""
import datetime

from .evaluator import evaluate_rule
from .loader import load_cad_read
from .report import build_report
from .rules import load_rules

UTC7 = datetime.timezone(datetime.timedelta(hours=7))


def now_iso() -> str:
    """Current time as ISO 8601 in UTC+7 (the only non-deterministic value in a report)."""
    return datetime.datetime.now(UTC7).isoformat(timespec="seconds")


def run_audit(input_bytes: bytes, rules_bytes: bytes, generated_at: str | None = None) -> dict:
    drawing = load_cad_read(input_bytes)
    ruleset = load_rules(rules_bytes)
    results = [evaluate_rule(rule, drawing) for rule in ruleset.rules]
    return build_report(drawing, ruleset, results, generated_at or now_iso())
