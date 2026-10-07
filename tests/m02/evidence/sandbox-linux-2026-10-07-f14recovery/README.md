# F14 recovery teardown gate (sandbox Linux, 2026-10-07)

Scope: NEXT_ALLOWED_STEP `M02_PATCH_F14_RECOVERY_TEARDOWN_GATE_ONLY` (GPT_REVIEW_V1 at `8762641`). Offline only:
no NotebookLM, no B2 or P9 re-run. Runtime: `uv run --no-project --python 3.11 --with pyyaml==6.0.2
--exclude-newer 2026-10-03T00:00:00Z`.

Files:
- `m02-suite-x3.txt`: the M02 suite, 3 consecutive verbose runs, each 157 tests OK, 4 skipped (Windows-only).
- `revert-check.txt`: the two new negative tests against the runner at `8762641`. Both report `(0, 'PASS')`, so
  both tests fail there.
- `standin_run.py`, `standin-runs.txt` and `standin-{startup,call}-stage-b.summary.json`: the whole runner against
  the real MCP client and the two-process stand-in. All six cases PASS. The P8 summary holds:
  - the timed-out teardown (`startup_failure` or `retire`, verified);
  - the recovery teardown (`close`, process_group, `tree_empty: true`, verified).
- `fake-runs.txt`:

  | Fake | Status | Exit |
  |---|---|---|
  | `clean` | PASS | 0 |
  | `mixed` | PASS | 0 |
  | `auth` | FAIL at P5 | 1 |

Not proven here: the Windows job-object path. It needs an offline run on the owner's machine.
