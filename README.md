# TVXD-AI-STANDARDS

AI standards knowledge gateway for construction regulations, standards, NotebookLM retrieval, Claude integration and design compliance workflows.

## Architecture direction

The current architecture authority is the approved roadmap, [Issue #2](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/issues/2) (hybrid local + index + NotebookLM fallback). Summary for M02 onward:

```text
Claude Code
   |
   v
Standards Gateway MCP (M02+)
   |
   +--> CACHE -> INDEX (WORK_CODE, applicability, source/version whitelist)
   |
   +--> exact source/clause known  --> LOCAL SOURCE READ (read-only sync/mount of Nextcloud)
   +--> semantic discovery needed  --> NotebookLM semantic search
   |
   v
structured grounded evidence (local reread only for ambiguity, layout-dependent
content, uncertain mapping or suspected sync/version drift)
```

Nextcloud is the authoritative document store. NotebookLM is a semantic retrieval layer, not the master repository and not the component that decides applicability. GitHub is the governance layer for rules, mappings, indexes, hashes, tests and review.

M01 covers only one leg of this design, the NotebookLM read path, as a pilot. Nothing in M01 implements the Gateway, the INDEX or local retrieval.

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

### M01 operating path

NotebookLM is used from Claude Code **only** through `scripts/m01/m01-session.ps1`. It first checks (`tests/m01/m01_lock.py surface --mode locked`, fail closed) that the model would see exactly the four approved tools and nothing else, then starts Claude Code with `--permission-mode dontAsk --tools= --allowedTools <4 tools> --mcp-config .mcp.json --strict-mcp-config`. In that session Claude has no shell, file, web or other MCP tools.

Ordinary Claude Code sessions in this repo do not load NotebookLM. The owner runs `tests/m01/m01_lock.py setup-local` once, which adds `gemini-notebook-mcp` to `disabledMcpjsonServers` in the git-ignored `.claude/settings.local.json`. This is needed because `claude -p` loads project `.mcp.json` servers without an approval prompt. `m01_lock.py surface --mode project` verifies that no NotebookLM/Gemini server or tool is visible in an ordinary session.

The hard read-only guarantee covers the locked session only. In ordinary sessions the `.claude/settings.json` deny rules for the `nlm` CLI and the login-state directories are best effort: Claude Code documents that such rules do not match a program called by path or wrapped in another shell.

Layers inside the locked session, all project-scoped (no other project on the machine is affected):

1. `.mcp.json` starts the pinned server (`notebooklm-mcp-cli==0.15.1` via `uvx`, server name `gemini-notebook-mcp`) with `NOTEBOOKLM_DISABLED_GROUPS` set to every tool group and `NOTEBOOKLM_ENABLED_TOOLS` set to the four tools. Hidden tools are absent from `tools/list` and calls to them return `Unknown tool`.
2. `.claude/settings.json` allows the four `mcp__gemini-notebook-mcp__*` tools and denies the other 49 by name.
3. The locked launch flags remove every built-in tool and every other MCP source.

Each layer was verified against the real 0.15.1 package in a Linux sandbox and on the owner's Windows machine. The latest Windows full authenticated acceptance passed all M01-01..10 tests at code-tested commit `040bede` on 2026-10-05; its evidence was recorded at `08f0301`. An earlier full run at `8213f80` failed on test-harness issues that the R05 patch fixed; it is kept as history. See [tests/m01/ACCEPTANCE.md](tests/m01/ACCEPTANCE.md).

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
