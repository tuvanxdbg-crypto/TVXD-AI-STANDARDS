# M02 stage-B runner gates and synced_at provenance: Linux sandbox evidence (2026-10-07)

M02_PATCH_B1_PROVENANCE_AND_B2_RUNNER_GATES_ONLY (GPT_REVIEW_V1 at `32b8705`). Offline only: synthetic stand-in
files (`make_pilot_synthetic.py`) and the fake NotebookLM backend. No Google contact; the committed stage-B config
stays `notebooklm.mode: disabled`.

- Code commit: `cb956a1b500bde7b6b85863e69032b88a3a9f476`.
- Environment: Linux sandbox, Python 3.11.15 (uv 0.8.17), PyYAML 6.0.2.

| File | What | Result |
|---|---|---|
| `m02-suite-run1.txt` … `run3.txt` | full verbose M02 suite, three consecutive runs (incl. `test_gateway_pilot_stage_b.py` and `SyncedAtPrecision`) | each: 127 run, OK, 4 skipped |
| `fake-clean.txt`, `fake-clean.summary.json` | `pilot_stage_b.py --fake clean` | PASS: P5, P10-A, P6, P7, P11, P8; 4 audited attempts (main ×2, p8 ×2) |
| `fake-mixed.txt`, `fake-mixed.summary.json` | `--fake mixed` (mapped source + injection source cited) | PASS: P5, P10-B, P8; P6/P7/P11 NOT_OBSERVED |
| `fake-auth.txt`, `fake-auth.summary.json` | `--fake auth` (expired login) | FAIL at P5, run stopped: 1 attempt, P10–P8 NOT_RUN, exit 1 |

The summaries carry ids, key names, counts and statuses only (no answer or passage text). `summary_file` paths
replaced by `<scratch>`.
