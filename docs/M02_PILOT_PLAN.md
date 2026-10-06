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
| Gateway `source_root` (dedicated read-only pilot folder; copies of Nextcloud `Thu-vien-chung/Vanban_XDCB` files) | `C:\Vanban_XDCB` (owner input, 2026-10-06) |
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

**First check, 2026-10-06 (owner-named Nextcloud folder `Thu-vien-chung/Vanban_XDCB`, local sync path under the
user profile).** Metadata only: no listing, no file opened, no write. Result:
- **READ_ONLY_PROOF: FAIL.** The account that runs Claude has inherited Full Control on the folder and both parents.
- **Unusable as `source_root`.** The Nextcloud client uses virtual files (`virtualFilesMode=wincfapi`). The sync root
  and the folder are Cloud Files reparse points and are Unpinned. The adapter refuses every reparse point by design.
  Reading a placeholder may also trigger a download.

Proposed remedy, pending the owner's decision (option A): a dedicated pilot folder **outside** the sync root. The
owner copies the 1–3 pilot files into it; these are real files, not placeholders. Its ACL gives the Claude account
read-only access, for example a deny-write ACE for that account, while the folder is managed from a different
account. Each copy's SHA-256 must equal the Nextcloud original. Supporting Cloud Files placeholders in the adapter
would be a code change and needs its own review.

**Second check, 2026-10-06: owner-chosen pilot folder `C:\Vanban_XDCB`, outside the sync root (option A).**
Metadata only: no file name printed, no file opened, no write.
- Owner is `BUILTIN\Administrators`; all ACEs are inherited.
- The Claude account, running non-elevated (Medium integrity, Administrators deny-only), gets only `RX` via
  `BUILTIN\Users`. It has no W/M/F/D/WD/AD/DC right, so it cannot create files or hard links there.
- No reparse point: neither the folder nor any entry inside it.
- Contents: 25 `.docx` files, about 30 MB, no subfolders. All files are under `max_source_bytes`.
- **READ_ONLY_PROOF: PASS, provided Claude/the Gateway runs non-elevated.** An elevated token would get Full
  Control through Administrators. Recommended hardening: an explicit deny-write ACE for the Claude account, which
  also applies when elevated.
- `ALL APPLICATION PACKAGES` has an inherited `RX,W`. It applies only to AppContainer apps, not to Claude or the
  Gateway.
- `source_root` for the pilot: `C:\Vanban_XDCB`. The 1–3 pilot documents are still to be named by the owner.

## 2. Bounded document set (1–3 files)

Only formats the Gateway supports: `md`, `txt`, `docx`. A PDF stays `UNSUPPORTED_FORMAT`; it is not replaced by a
summary or conversion.

| # | File (path under `source_root`) | Bytes | SHA-256 | Last write (UTC) | Document ID / version / status / effectivity |
|---|---|---|---|---|---|
| 1 | `2025-LUAT-135-QH15-Xay-dung.docx` | 47,416 | `c72b9ba9bcc3b743ab72afd1ab39f8ee580deaf5437ed72fd77bfae0ed3339af` | 2026-06-05T01:30:05Z | `LUAT-135-2025-QH15` (proposed) / `2025` / active (owner) / effective_from `2026-07-01` (web, see below) |
| 2 | `2024-TCVN-5575-Thiet-ke-ket-cau-thep.docx` | 14,444,867 | `87b3fd22e59b8ed1a6ebb9f7c3680a56d87af4cb58d1a34bba0d431665893124` | 2026-08-05T07:05:39Z | `TCVN-5575-2024` (proposed) / `2024` / active (owner) / effective_from `2024-12-24` (web, see below) |
| 3 | `2011-TCVN-8794-Truong-trung-hoc-yeu-cau-th.docx` | 35,242 | `827c9676fcc336ee593c341ccc62dc2029a934618a7883cf20462487c3dd688f` | 2019-06-09T08:57:34Z | `TCVN-8794-2011` (proposed) / `2011` / active (owner) / effective_from `2011-08-23` (web, see below) |

These are the owner-named files (2026-10-06). Inventory was metadata and SHA-256 only, on the owner's machine: no
content opened or parsed, no other file name printed. All three are plain files (`Archive`): no reparse point, NFC
names, ACEs inherited from the folder (the Claude account gets `RX` when non-elevated). Each copy's SHA-256 must
match the Nextcloud original (`Thu-vien-chung/Vanban_XDCB`). The owner's confirmation of that match is still
`<OWNER_INPUT>`.

Effective dates (owner asked Claude to look them up, 2026-10-06). They come from web search summaries only: the
official publication sites (`vanban.chinhphu.vn`, `tieuchuan.vsqi.gov.vn`) were not reachable from the sandbox, so
none of them is checked against the official text. The owner should confirm them before the live pilot.

| Document | effective_from | Basis found | Secondary sources |
|---|---|---|---|
| Luật Xây dựng 135/2025/QH15 | 2026-07-01 | Passed 2025-12-10; in force 2026-07-01, some provisions from 2026-01-01 (INDEX keeps one version; per-provision dates are not modelled) | xaydungchinhsach.chinhphu.vn, baomoi.com, vanban.chinhphu.vn search listing |
| TCVN 5575:2024 | 2024-12-24 | Announced by QĐ 3366/QĐ-BKHCN dated 2024-12-24; replaces TCVN 5575:2012 | caselaw.vn, luatvietnam.vn, icci.vn |
| TCVN 8794:2011 | 2011-08-23 | Issue date per secondary sites; the announcing decision number was not confirmed | thuvienphapluat.vn, caselaw.vn, hethongphapluat.com |

With these dates the draft INDEX passes schema validation, and `version_check` returns `PASS` for each version on
2026-10-06. Applicability still returns `UNKNOWN` for all three documents because they remain `reviewed: false`.

Note for stage A: file 2 is 14.4 MB, under `max_source_bytes` (20 MB). Its uncompressed size has not been checked.
The Gateway refuses a docx above `max_docx_uncompressed_bytes` (50 MB) with `EXTRACTION_FAILED`. That would be a
stage-A finding, not something to work around.

Inventory, run only on the files named above (no directory listing or bulk read of the library):

```powershell
Get-Item "<source_root>\<path>" | Select-Object FullName, Length, LastWriteTimeUtc
Get-FileHash -Algorithm SHA256 "<source_root>\<path>"
```

## 3. Request context and test questions

| Item | Value |
|---|---|
| WORK_CODE(s) | `THIET-KE-DAN-DUNG` (owner input, 2026-10-06) |
| assessment_date | `<OWNER_INPUT: YYYY-MM-DD>` |
| project_context.conditions | `<OWNER_INPUT: condition id → true/false>` |
| Exact/local questions (document + clause known) | None from the owner. Users usually do not remember clauses or wording, so **semantic lookup is the primary pilot case**. Exact/local cases (P1) will be drawn from clauses that stage A shows exist in the files, and the owner confirms them. |
| Semantic questions (discovery needed) | Q-S1 (owner, 2026-10-06): "Tiêu chuẩn thiết kế chiếu sáng lớp học trường trung học" (lighting design requirements for secondary-school classrooms). Stage A: with `document_id` of the TCVN 8794:2011 copy, the expected result is `CANDIDATES` (heuristic keyword match, never exact); without `document_id` it is `BACKEND_UNAVAILABLE` while NotebookLM is disabled. Stage B: semantic lookup over the whitelisted, mapped pilot sources. Whether the document has a lighting clause is unverified (contents not opened). Further questions: `<OWNER_INPUT: optional>` |

## 4. Applicability review

| Item | Value |
|---|---|
| Reviewer of effectivity/applicability (`reviewed_by`) | The owner (owner input, 2026-10-06), recorded as `owner (tuvanxdbg-crypto)` |
| Reviewed work codes and conditions per document | `<OWNER_INPUT>`: owner confirmation of the proposed `THIET-KE-DAN-DUNG` for all three, `COND-KET-CAU-THEP` (TCVN 5575) and `COND-TRUONG-TRUNG-HOC` (TCVN 8794), and of the web-sourced effective dates. Until then `reviewed: false` |

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
| 1 | Source path, Claude account, sync state, `icacls` output | RECEIVED: `source_root` `C:\Vanban_XDCB` (outside the Nextcloud sync root); READ_ONLY_PROOF PASS when non-elevated (§1); optional deny-write hardening |
| 2 | 1–3 documents: ID, title, version, format, path, status/effectivity | PARTIAL: 3 files inventoried (§2); owner: types LUAT/TCVN, all in force. Draft metadata in `m02-pilot/INDEX.pilot.draft.yaml`. effective_from filled from web search (§2, not checked on official sites). MISSING: owner confirmation of the dates and proposed IDs/conditions, and the Nextcloud-copy hash match |
| 3 | WORK_CODE, assessment_date, conditions, exact + semantic questions | PARTIAL: WORK_CODE `THIET-KE-DAN-DUNG`, Q-S1; semantic-first (no exact questions). MISSING: assessment_date, confirmation of proposed conditions (COND-KET-CAU-THEP, COND-TRUONG-TRUNG-HOC) |
| 4 | Applicability reviewer and reviewed metadata | PARTIAL: reviewer is the owner. MISSING: owner confirmation of the proposed metadata (`reviewed: true` is set only after that) |
| 5 | NotebookLM notebook/source mapping and sync proof per file | PARTIAL: owner says the sources already exist in NotebookLM. MISSING: notebook name/URL and source titles; IDs to be read in stage B with the M01 read tool `notebook_get`; sync proof that each source was uploaded from the same file (SHA-256 in §2) |
| 6 | Approval of the live scope (stages A and B) after review of this plan | MISSING |
