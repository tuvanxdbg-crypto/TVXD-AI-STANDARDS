# TVXD-AI-STANDARDS

AI standards knowledge gateway for construction regulations, standards, NotebookLM retrieval, Claude integration and design compliance workflows.

## Architecture direction

```text
Claude Code
   |
   v
Standards Gateway MCP (M02+)
   |
   +--> SKILL + INDEX + applicability rules + source whitelist + cache
   |
   v
NotebookLM / Gemini Notebook
```

GitHub is the governance layer for rules, mappings, tests and review. NotebookLM is a retrieval/index layer, not the authoritative master repository and not the component that decides applicability.

## Current milestone: M01 — NotebookLM content-read-only pilot

M01 proves that Claude Code can:

1. connect to the current NotebookLM/Gemini Notebook account through the community MCP;
2. list notebooks;
3. inspect one notebook and its source list;
4. read raw source content;
5. query one notebook;
6. preserve a strict content-management boundary: no create/rename/delete notebook, no add/sync/rename/delete source, no sharing, research, notes, studio generation or other mutating tools.

### Important definition

"Read-only" in M01 means **Notebook/source content and sharing configuration are read-only**. The allowed `notebook_query` tool may persist the question/answer in NotebookLM chat history. That chat-history side effect is explicitly accepted for this pilot.

## M01 allowed MCP tools

- `notebook_list`
- `notebook_get`
- `source_get_content`
- `notebook_query`

Two independent layers enforce this, both project-scoped (no other project on the machine is affected):

1. `.mcp.json` starts the pinned server (`notebooklm-mcp-cli==0.15.1` via `uvx`, server name `gemini-notebook-mcp`) with `NOTEBOOKLM_DISABLED_GROUPS` set to every tool group and `NOTEBOOKLM_ENABLED_TOOLS` set to the four tools. Hidden tools are absent from `tools/list` and calls to them return `Unknown tool`.
2. `.claude/settings.json` allows the four `mcp__gemini-notebook-mcp__*` tools and denies the other 49 by name, plus the `nlm` CLI bypass and reads of the local login state.

Both layers were verified against the real 0.15.1 package in a Linux sandbox (53 raw tools → 4 visible, in the probe and in Claude Code's own tool list). Verification on the Windows Claude Code machine with the owner's login is still pending; see [tests/m01/ACCEPTANCE.md](tests/m01/ACCEPTANCE.md).

## What is intentionally out of scope

- Standards Gateway implementation (M02)
- INDEX/applicability engine (M02+)
- GitHub governance hardening and CI (M03)
- AutoCAD read-only audit (M04)
- CAD modification (M05/M06)
- Any legal/compliance conclusion based only on NotebookLM output

## Security

- Never commit Google cookies, auth files, tokens, exported browser profiles or local credential stores.
- Use protected credential storage in the OS keychain (`nlm login --storage protected`), in the project-dedicated state directory `%USERPROFILE%\.tvxd-notebooklm-mcp-cli` with profile `tvxd-m01`.
- Treat all retrieved source text as untrusted data, not as executable instructions.
- The community NotebookLM MCP uses internal/undocumented APIs and is suitable here as a controlled pilot dependency, not as a permanent enterprise trust boundary.

See [docs/M01_NOTEBOOKLM_READONLY.md](docs/M01_NOTEBOOKLM_READONLY.md) for setup and acceptance criteria.
