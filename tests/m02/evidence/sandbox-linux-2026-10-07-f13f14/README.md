# F13 / F14 patch validation (sandbox Linux, 2026-10-07)

Scope: NEXT_ALLOWED_STEP `M02_PATCH_F13_CITATION_NORMALIZATION_AND_F14_TIMEOUT_PROCESS_AUDIT_ONLY`
(GPT_REVIEW_V1 at `17090da`). Offline only: no NotebookLM, no `mcp_stdio` against the real server, no B2 or P9
re-run. Runtime: `uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z`.

Files:
- `m02-suite-x3.txt`: the M02 suite, 3 consecutive verbose runs. Each ran 155 tests: OK, 4 skipped (Windows-only).
- `fake-runs.txt` and `fake-stage-b-*.summary.json`: `pilot_stage_b.py --fake clean|mixed|auth` on
  `make_pilot_synthetic.py` output. The fakes now return the notebooklm-mcp-cli 0.15.1 shape.

  | Fake | Status | Exit | Detail |
  |---|---|---|---|
  | `clean` | PASS | 0 | P10-A, trigger empty |
  | `mixed` | PASS | 0 | P10-B, trigger = the injection source id |
  | `auth` | FAIL at P5, stopped | 1 | |

- `standin_run.py`, `standin-runs.txt` and `standin-{startup,call}-stage-b.summary.json`: the whole runner against
  the real `McpStdioNotebookLMClient` and `fake_uvx_wrapper.py` → `fake_mcp_server.py`. This is a two-process
  tree, like `uvx.exe` → `notebooklm-mcp`. All six cases PASS in both variants.

  | Variant | P8 timed-out attempt | Teardown | Recovery |
  |---|---|---|---|
  | startup | `initialize`, `sent_to_backend: false` | `startup_failure`, process_group, wrapper exited, tree empty, verified | new validated pid |
  | call | `tools/call`, `sent_to_backend: true` | `retire`, verified | new validated pid |

Not proven here: the Windows job-object path. Its tests are in the same files and need an offline run on the
owner's machine.

Synthetic stand-in data only; temporary paths are replaced by `<synthetic>` / `<tmp>`.
