# F14 Windows suspended start: Linux validation (sandbox, 2026-10-09)

Patch for GPT_REVIEW_V1 at `b869e798a7a35a7f00d0c27ff3922c32655d2fa6`.
- Decision: PATCH_REQUIRED.
- NEXT_ALLOWED_STEP: `M02_PATCH_F14_WINDOWS_SUSPENDED_START_CONTAINMENT_RACE_ONLY`.
- Design: `docs/M02_STANDARDS_GATEWAY.md` §20.

Run details:
- Code-tested commit: `981f15db385559a7b8096641959a6479a1c486b4`, a fresh detached worktree.
- The worktree was unchanged after the runs (`worktree-status-after.txt`, empty). It was also unchanged after the
  revert check restored the file (`worktree-status-after-revert-check.txt`, empty).
- Environment (`env.txt`):
  - Linux cloud container;
  - uv 0.8.17, Python 3.11.15, PyYAML 6.0.2;
  - Claude Code 2.1.295;
  - runtime `uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z`.

Offline only:
- fixtures, fake NotebookLM backends and local Python stand-ins;
- every committed config stays `notebooklm.mode: disabled`;
- no NotebookLM, login or live run.

**This is Linux evidence.**
- The Windows path (`CREATE_SUSPENDED`, job assignment, `ResumeThread`) and the 4 new Windows-only regressions do
  not run here. They are skipped.
- They need the owner's Windows offline run after review.

| File | Result | Kind |
|---|---|---|
| `m02-suite-x3.txt` | M02 suite, 3 consecutive verbose runs: each 176 tests OK, 8 skipped (4 Windows junction/reparse controls, 4 Windows suspended-start tests) | mock / local stand-ins |
| `revert-check.txt` | `gateway/adapters/notebooklm.py` from `eec1680` against the new F13/F14 tests: 2 failures, 3 errors. The tests are `test_containment_unavailable_is_blocked_not_pass`, `test_uncontained_start_is_refused_before_any_request`, `test_popen_kwargs_and_resume_rules`, `test_repeated_starts_never_escape_and_always_close_verified` and `test_tight_start_containment_unavailable_is_blocked` | test-suite strength |
| `fake-runs.txt` | stage-B runner on the fake backends: `clean` PASS (exit 0), `mixed` PASS (exit 0), `auth` FAIL at P5 (exit 1) | mock |
| `standin-runs.txt`, `standin-{startup,call}-stage-b.summary.json` | whole stage-B runner against the real MCP client and `fake_uvx_wrapper.py` → `fake_mcp_server.py`: both variants PASS. In P8, every spawned server has `resumed: true` and every teardown is verified | local stand-ins |
| `m01-regression-and-secret-scan.txt` | M01-09 secret scan PASS (293 tracked files at `981f15d`); M01-10 checker controls OK; console encoding OK | regression |
| `claude-code-gateway-surface-clean-run1.json` | `m02_surface.py surface`: PASS | real Claude Code, fixture Gateway |
| `claude-code-gateway-llm-run{1,2}.json` | `m02_surface.py llm`: PASS with 14/14 checks; exactly one `standards_lookup`; fake backend exactly `["notebook_query"]` | real Claude Code, temporary mcp_stdio config, fake NotebookLM |
| `runs.txt`, `run_evidence.sh` | exit codes, and the producing script (paths sanitized, so not runnable as is) | — |

The `surface`/`llm` runs use an empty `CLAUDE_CONFIG_DIR` in the session scratch area, with plugin/skill sync unset
for the child process only. This is the same as the earlier rounds: this container syncs plugin MCP servers from
the account.

No credentials, cookies, real document text or raw transcripts are included. Paths are replaced by `<repo>`,
`<scratch>`, `<tmp>`, `<repo-main>` and `<home>`.
