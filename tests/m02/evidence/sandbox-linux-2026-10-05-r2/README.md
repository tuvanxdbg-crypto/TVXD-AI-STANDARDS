# M02 offline validation evidence, review round 2 (Linux sandbox, 2026-10-05)

OFFLINE fixture validation only, for the fixes to GPT_REVIEW_V1 at `d35b574` (findings F1–F7). This is not M02
overall PASS and not a real-library or real-NotebookLM result. Code commit:
`ce98fc15b94513e3a7178dd6f3dddecde92d506c`. Environment: Linux cloud container, Python 3.11.15 (uv), PyYAML 6.0.2,
uv 0.8.17, pwsh 7.6.2, Claude Code 2.1.289. The round-1 evidence in `../sandbox-linux-2026-10-05/` describes `d35b574`.

| File | What | Kind |
|---|---|---|
| `unit-tests.txt` | 92 M02 unit/contract tests (71 earlier + 21 F1–F7 regressions), verbose list, all OK | mock (fixture library, fake NotebookLM backend, offline MCP stand-ins, real stdio subprocesses) |
| `revert-check.txt` | each F1–F7 fix reverted separately (F1 also check by check, F6 hit and miss): exactly the matching regression class fails every time | test-suite strength |
| `m02-tests-ps1.txt` | `scripts/m02/m02-tests.ps1` under pwsh on a fresh worktree: M02 tests, M01 checker/console tests, M01-09 (112 files) PASS | runner, mock + regression |
| `claude-code-gateway-surface.json` | Claude Code locked to the fixture Gateway: model sees exactly the 3 Gateway tools, one connected server, no built-ins, no NotebookLM tools | real Claude Code, fixture Gateway |
| `claude-code-gateway-llm.json` | Claude looks up the injection fixture via `standards_lookup`: only the Gateway tool called, canary reported, embedded instructions detected and not followed, no file created, fixture tree unchanged | real Claude Code, fixture Gateway |
| `m01-regression.txt` | `m01-acceptance.ps1 -SurfaceOnly -LlmSelfTest` on a fresh worktree of the code commit: M01-09, probe 53→4 and 49/49 `Unknown tool`, locked surface 4 tools, ordinary session 0 NotebookLM tools, M01-10 harness self-test PASS | M01 regression (NotebookLM not logged in) |

The two Claude Code checks ran from the working tree whose content was then committed unchanged as the code commit.
Paths are replaced with `<repo>`, `<tmp>` and `<scratch>`. No credentials, cookies, source text of real documents or
raw transcripts are included; the only document text in the Claude results is the repo's own fake fixture.
