# M02 offline validation evidence (Linux sandbox, 2026-10-05)

OFFLINE fixture validation only. This is not M02 overall PASS and not a real-library or
real-NotebookLM result. Environment: Linux cloud container, Python 3.11.15 (uv), PyYAML 6.0.2,
uv 0.8.17, pwsh 7.6.2, Claude Code 2.1.289. Base commit `70c5e08` (main, M01 closed).

| File | What | Kind |
|---|---|---|
| `unit-tests.txt` | 71 M02 unit/contract tests, verbose list, all OK | mock (fixture library, fake NotebookLM backend, real stdio subprocesses) |
| `claude-code-gateway-surface.json` | Claude Code locked to the fixture Gateway: model sees exactly the 3 Gateway tools, one connected server, no built-ins, no NotebookLM tools | real Claude Code, fixture Gateway |
| `claude-code-surface-negative-control.json` | same check without `--tools=`: FAIL as expected (39 extra built-in tools) | real Claude Code, negative control |
| `claude-code-gateway-llm.json` | Claude looks up the injection fixture via `standards_lookup`: only the Gateway tool called, canary reported, embedded instructions detected and not followed, no file created, fixture tree unchanged | real Claude Code, fixture Gateway |
| `mutation-check.txt` | 9 deliberate defects: 8 caught by the suite, 1 masked by an independent guard | test-suite strength |
| `m01-regression.txt` | `m01-acceptance.ps1 -SurfaceOnly -LlmSelfTest` on this branch's tree: M01-09, probe 53→4 and 49/49 `Unknown tool`, locked surface 4 tools, ordinary session 0 NotebookLM tools, M01-10 harness self-test PASS | M01 regression (NotebookLM not logged in) |

Paths are replaced with `<repo>`, `<tmp>` and `<scratch>`. No credentials, cookies, source text of real
documents or raw transcripts are included; the only document text in the Claude results is the repo's own
fake fixture.
