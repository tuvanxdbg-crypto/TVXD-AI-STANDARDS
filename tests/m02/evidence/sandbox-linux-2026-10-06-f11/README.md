# M02 F11 patch: Linux sandbox evidence (2026-10-06)

M02_PATCH_AMBIGUOUS_CLAUSE_RESOLUTION_ONLY (GPT_REVIEW_V1 at `fb14c65`). Offline only: fixture and synthetic data,
NotebookLM disabled, no real document.

- Code commit: `f9c69463e746baab73c946a6399f54eb179e0863`.
- Environment: Linux sandbox, Python 3.11.15 (uv 0.8.17), PyYAML 6.0.2.

| File | What | Result |
|---|---|---|
| `m02-suite-run1.txt` … `run3.txt` | full verbose output of `python -m unittest discover -v -s tests/m02 -p 'test_gateway_*.py'`, three consecutive runs | each: 114 run, OK, 4 skipped (Windows-only controls) |
| `synthetic-stage-a-discover.summary.json` | `pilot_stage_a.py discover` on `make_pilot_synthetic.py` output (no real content) | PASS |
| `synthetic-stage-a-run.txt`, `synthetic-stage-a-run.summary.json` | `pilot_stage_a.py run`, including `PA-ambiguous-TCVN-8794-2011` (the synthetic 8794 has a table of contents, so "1" occurs twice) | PASS; PA returns `ERROR CLAUSE_AMBIGUOUS`, 2 occurrences, no results |

Revert check (not a file here): with the pre-fix Gateway and the new tests, the five `F11AmbiguousClause` tests
fail (2 errors, 3 failures).

The ambiguous probes on the three real pilot files need a new run on the owner's machine with the owner's
approval. That run is `pilot_stage_a.py run` at this commit; see the report.
