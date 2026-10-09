# Contract-v2 stage B plan draft: offline validation (sandbox Linux, 2026-10-09)

Scope: NEXT_ALLOWED_STEP `OWNER_PROVIDE_BOUNDED_LIVE_SOURCE_SET_AND_AUTHORIZE_CONTRACT_V2_STAGE_B_PLAN_DRAFT_ONLY`,
from the GPT_REVIEW_V1 PASS at `727ae61`.
- The owner kept the B0/B1 bounded set (Claude chat, 2026-10-09):
  - notebook `8ca84143-…` (TVXD-M01-TEST);
  - its three mapped sources;
  - authorization for the plan draft only.
- Plan: `docs/M02_PILOT_PLAN.md` §6c.

Run details:
- Code-tested commit: `d007e4e8e13839d1d96c92e236e0c41c9dbf411f`, a fresh detached worktree, unchanged after the
  runs (`worktree-status-after.txt` is empty).
- Environment: Linux cloud container; uv 0.8.17, Python 3.11.15, PyYAML 6.0.2 (`env.txt`).
- Offline only:
  - fixtures, fake NotebookLM backends and local stand-ins;
  - no NotebookLM, login or `mcp_stdio` against the real server;
  - no local library file read.

| File | Result |
|---|---|
| `m02-suite-x3.txt` | M02 suite, 3 consecutive verbose runs: each 185 tests OK, 8 skipped (Windows-only controls) |
| `m01-regression-and-secret-scan.txt` | M01-09 secret scan PASS (314 tracked files at `d007e4e`); M01-10 checker controls OK; console encoding OK |
| `fake-runs.txt` | `pilot_stage_b.py --fake` on `make_pilot_synthetic.py` output: `clean` PASS, `mixed` PASS, `auth` FAIL at P5 (exit 1), with the new P5 contract-v2 evidence gate |
| `preflight-v2-runs.txt` | `pilot_stage_b_v2_preflight.py` on the clean worktree. See the two runs below |
| `preflight-v2-wrong-expect-head.summary.json` | the summary of the negative run |
| `run_evidence.sh` | the producing script (paths sanitized, so not runnable as is) |

The two preflight runs in `preflight-v2-runs.txt`:
- **With `--expect-head d007e4e…`:** every non-token check PASSes (HEAD, tree, committed configs disabled, stage-B
  scope, M01 server pin). The token checks are NOT_APPLICABLE, so the status is `NOT_A_LIVE_HOST` (exit 3). PASS is
  possible only on Windows.
- **With a wrong `--expect-head`:** `HEAD_IS_APPROVED` FAIL, status FAIL (exit 1).

Both runs started in the same second, so they wrote the same summary file name and the second overwrote the first.
The surviving summary, renamed here, is the negative run. Both console outputs are in `preflight-v2-runs.txt`.

This round has no real Claude Code run. The model-visible harness and the Gateway are unchanged since the owner's
Windows acceptance at `f9c1061`.

No credentials, cookies, real document text or raw transcripts are included.
