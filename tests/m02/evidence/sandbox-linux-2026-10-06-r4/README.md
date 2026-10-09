# M02 offline validation evidence, review round 4 (Linux sandbox, 2026-10-06)

OFFLINE fixture validation only, for the F10 fix (bounded stdin writes) reviewed by GPT_REVIEW_V1 at `746fac2`
(DECISION: PASS for the F10 code fix; M02 overall still IN_PROGRESS). No real library, no NotebookLM call.
Code commit: `746fac2d823ea4d044d69748f7438401f73c5cd3`. Environment: Linux cloud container, Python 3.11.15 (uv),
PyYAML 6.0.2, uv 0.8.17, pwsh 7.6.2, Claude Code 2.1.290 (the CLI updated itself from 2.1.289 between round 3 and
round 4; each JSON records the version that actually ran). Earlier rounds: `../sandbox-linux-2026-10-05/`,
`-r2/`, `-r3/`. The reviewer's independent Windows run (PowerShell 5.1, Python 3.11.16) is recorded in its review,
not here.

| File | What | Kind |
|---|---|---|
| `unit-tests.txt` | 105 M02 unit/contract tests (100 earlier + 5 F10), verbose list, all OK | mock (fixture library, fake NotebookLM, offline MCP stand-in incl. stalled stdin) |
| `revert-check.txt` | F1–F7, F8–F9 and F10 revert results; on the previous client the four stalled-stdin tests hang (caught) | test-suite strength |
| `m02-tests-ps1.txt` | `scripts/m02/m02-tests.ps1` under pwsh on a fresh worktree: M02 105/105, M01 checker/console, M01-09 (126 files) PASS | runner, Linux |
| `claude-code-gateway-surface.json` | Claude Code locked to the fixture Gateway sees exactly the 3 Gateway tools | real Claude Code, fixture Gateway |
| `claude-code-gateway-llm.json` | injection fixture via `standards_lookup`: canary reported, embedded instructions detected and not followed | real Claude Code, fixture Gateway |
| `m01-regression.txt` | `m01-acceptance.ps1 -SurfaceOnly -LlmSelfTest` on a fresh worktree of the code commit: all PASS | M01 regression (NotebookLM not logged in) |

Not run in this round (M02, code `746fac2`): live NotebookLM, real library, authenticated M01 acceptance, Windows
junction controls. (The historical authenticated M01 acceptance passed on the owner machine and M01 is CLOSED; it
was not re-run for the M02 code.)
Paths are replaced with `<repo>`, `<tmp>` and `<scratch>`; no credentials, real document text or raw transcripts.
