"""Command line: python -m cadaudit check --input <cad_read.json> --rules <rules.yaml> --out <report.json>

Exit codes: 0 report written; 2 input/rules error; 3 output refused or failed; 70 internal error.
On any error no report file is created.
"""
import argparse
import sys

from . import __version__
from ._report_writer import check_target, write_report
from .audit import run_audit
from .errors import CadAuditError
from .loader import read_file_bytes
from .model import MAX_INPUT_BYTES, MAX_RULES_BYTES
from .report import report_bytes


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cadaudit", description="Read-only CAD audit on a CAD_READ JSON file (offline).")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="apply a rule file to a CAD_READ file and write a new report file")
    c.add_argument("--input", required=True, help="CAD_READ JSON file (read only)")
    c.add_argument("--rules", required=True, help="rules YAML file (read only, yaml.safe_load)")
    c.add_argument("--out", required=True, help="report .json file to create; must not exist, never overwritten")
    return p


def main(argv=None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:  # argparse already printed the usage error
        return e.code if isinstance(e.code, int) else 2
    try:
        check_target(args.out, args.input, args.rules)  # fail fast; write_report checks again right before writing
        input_bytes = read_file_bytes(args.input, MAX_INPUT_BYTES, "INPUT")
        rules_bytes = read_file_bytes(args.rules, MAX_RULES_BYTES, "RULES")
        report = run_audit(input_bytes, rules_bytes)
        write_report(args.out, report_bytes(report), args.input, args.rules)
    except CadAuditError as e:
        print(f"cadaudit {__version__}: ERROR {e.code}: {e.message}", file=sys.stderr)
        return e.exit_code
    except Exception as e:  # noqa: BLE001 - fail closed: nothing has been written before write_report
        print(f"cadaudit {__version__}: ERROR INTERNAL: {type(e).__name__}", file=sys.stderr)
        return 70
    print(f"cadaudit {__version__}: report written, overall={report['summary']['overall']}")
    return 0
