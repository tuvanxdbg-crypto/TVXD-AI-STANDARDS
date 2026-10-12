#!/usr/bin/env python3
"""Regenerate the sample reports in tests/m04/evidence/ with the real CLI and the real report writer.

For every fixture group (PASS, FAIL, UNKNOWN) and rule file it runs `cadaudit check` and writes
evidence/report_<input>__<rules>.json. For the input-error fixtures it records the exit code and error code in
evidence/input_errors.json (an error run writes no report). The report writer never overwrites, so this script first
deletes the sample files it generated earlier (only names it owns, only inside evidence/).

  python tests/m04/make_evidence.py     # from the repository root, Python 3.11 + pyyaml

Everything here is FIXTURE data (fake). generated_at in the samples is the time of the regeneration.
"""
import io
import json
import os
import re
import sys
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from cadaudit import cli  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
EVD = os.path.join(HERE, "evidence")
GROUPS = {"pass": "cad_read_pass.json", "fail": "cad_read_fail.json", "unknown": "cad_read_unknown.json"}
RULES = {"internal": "rules_internal.yaml", "standard": "rules_standard.yaml"}
INPUT_ERRORS = ["error_bad_schema.json", "error_read_mode_read_write.json", "error_duplicate_handle.json",
                "error_coverage_inconsistent.json", "error_dangling_reference.json"]
RULE_ERRORS = ["rules_error_unknown_check.yaml", "rules_error_hint_not_required.yaml", "rules_error_bad_schema.yaml",
               "rules_error_not_yaml_object.yaml"]


def run(args):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = cli.main(args)
    return code, err.getvalue().strip()


def main():
    os.makedirs(EVD, exist_ok=True)
    for name in os.listdir(EVD):
        if re.fullmatch(r"report_[a-z]+__[a-z]+\.json", name):
            os.unlink(os.path.join(EVD, name))
    for g, inp in GROUPS.items():
        for r, rules in RULES.items():
            out = os.path.join(EVD, f"report_{g}__{r}.json")
            code, err = run(["check", "--input", os.path.join(FIX, inp), "--rules", os.path.join(FIX, rules), "--out", out])
            print(f"report_{g}__{r}.json exit={code} {err}")
            if code != 0:
                raise SystemExit(1)
    errors = []
    scratch = os.path.join(EVD, "report_must_not_exist.json")
    cases = [(os.path.join(FIX, n), os.path.join(FIX, "rules_internal.yaml"), n) for n in INPUT_ERRORS]
    cases += [(os.path.join(FIX, "cad_read_pass.json"), os.path.join(FIX, "errors", n), n) for n in RULE_ERRORS]
    for inp, rules, label in cases:
        code, err = run(["check", "--input", inp, "--rules", rules, "--out", scratch])
        errors.append({"case": label, "exit_code": code, "stderr": err, "report_created": os.path.lexists(scratch)})
    with open(os.path.join(EVD, "input_errors.json"), "wb") as f:
        f.write((json.dumps({"note": "FIXTURE data. An input or rules error stops the run and writes no report.",
                             "cases": errors}, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps(errors, indent=1))


if __name__ == "__main__":
    main()
