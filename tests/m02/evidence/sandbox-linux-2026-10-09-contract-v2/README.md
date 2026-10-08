# Contract v2 (M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE) offline validation (sandbox Linux, 2026-10-09)

Scope: `M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE_OFFLINE_IMPLEMENTATION_AND_EXACT_HEAD_REVIEW`.
- Authority: OWNER_ARCHITECTURE_CHANGE_V1 at the top of Issue #2 and #4, plus the owner's direct confirmation in the
  Claude chat on 2026-10-09.
- Base: `6f5a48d9eaf37fc9592a6703acecc86e05e01a6e`.
- Offline only: fixtures, the fake NotebookLM backend, and local Python stand-ins for the MCP server tree.
- No NotebookLM, no login, no live B2/P9, no change to sources, notebook, deployment config, pin, ACL, credentials
  or permissions. Every committed config stays `notebooklm.mode: disabled`.
- Runtime: `uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z`.

Files:
- **`m02-suite-x3.txt`:** the M02 suite, 3 consecutive verbose runs, each 153 tests OK, 4 skipped.
  - The skips are the 4 Windows-only junction/reparse controls, which now run against `LocalSourceAdapter` directly.
- **`fake-runs.txt`:** `pilot_stage_b.py --fake clean|mixed|auth` on `make_pilot_synthetic.py` output.

  | Fake | Status | Exit | Detail |
  |---|---|---|---|
  | `clean` | PASS | 0 | P7 FAILED on `NOTEBOOK_SCOPE`; P11 shows a missing sync identity is not blocking and is marked not checked |
  | `mixed` | PASS | 0 | P10-B |
  | `auth` | FAIL at P5 | 1 | |

- **`standin_run.py`, `standin-runs.txt`, `standin-{startup,call}-stage-b.summary.json`:** the whole stage-B runner
  against the real MCP client and `fake_uvx_wrapper.py` → `fake_mcp_server.py`.
  - All six cases PASS.
  - P8 keeps the F14 gates: both teardowns verified, and recovery on a new validated pid.

Not covered here (open):
- the Windows offline run at this HEAD (job object, junction controls);
- the real Claude Code surface check (`m02_surface.py`);
- any live NotebookLM behaviour.

Synthetic stand-in data only; temporary paths are replaced by `<synthetic>` / `<tmp>`.
