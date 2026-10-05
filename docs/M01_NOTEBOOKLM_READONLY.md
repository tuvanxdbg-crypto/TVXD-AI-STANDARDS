# M01 — NotebookLM content-read-only pilot

## Objective
Prove that Claude Code can retrieve information from the company's current NotebookLM Pro account through MCP without allowing content-management or sharing mutations.

## Acceptance tests

| ID | Test | Expected |
|---|---|---|
| M01-01 | MCP server starts | PASS |
| M01-02 | Authentication check | PASS |
| M01-03 | List notebooks | PASS |
| M01-04 | Inspect one notebook + sources | PASS |
| M01-05 | Read one source's raw/text content | PASS |
| M01-06 | Query one notebook | PASS |
| M01-07 | Record raw tool inventory; verify only approved tools are exposed | PASS |
| M01-08 | Attempt to access a disallowed mutation capability | BLOCKED / unavailable |
| M01-09 | No credentials or auth artifacts tracked by Git | PASS |
| M01-10 | Prompt-injection / data-boundary: instruction-like source text is returned as data and causes no tool execution or policy change | PASS |

## Approved tool surface
- notebook_list
- notebook_get
- source_get_content
- notebook_query

In Claude Code these appear as `mcp__gemini-notebook-mcp__<tool>`.

## Read-only boundary
M01 protects notebook/source content and sharing configuration from mutation.

The approved query tool may persist chat history in NotebookLM. This is an accepted pilot side effect and must not be confused with permission to edit notebook/source content.

## Upstream, package and version (verified 2026-10-03)

| Item | Value | How verified |
|---|---|---|
| PyPI package | `notebooklm-mcp-cli` | PyPI JSON API |
| Version | `0.15.1` (latest at verification, uploaded 2026-10-02T16:29:02Z, not yanked) | PyPI JSON API |
| Upstream repository | https://github.com/jacob-bd/gemini-notebook-mcp-cli (MIT, author Jacob Ben-David) | `project_urls` in PyPI metadata |
| Wheel | `notebooklm_mcp_cli-0.15.1-py3-none-any.whl`, sha256 `4bfd21d83b0636210d72a1678f82b7f4b8d33c90b6504718c694a6b46c14d57f` | downloaded, `sha256sum` equals PyPI digest |
| sdist | `notebooklm_mcp_cli-0.15.1.tar.gz`, sha256 `e2316440db67378847dbc3d998c4382aec116bf0aca6f9adde0324e2f50b8443` | downloaded, `sha256sum` equals PyPI digest |
| Entry points | `notebooklm-mcp = notebooklm_tools.mcp.server:main`, `nlm = notebooklm_tools.cli.main:cli_main` | `entry_points.txt` in the wheel |
| Tool gating | `notebooklm_tools/mcp/tool_groups.py`: `NOTEBOOKLM_DISABLED_GROUPS`, `NOTEBOOKLM_DISABLED_TOOLS`, `NOTEBOOKLM_ENABLED_TOOLS` (later wins) via FastMCP `local_provider.disable()` | source read |
| Raw tool count | 53 | live `tools/list` |
| Python | `>=3.11` (pilot runs 3.11) | `Requires-Python` |

Not to be confused with: `notebooklm-mcp-server` and `notebooklm-cli` (same author, legacy split packages replaced by `notebooklm-mcp-cli`) and `notebooklm-mcp` (unrelated project, last release 2025-09).

### Launcher and dependency pinning
`.mcp.json` (project scope) starts the server with:

```text
uvx --python 3.11 --exclude-newer 2026-10-03T00:00:00Z --from notebooklm-mcp-cli==0.15.1 notebooklm-mcp
```

- `==0.15.1` pins the package. The package declares loose ranges (for example `fastmcp>=2.0.0,<5.0`), so `--exclude-newer` freezes every transitive dependency to what PyPI held at the cutoff. Resolved key dependencies: `fastmcp 4.0.10`, `mcp 2.3.0`.
- `uvx` builds an isolated, cached environment for exactly this spec. Nothing is installed into a global Python or onto PATH, and an existing `uv tool install` of another version is not used because a version is requested.
- Verified with uv 0.8.17 and uv 0.12.22.

### Executable path discovery
No absolute path is committed. Claude Code resolves `uvx` from PATH (the uv installer puts `uv.exe`/`uvx.exe` on the user PATH), and `uvx` runs the `notebooklm-mcp` console script inside its own cached environment. `scripts/m01/m01-audit.ps1` records the resolved `uvx`/`claude`/`git` paths on the Windows machine. The package version actually launched is recorded by `tests/m01/m01_probe.py`, which runs `nlm --version` through the same `uvx` spec (the MCP `serverInfo.version` field reports the FastMCP version, `4.0.10`, not the package version).

## Isolation from other projects
Everything is scoped to this repository or to a dedicated state directory:

| What | Where | Effect on other projects |
|---|---|---|
| MCP server definition | `.mcp.json` (project scope), loaded by the locked session through `--mcp-config` | Only this repo. Ordinary sessions in this repo reject it after `m01_lock.py setup-local`. |
| Ordinary-session opt-out | `disabledMcpjsonServers` in `.claude/settings.local.json` (git-ignored, written by `m01_lock.py setup-local`) | Only this repo, only this machine. |
| Tool permissions | `.claude/settings.json` (project scope) | This repo only. |
| Package + dependencies | `uvx` cached environment for the pinned spec | None. No global install. |
| Login state, browser profile | `%USERPROFILE%\.tvxd-notebooklm-mcp-cli` (`NOTEBOOKLM_MCP_CLI_PATH`), profile `tvxd-m01` (`NLM_PROFILE`) | Separate from the default `~\.notebooklm-mcp-cli` used by other setups. Protected-storage key name includes this directory's installation id and the profile. |

Do not use `nlm setup`, `claude mcp add --scope user` or `uv tool install` for M01: they write user-level configuration that every project sees.

The locked session uses `--strict-mcp-config`, so user-scope, local-scope, plugin and connector MCP servers do not load there. Ordinary sessions still load them: a NotebookLM server configured at user or local scope under any name would be reachable from an ordinary session. `m01_lock.py surface --mode project` fails if any NotebookLM/Gemini server or tool is visible in an ordinary session, and `m01-audit.ps1` lists such servers by name.

## M01 operating path (hard boundary)
NotebookLM is used from Claude Code only through `scripts/m01/m01-session.ps1`:

1. Preflight, fail closed: `tests/m01/m01_lock.py surface --mode locked` starts Claude Code with the locked arguments in print mode, reads the `system/init` event and requires that the model sees exactly the four approved tools and nothing else, from `gemini-notebook-mcp` alone.
2. Launch: `claude --permission-mode dontAsk --tools= --allowedTools <4 tools> --mcp-config .mcp.json --strict-mcp-config`.
   - `--tools=` removes every built-in tool (Bash, PowerShell, Read, Grep, Glob, Write, Edit, WebFetch, ...). It is written as one non-empty argument because Windows PowerShell 5.1 drops empty `""` arguments to native programs.
   - `dontAsk` refuses anything outside the allow list without prompting.
   - `--strict-mcp-config` loads only the pinned, gated server.

In that session Claude cannot run commands, read or write files, fetch URLs or reach any other MCP server. This is the only place the M01 read-only guarantee is claimed.

Ordinary sessions are not NotebookLM sessions. `m01_lock.py setup-local` makes them reject the project server, and `surface --mode project` verifies that no NotebookLM/Gemini tool is visible in them. Their `nlm`/login-state deny rules are best effort only (see V-03).

## Tool exposure layers inside the locked session
1. **Server gating** (`.mcp.json` env): all 16 groups from `tool_groups.py` disabled, the four tools re-enabled. Hidden tools are absent from `tools/list`, and calling one returns `Unknown tool`. Upstream docs list only 14 groups (`aliases` and `usage` are missing there); the config follows the code.
2. **Claude Code permissions** (`.claude/settings.json`): `allow` for the four tools; `deny` for the other 49 tool names (a whole-tool deny removes the tool from Claude's context and wins over any allow), for the `nlm` CLI through Bash/PowerShell, and for reading or editing the login state directories.
3. **Locked launch flags**: no built-in tools, no other MCP source, `dontAsk`.

Each of layers 1 and 2 alone produced the four-tool surface in the sandbox, and the locked flags give a total model tool list of exactly four (see `tests/m01/evidence/sandbox-linux-2026-10-03/` and `sandbox-linux-2026-10-05/`).

See:
- `config/m01-tool-policy.yaml`
- `tests/m01/ACCEPTANCE.md`

## Owner runbook (Windows machine that runs Claude Code)

Prerequisites: Claude Code, Git, and uv. If `uvx` is missing, install uv with the official installer, then reopen PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

From the repo root, on the M01 branch:

1. Audit (no tracked-file or NotebookLM changes; `git fetch` updates remote-tracking refs): `powershell -ExecutionPolicy Bypass -File scripts\m01\m01-audit.ps1`
2. Opt ordinary sessions out of NotebookLM (once per machine): `uv run --no-project --python 3.11 tests/m01/m01_lock.py setup-local`. If `claude` asks whether to use the project server `gemini-notebook-mcp` in an ordinary session, answer No.
3. Surface tests, no NotebookLM login needed: `powershell -ExecutionPolicy Bypass -File scripts\m01\m01-acceptance.ps1 -SurfaceOnly`. This covers M01-09, the server view (M01-01/07/08) and the Claude Code view: locked session exactly four tools, ordinary session none.
4. **Owner only — login/MFA:** `powershell -ExecutionPolicy Bypass -File scripts\m01\m01-login.ps1`. Sign in in the browser window it opens. Never paste passwords, cookies or tokens anywhere.
5. **Owner only — test data:** in the NotebookLM web UI create a notebook `TVXD-M01-TEST` with (a) one non-confidential document for M01-04/05/06 and (b) a pasted-text source whose content is `tests/m01/fixtures/M01-10_injection_source.md`. This is a manual UI action by the owner, outside Claude's read-only tool surface.
6. Full tests: `powershell -ExecutionPolicy Bypass -File scripts\m01\m01-acceptance.ps1 -NotebookId <id> -SourceId <id> -InjectionSourceId <id>`. Running it without `-NotebookId` prints the notebook IDs on screen only.
7. Review `tests\m01\evidence\local\` (git-ignored), transcribe non-secret results into `tests/m01/ACCEPTANCE.md`, run `tests/m01/check_no_secrets.py`, commit, push, request review.
8. Day-to-day NotebookLM retrieval: `powershell -ExecutionPolicy Bypass -File scripts\m01\m01-session.ps1` only.

## Verification findings

| ID | Finding | Handling |
|---|---|---|
| V-01 | 0.15.1 creates its state directory with `mkdir` without `parents=True`; a nested `NOTEBOOKLM_MCP_CLI_PATH` makes the server crash at start (observed through Claude Code's MCP log). | State dir is a direct child of `%USERPROFILE%`; the scripts also create it up front. |
| V-02 | `serverInfo.version` is FastMCP's version (`4.0.10`), not the package's. | Package version recorded via `nlm --version` with the same launcher spec. |
| V-03 | The package also installs the `nlm` CLI, which has full mutation capability and is not covered by MCP gating. | Hard boundary: the locked session has no shell or file tools at all. Ordinary sessions: Bash/PowerShell deny rules, best effort only (Claude Code documents that such rules do not match a program invoked by path or inside `sh -c`); in default mode those commands still prompt, and the owner must refuse any NotebookLM CLI command. |
| V-04 | Upstream docs list 14 tool groups; the code has 16. | All 16 disabled; M01-07 fails on any drift. |
| V-05 | Tool errors come back as JSON `{"status": "error"}` with `isError=false`. | The probe parses the payload. |
| V-06 | Loose dependency ranges. | `--exclude-newer` cutoff. |
| V-07 | Very fast release cadence (142 releases; 0.12.0 → 0.15.1 in eight days). | Any version bump requires re-running M01-01/07/08/10 and a new review. |
| V-08 | `claude -p` (Claude Code 2.1.289) loads project `.mcp.json` servers with no approval prompt, even in a never-approved checkout: an ordinary print-mode session saw 46 tools including the four NotebookLM tools. | `setup-local` adds the server to `disabledMcpjsonServers` (then `claude mcp get` reports it Rejected and ordinary sessions see 0 NotebookLM tools); the locked session loads it through `--mcp-config`, which that setting does not affect. Both checked by `m01_lock.py surface`. |
| V-09 | Windows PowerShell 5.1 drops empty-string arguments to native programs, so `--tools ""` would silently vanish. | The locked path uses `--tools=`. |
| V-10 | The M01-10 checker allowed Read/Glob/Grep/TodoWrite (GPT review R03-F02). | Now only `source_get_content`, plus `ToolSearch` solely to load that tool; anything else fails. |

## Exit criteria
M01 is complete only when all tests are PASS/BLOCKED as expected on the Windows Claude Code machine and the PR contains evidence of the actual tool surface.

M01 does not authorize:
- standards applicability decisions;
- legal-validity conclusions;
- CAD audit;
- CAD write operations;
- M02 Gateway development.

## Dependency risk
The current community MCP relies on non-public NotebookLM interfaces. Treat it as a pilot dependency. M02's Gateway must isolate Claude from this backend so it can later be replaced without changing Claude's public tool contract.
