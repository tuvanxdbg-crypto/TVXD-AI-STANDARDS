# M02 stage-B runner: late-open seal gate, Linux sandbox evidence (2026-10-07)

M02_PATCH_B2_LATE_OPEN_SEAL_GATE_ONLY (GPT_REVIEW_V1 at `c85671a`). Offline only: synthetic stand-in files and the fake
NotebookLM backend. No Google contact; the committed stage-B config stays `notebooklm.mode: disabled`.

- Code commit: `aa9deb6402523743a38e01fc3c489038a77f826f`.
- Environment: Linux sandbox, Python 3.11.15 (uv 0.8.17), PyYAML 6.0.2.

| File | What | Result |
|---|---|---|
| `m02-suite-run1.txt` … `run3.txt` | full verbose M02 suite, three consecutive runs, incl. `test_sealed_audit_refuses_a_late_open_before_transport` and `test_worker_that_opens_only_after_the_seal_never_sends_and_run_cannot_pass` | each: 133 run, OK, 4 skipped |
| `fake-clean.*`, `fake-mixed.*`, `fake-auth.*` | `pilot_stage_b.py --fake clean|mixed|auth` | PASS / PASS (P10-B) / FAIL at P5, stopped (as expected) |

Revert check (not a file here): both new regressions fail against the previous runner (`c85671a`). The late-open
run reports `(0, 'PASS')` instead of `(1, 'FAIL')`, and the sealed audit does not refuse the late open.

No summary contains `in_flight`, `abandoned`, `no_attempt_seen`, answer or passage text, or a scratch path.
