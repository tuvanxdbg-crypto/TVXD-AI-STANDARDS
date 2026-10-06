# M02 — Bounded live pilot plan (preparation only)

Status: **PREPARATION ONLY** (`M02_BOUNDED_PILOT_SOURCE_PREPARATION_ONLY`, GPT_REVIEW_V1 at `24beaac`).
Nothing in this document has been executed. No live pilot, no `notebooklm.mode: mcp_stdio`, no NotebookLM login,
upload or source change, no real-library read beyond the owner-named files listed in section 2, no merge, no M03,
no AutoCAD, no change to the M01 pin or permissions. The live run needs a GPT_REVIEW_V1 of the completed plan **and**
the owner's explicit approval of the concrete live scope.

Every `<OWNER_INPUT: ...>` below is a placeholder that only the owner can fill. Claude does not choose documents,
work codes, reviewers or mappings.

Templates: [`m02-pilot/INDEX.pilot.template.yaml`](m02-pilot/INDEX.pilot.template.yaml) and
[`m02-pilot/gateway.pilot.template.json`](m02-pilot/gateway.pilot.template.json). Both fail closed until filled:
the INDEX template fails schema validation (`INDEX_INVALID`), and the config template points at placeholder paths,
so every lookup returns `INDEX_INVALID` and `standards_status` reports `ERROR`. The config keeps
`notebooklm.mode: disabled`.

## 1. Source location and read-only proof

| Item | Value |
|---|---|
| Nextcloud local sync/mount path (Gateway `source_root`) | `<OWNER_INPUT: absolute path, e.g. D:\Nextcloud\STANDARDS>` |
| Windows account that runs Claude Code / the Gateway | `<OWNER_INPUT: DOMAIN\user>` |
| Nextcloud client sync state for that folder | `<OWNER_INPUT: "up to date" + time>` |

Read-only proof, gathered **without writing to the library**:

```powershell
# effective rights of the Claude account on the root and on each pilot file (no write/modify/delete expected)
icacls "<source_root>"
icacls "<source_root>\<pilot file>"
(Get-Acl "<source_root>").Access | Format-Table IdentityReference, FileSystemRights, AccessControlType -AutoSize
```

PASS only if the Claude account has no `W`, `M`, `F`, `D`, `WD`, `AD` (write, modify, full, delete, write data,
append/create) on the root or the pilot files. Because the account then cannot create files, it also cannot create
hard links or junctions inside the root. This matters because:
- hard links are not reparse points and the adapter cannot detect them (docs §10);
- the Windows file-symlink refusal was SKIPPED in the fixture acceptance, since the account lacks the privilege.

If write access cannot be removed, the pilot stops here (`READ_ONLY_PROOF: FAIL`).

## 2. Bounded document set (1–3 files)

Only formats the Gateway supports: `md`, `txt`, `docx`. A PDF stays `UNSUPPORTED_FORMAT`; it is not replaced by a
summary or conversion.

| # | Document ID | Title | Version | Format | Path under `source_root` | SHA-256 | Status / effective from–to |
|---|---|---|---|---|---|---|---|
| 1 | `<OWNER_INPUT>` | `<OWNER_INPUT>` | `<OWNER_INPUT>` | `<md/txt/docx>` | `<OWNER_INPUT>` | `<computed>` | `<OWNER_INPUT>` |
| 2 | (optional) | | | | | | |
| 3 | (optional) | | | | | | |

Inventory, run only on the files named above (no directory listing or bulk read of the library):

```powershell
Get-Item "<source_root>\<path>" | Select-Object FullName, Length, LastWriteTimeUtc
Get-FileHash -Algorithm SHA256 "<source_root>\<path>"
```

## 3. Request context and test questions

| Item | Value |
|---|---|
| WORK_CODE(s) | `<OWNER_INPUT>` |
| assessment_date | `<OWNER_INPUT: YYYY-MM-DD>` |
| project_context.conditions | `<OWNER_INPUT: condition id → true/false>` |
| Exact/local questions (document + clause known) | `<OWNER_INPUT: 1–3 questions with expected clause>` |
| Semantic questions (discovery needed) | `<OWNER_INPUT: 1–3 questions>` |

## 4. Applicability review

| Item | Value |
|---|---|
| Reviewer of effectivity/applicability (`reviewed_by`) | `<OWNER_INPUT: name/role>` |
| Reviewed work codes and conditions per document | `<OWNER_INPUT>` |

A document without owner-reviewed metadata stays `reviewed: false`, so every result for it is `UNKNOWN`.

## 5. NotebookLM mapping and sync proof

| Document | notebook_id | source_id | SHA-256 of the file uploaded/synced | synced_at |
|---|---|---|---|---|
| `<doc>` | `<OWNER_INPUT>` | `<OWNER_INPUT>` | `<OWNER_INPUT: must equal section 2 hash>` | `<OWNER_INPUT>` |

Whitelists: `whitelist.documents` = the documents in section 2; `whitelist.notebooklm_notebooks` = only the
notebook(s) above. Mappings are read from the owner's notes and M01-approved read tools; nothing is uploaded,
synced or edited in NotebookLM by Claude.

## 6. Pilot cases and PASS/FAIL criteria

Stage A runs with `notebooklm.mode: disabled` (local only). Stage B runs only after it is approved separately, in the
M01 locked context, with `mcp_stdio` against the M01 gated server (the four read tools only).

| ID | Stage | Case | PASS when |
|---|---|---|---|
| P1 | A | Exact/local lookup for each section-3 exact question | expected clause returned, `VERIFIED` only with reviewed applicability, `notebooklm_calls: 0` |
| P2 | A | `standards_verify` on P1 evidence; then on a tampered copy (temporary JSON edit, not the source) | genuine → `VERIFIED`; tampered → `FAILED` |
| P3 | A | Missing work_code / unreviewed metadata | `UNKNOWN` with `missing` list |
| P4 | A | Drift simulated by changing the hash in a **temporary copy of the pilot INDEX** (the real file is never edited) | `SOURCE_DRIFT`, no `VERIFIED` |
| P5 | B | Semantic question: capture the real `notebook_query` citation shape (key names, counts, source ids only) | citations map to whitelisted source ids; unmatched shape → documented, never `VERIFIED` |
| P6 | B | Cold vs cache hit for the same semantic question | second call `cache_hit: true`, identity re-checked, no extra backend call |
| P7 | B | Revoke the notebook in the temporary pilot INDEX copy | lookup excludes it; old evidence verifies `FAILED` (MAPPING) |
| P8 | B | Timeout recovery: pilot config with a small `timeout_s` | structured `TIMEOUT`, process retired, next call starts and validates a fresh server |
| P9 | A+B | Model isolation: Claude Code locked to the pilot Gateway (`--tools= --strict-mcp-config`) | exactly the 3 Gateway tools visible; no raw NotebookLM tools |

Any FAIL stops the pilot. The result is reported as FAIL with the case ID; nothing is patched during the live run.

## 7. Logs, evidence and rollback

- **May be committed to GitHub:** document IDs, versions, formats, SHA-256, notebook/source IDs, case IDs,
  statuses, error codes, counts, citation key names, timings, tool lists, environment versions.
- **Never committed:** document text, excerpts, NotebookLM answers, raw transcripts, raw `notebook_query` payloads,
  cookies, tokens, browser profiles, or anything under `~/.tvxd-notebooklm-mcp-cli` / `~/.notebooklm-mcp-cli`.
  Gateway logs already carry no query or source text.
- **Rollback:** set `notebooklm.mode` back to `disabled` (or delete the pilot config), stop the Gateway, and delete
  the temporary pilot INDEX copies. The library and NotebookLM are never modified, so nothing else needs undoing.

## 8. Security boundary and known constraints

- Exactly three Gateway tools. The Gateway is not added to the project `.mcp.json`; the M01 pin, `.mcp.json`,
  `.claude/settings.json` and `config/m01-tool-policy.yaml` are unchanged.
- NotebookLM use only through the M01 gated server (four read tools), started by the Gateway's MCP client, which
  refuses any other tool surface. Login, if needed, is done by the owner (`scripts\m01\m01-login.ps1`); Claude never
  asks for passwords, cookies or tokens.
- Constraints carried from the offline review: file-symlink refusal unverified on Windows (SKIP); hard links not
  detected (mitigated by read-only proof, section 1); PDF unsupported; `EVIDENCE_ID` is a consistency check, not a
  signature; cache and evidence registry are in memory; after a timeout the MCP server process is restarted.

## 9. Owner inputs checklist

| # | Input | Status |
|---|---|---|
| 1 | Source path, Claude account, sync state, `icacls` output | MISSING |
| 2 | 1–3 documents: ID, title, version, format, path, status/effectivity | MISSING |
| 3 | WORK_CODE, assessment_date, conditions, exact + semantic questions | MISSING |
| 4 | Applicability reviewer and reviewed metadata | MISSING |
| 5 | NotebookLM notebook/source mapping and sync proof per file | MISSING |
| 6 | Approval of the live scope (stages A and B) after review of this plan | MISSING |
