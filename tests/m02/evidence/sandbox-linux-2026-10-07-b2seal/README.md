# M02 stage-B runner: unfinished-worker fail-closed and sealed audit, Linux sandbox evidence (2026-10-07)

M02_PATCH_B2_ABANDONED_AUDIT_FAIL_CLOSED_ONLY (GPT_REVIEW_V1 at `3ebef42`). Offline only: synthetic stand-in files and
the fake NotebookLM backend. No Google contact; the committed stage-B config stays `notebooklm.mode: disabled`.

- Code commit: `69340ae3863ab837730d1c8789a354a004eae0bf`.
- Environment: Linux sandbox, Python 3.11.15 (uv 0.8.17), PyYAML 6.0.2.

| File | What | Result |
|---|---|---|
| `m02-suite-run1.txt` … `run3.txt` | full verbose M02 suite, three consecutive runs, incl. `test_worker_outliving_finalize_fails_closed_and_snapshot_is_immutable` | each: 131 run, OK, 4 skipped |
| `fake-clean.*`, `fake-mixed.*`, `fake-auth.*` | `pilot_stage_b.py --fake clean|mixed|auth` | PASS / PASS (P10-B) / FAIL at P5, stopped (as expected) |

Revert check (not a file here): the new abandoned-worker regression against the previous runner (`3ebef42`) fails
with `(0, 'PASS') != (1, 'FAIL')`, i.e. the old runner reported a false PASS.

No summary contains `in_flight`, `abandoned`, answer or passage text, or a scratch path.
