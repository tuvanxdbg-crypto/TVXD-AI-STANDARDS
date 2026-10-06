# M02 F12 patch: Linux sandbox evidence (2026-10-06)

M02_PATCH_OUT_OF_SCOPE_NOTEBOOKLM_RESPONSE_FAIL_CLOSED_ONLY (GPT_REVIEW_V1 at `a9877ec`). Offline only: fixture data
and the fake NotebookLM backend; `notebooklm.mode` stays `disabled` in every committed config; no NotebookLM call.

- Code commit: `028535df96d06b478f334850d82d2df61941dc32`.
- Environment: Linux sandbox, Python 3.11.15 (uv 0.8.17), PyYAML 6.0.2.

| File | What | Result |
|---|---|---|
| `m02-suite-run1.txt` … `run3.txt` | full verbose output of `python -m unittest discover -v -s tests/m02 -p 'test_gateway_*.py'`, three consecutive runs | each: 121 run, OK, 4 skipped (Windows-only controls) |

Revert check (not a file here): with the pre-fix Gateway and the new tests, the six new negative tests fail
(5 errors, 1 failure). The all-whitelisted and queried-set controls pass on both.
