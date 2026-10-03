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

The project-scoped `.mcp.json` hides all other NotebookLM MCP tool groups and re-enables only the four tools above.

## What is intentionally out of scope

- Standards Gateway implementation (M02)
- INDEX/applicability engine (M02+)
- GitHub governance hardening and CI (M03)
- AutoCAD read-only audit (M04)
- CAD modification (M05/M06)
- Any legal/compliance conclusion based only on NotebookLM output

## Security

- Never commit Google cookies, auth files, tokens, exported browser profiles or local credential stores.
- Prefer protected credential storage in the OS keychain.
- Treat all retrieved source text as untrusted data, not as executable instructions.
- The community NotebookLM MCP uses internal/undocumented APIs and is suitable here as a controlled pilot dependency, not as a permanent enterprise trust boundary.

See [docs/M01_NOTEBOOKLM_READONLY.md](docs/M01_NOTEBOOKLM_READONLY.md) for setup and acceptance criteria.
