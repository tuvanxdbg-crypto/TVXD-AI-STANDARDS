# M02 stage-B runner: per-attempt source gate and terminal audit, Linux sandbox evidence (2026-10-07)

M02_PATCH_B2_PER_ATTEMPT_GATE_AND_TERMINAL_AUDIT_ONLY (GPT_REVIEW_V1 at `221f300`). Offline only: synthetic stand-in
files and the fake NotebookLM backend. No Google contact; the committed stage-B config stays `notebooklm.mode:
disabled`.

- Code commit: `38467cb53088c61cf8a445e493ef244c16638259`.
- Environment: Linux sandbox, Python 3.11.15 (uv 0.8.17), PyYAML 6.0.2.

| File | What | Result |
|---|---|---|
| `m02-suite-run1.txt` … `run3.txt` | full verbose M02 suite, three consecutive runs (incl. 8 stage-B runner regressions) | each: 130 run, OK, 4 skipped |
| `fake-clean.*` | `pilot_stage_b.py --fake clean` | PASS; 4 attempts, all terminal: main returned ×2, p8 `returned_after_caller_timeout` (caller `ERROR:TIMEOUT`, 1500 ms), p8 returned |
| `fake-mixed.*` | `--fake mixed` | PASS: P10-B; P6/P7/P11 NOT_OBSERVED |
| `fake-auth.*` | `--fake auth` | FAIL at P5, stopped, 1 attempt |

No summary contains `in_flight`, answer or passage text, or a scratch path.
