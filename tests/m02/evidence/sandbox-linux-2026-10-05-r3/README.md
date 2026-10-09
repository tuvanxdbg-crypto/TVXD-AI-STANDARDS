# M02 offline validation evidence, review round 3 (Linux sandbox, 2026-10-05)

OFFLINE fixture validation only, for the fixes to GPT_REVIEW_V1 at `eeb76bc` (findings F8–F9; F1–F7 were confirmed
fixed by that review). Not M02 overall PASS; no real library, no NotebookLM call. Code commit:
`e361f4261b696097598b3352d944923a9fea74e8`. Environment: Linux cloud container, Python 3.11.15 (uv), PyYAML 6.0.2,
uv 0.8.17, pwsh 7.6.2, Claude Code 2.1.289. Earlier rounds: `../sandbox-linux-2026-10-05/` (`d35b574`) and
`../sandbox-linux-2026-10-05-r2/` (`ce98fc1`).

| File | What | Kind |
|---|---|---|
| `unit-tests.txt` | 100 M02 unit/contract tests (92 earlier + 8 F8–F9 regressions), verbose list, all OK | mock (fixture library, fake NotebookLM backend, offline MCP stand-in with timestamped call log) |
| `revert-check.txt` | F1–F7 reverts (each still caught by its class) and F8/F9 reverts: all of F8 → 4 tests fail, F9 → 4 tests fail (one hangs and is killed); layered F8 guards reported separately | test-suite strength |
| `m02-tests-ps1.txt` | `scripts/m02/m02-tests.ps1` under pwsh on a fresh worktree: M02 100/100, M01 checker/console tests, M01-09 (119 files) PASS | runner, mock + regression |
| `claude-code-gateway-surface.json` | Claude Code locked to the fixture Gateway sees exactly the 3 Gateway tools, one server, no built-ins, no NotebookLM tools | real Claude Code, fixture Gateway |
| `claude-code-gateway-llm.json` | injection fixture via `standards_lookup`: only the Gateway tool called, canary reported, embedded instructions detected and not followed | real Claude Code, fixture Gateway |
| `m01-regression.txt` | `m01-acceptance.ps1 -SurfaceOnly -LlmSelfTest` on a fresh worktree of the code commit: all PASS | M01 regression (NotebookLM not logged in) |

All runs used a fresh worktree of the code commit. Paths are replaced with `<repo>`, `<tmp>` and `<scratch>`. No
credentials, cookies, real document text or raw transcripts are included.
