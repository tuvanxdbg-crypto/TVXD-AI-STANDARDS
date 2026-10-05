# Windows surface acceptance evidence (owner machine "ducdq", 2026-10-05)

Step: OWNER_WINDOWS_SURFACE_ACCEPTANCE, authorized by GPT_REVIEW_V1 at `20bac56`.

- Ran on the owner's machine in `C:\Users\<user>.tvxdbg\TVXD-AI-STANDARDS`, branch
  `claude/m01-local-verification-tt0fgc` at `20bac5686fc32eb261c5a298bc13ec71d5e27019`,
  clean working tree before and after.
- Executed by a Claude Code Remote Control session on that machine, following the runbook order:
  `m01-audit.ps1`, `m01_lock.py setup-local`, `m01-acceptance.ps1 -SurfaceOnly` (all exit 0).
- No Google/NotebookLM login, project MCP server not approved, nothing committed from that machine.
- Files are copies of `tests\m01\evidence\local\` from that run. The Windows user name is replaced
  with `<user>`; JSON was re-serialised with the same values. The four files were scanned for
  cookie/token/password/secret/bearer/SAPISID/SID=/api-key patterns; the only hit is the tool name
  `save_auth_tokens` in the raw inventory.
- The audit ran before `setup-local` (runbook order), so it still shows `gemini-notebook-mcp` as
  "Pending approval". The ordinary-session check ran after `setup-local` and found no NotebookLM
  server or tool.

| File | Source |
|---|---|
| `m01-audit.txt` | `m01-audit-20261005-120738.txt` |
| `probe-surface.json` | `m01-probe-surface-20261005-120905.json` |
| `claude-code-surface-locked.json` | `m01-tool-surface-locked-20261005-120914.json` |
| `claude-code-surface-project.json` | `m01-tool-surface-project-20261005-120922.json` |
