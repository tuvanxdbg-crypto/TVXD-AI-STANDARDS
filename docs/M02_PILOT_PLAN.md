# M02 — Bounded live pilot plan (preparation only)

Status: **STAGE A DONE AND REVIEWED; STAGE B PLAN UNDER REVIEW, NOT AUTHORIZED.**
- Stage A ran on the owner's machine (§6a).
- Its open finding (non-unique clause IDs) was fixed as F11, re-run on the real files, and passed GPT_REVIEW_V1 at
  `5f6f254`.
- The out-of-scope citation fix F12 passed code review at `8ac4e6b`.
- The stage B plan (§6b) awaits review of the P10 criteria. Stage B, including B0, runs only after that review
  **and** the owner's direct approval of the exact plan.

Executed so far, all on the owner's machine, non-elevated:
- Preparation, metadata only: ACL/token checks on the Nextcloud folder and on `C:\Vanban_XDCB` (§1), and
  `Get-Item`/`Get-FileHash` on the three owner-named files (§2). The offline checks of the draft INDEX
  (`load_index`, `version_check`, `applicability()`) read no source.
- **Stage A, 2026-10-06, completed and reviewed.**
  - It was approved directly by the owner and ran after a preflight PASS.
  - Through the Gateway's read-only local adapter it read the content of exactly the three owner-authorized files,
    and nothing else.
  - It ran discover, P1–P4 and P9, with preflight PASS before and after and the file hashes unchanged. Results:
    §6a and the review at `fb14c65`.
  - Its finding (non-unique clause IDs) was fixed as F11 and re-run on the same three files. That review PASSed at
    `5f6f254`.

Not executed: any stage B step, including B0. No NotebookLM call, no `notebooklm.mode: mcp_stdio`, no NotebookLM
login, upload, source or notebook change. No merge, no M03, no AutoCAD, no change to the M01 pin or permissions.

Every `<OWNER_INPUT: ...>` below is a placeholder that only the owner can fill. Claude does not choose documents,
work codes, reviewers or mappings.

Templates: [`m02-pilot/INDEX.pilot.template.yaml`](m02-pilot/INDEX.pilot.template.yaml) and
[`m02-pilot/gateway.pilot.template.json`](m02-pilot/gateway.pilot.template.json). Both fail closed until filled:
the INDEX template fails schema validation (`INDEX_INVALID`), and the config template points at placeholder paths,
so every lookup returns `INDEX_INVALID` and `standards_status` reports `ERROR`. The config keeps
`notebooklm.mode: disabled`. Filled stage-A files: [`m02-pilot/INDEX.pilot.draft.yaml`](m02-pilot/INDEX.pilot.draft.yaml)
and [`m02-pilot/gateway.pilot.stage-a.json`](m02-pilot/gateway.pilot.stage-a.json) (section 6a).

## 1. Source location and read-only proof

| Item | Value |
|---|---|
| Gateway `source_root` (dedicated read-only pilot folder; copies of Nextcloud `Thu-vien-chung/Vanban_XDCB` files) | `C:\Vanban_XDCB` (owner input, 2026-10-06) |
| Windows account that runs Claude Code / the Gateway | The owner's account on machine `ducdq`, non-elevated (the account checked in the second check below) |
| Nextcloud client sync state for that folder | Not applicable: `C:\Vanban_XDCB` is outside the sync root. Instead the owner confirmed (2026-10-06) that each copy equals its Nextcloud original (§2) |

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
- `source_root` for the pilot: `C:\Vanban_XDCB`. The owner named 3 pilot documents (§2).

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
match the Nextcloud original (`Thu-vien-chung/Vanban_XDCB`). The owner confirmed that match on 2026-10-06. This is
owner provenance only: Claude did not hash the Nextcloud originals, and the copies are not a synchronized mirror.

Effective dates (owner asked Claude to look them up, 2026-10-06; owner-confirmed the same day). Claude found them
by web search; the official sites were not reachable from the Claude sandbox. The GPT reviewer then checked the
official listings (GPT_REVIEW_V1 at `a4b630b`):

| Document | effective_from | Basis (official listing, per the reviewer) |
|---|---|---|
| Luật Xây dựng 135/2025/QH15 | 2026-07-01 | Government legal-document portal: in force 2026-07-01 ([vanban.chinhphu.vn](https://vanban.chinhphu.vn/?classid=1&docid=216514&orggroupid=1&pageid=27160)). Some provisions apply earlier ([xaydungchinhsach.chinhphu.vn](https://xaydungchinhsach.chinhphu.vn/noi-dung-co-ban-cua-luat-xay-dung-135-2025-qh15-119260121111210485.htm)) |
| TCVN 5575:2024 | 2024-12-24 | VSQI: Active, replaces TCVN 5575:2012, announced by QĐ 3366/QĐ-BKHCN of 2024-12-24 ([tieuchuan.vsqi.gov.vn](https://tieuchuan.vsqi.gov.vn/tieuchuan/view?sohieu=TCVN+5575%3A2024)) |
| TCVN 8794:2011 | 2011-08-23 | VSQI: Active, announced by QĐ 2585/QĐ-BKHCN of 2011-08-23 ([tieuchuan.vsqi.gov.vn](https://tieuchuan.vsqi.gov.vn/tieuchuan/view?sohieu=TCVN+8794%3A2011)) |

Limits of this metadata:
- It is a catalogue/metadata check. It does not authenticate the content of the three DOCX copies and is no legal
  or design certification.
- A TCVN announcement date does not by itself make the standard mandatory for every project. Applicability comes
  only from the owner-reviewed INDEX metadata plus the request context.
- The INDEX holds one effective date per version, so the law's earlier-effective provisions are not modelled. The
  pilot evaluates 2026-10-06 only; the INDEX is not used to answer questions dated before 2026-07-01.

With these dates the draft INDEX passes schema validation, and `version_check` returns `PASS` for each version on
2026-10-06. With the owner-reviewed metadata (§4), `applicability()` on 2026-10-06 with `THIET-KE-DAN-DUNG` gives
(offline check against the draft INDEX, no source read):

| project_context.conditions | LUAT-135-2025-QH15 | TCVN-5575-2024 | TCVN-8794-2011 |
|---|---|---|---|
| none | APPLICABLE | UNKNOWN (missing COND-KET-CAU-THEP) | UNKNOWN (missing COND-TRUONG-TRUNG-HOC) |
| COND-TRUONG-TRUNG-HOC: true | APPLICABLE | UNKNOWN (missing COND-KET-CAU-THEP) | APPLICABLE |
| COND-TRUONG-TRUNG-HOC: true, COND-KET-CAU-THEP: false | APPLICABLE | NOT_APPLICABLE | APPLICABLE |

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
| assessment_date | `2026-10-06` (owner-confirmed, 2026-10-06) |
| project_context.conditions | Condition definitions owner-confirmed: `COND-KET-CAU-THEP` (TCVN 5575), `COND-TRUONG-TRUNG-HOC` (TCVN 8794). For Q-S1 only `COND-TRUONG-TRUNG-HOC: true` is confirmed. `COND-KET-CAU-THEP` is unknown, so it stays unset and TCVN 5575 stays `UNKNOWN`; Claude never fills it in as true. No stage-A case sets `COND-KET-CAU-THEP: true`: TCVN 5575 applicability is not widened just because a project has a steel structure, and building types or conditions outside this scope stay `UNKNOWN` or excluded |
| Exact/local questions (document + clause known) | None from the owner. Users usually do not remember clauses or wording, so **semantic lookup is the primary pilot case**. Exact/local cases (P1) will be drawn from clauses that stage A shows exist in the files, and the owner confirms them. |
| Semantic questions (discovery needed) | Q-S1 (owner, 2026-10-06): "Tiêu chuẩn thiết kế chiếu sáng lớp học trường trung học" (lighting design requirements for secondary-school classrooms). Stage A: with `document_id` of the TCVN 8794:2011 copy, the expected result is `CANDIDATES` (heuristic keyword match, never exact); without `document_id` it is `BACKEND_UNAVAILABLE` while NotebookLM is disabled. Stage B: semantic lookup over the whitelisted, mapped pilot sources. Whether the document has a lighting clause is unverified (contents not opened). Further questions: `<OWNER_INPUT: optional>` |

## 4. Applicability review

| Item | Value |
|---|---|
| Reviewer of effectivity/applicability (`reviewed_by`) | The owner (owner input, 2026-10-06), recorded as `owner (tuvanxdbg-crypto)` |
| Reviewed work codes and conditions per document | Owner-confirmed 2026-10-06: `THIET-KE-DAN-DUNG` for all three; `COND-KET-CAU-THEP` (TCVN 5575), `COND-TRUONG-TRUNG-HOC` (TCVN 8794), none for the law; the document IDs and the effective dates in §2. The draft INDEX now has `reviewed: true` for all three |

A document without owner-reviewed metadata stays `reviewed: false`, so every result for it is `UNKNOWN`.

## 5. NotebookLM mapping and sync proof

Notebook (owner input 2026-10-06): `8ca84143-c240-4fcb-98fe-e1f8c6cca02d`. This is the M01 test notebook
`TVXD-M01-TEST` (tests/m01/ACCEPTANCE.md). The owner wrote the domain as `notebook.google.com`; only the ID is used.
At the M01 run (2026-10-05) `notebook_get` listed 2 sources in it:
- `1b0abe72-e94a-4f0a-8f91-827ab7668321` "2025-LUAT-135-QH15-Xay-dung.docx";
- `b710e565-91f6-49f1-bea6-a6783cbca9f4` "M01-10_injection_source.md", the M01-10 prompt-injection test source.

The two TCVN sources were not in that listing. Owner input 2026-10-06: both TCVN files have now been uploaded to
this same notebook. Their source IDs and titles are read in B0; a title must match the §2 file name or the source
stays unmapped.

| Document | notebook_id | source_id | SHA-256 of the file uploaded/synced | synced_at |
|---|---|---|---|---|
| LUAT-135-2025-QH15 | `8ca84143-…cca02d` | read in B0 (re-uploaded 2026-10-06; the M01 ID `1b0abe72-…` may be obsolete) | `c72b9ba9…3339af` (owner: uploaded from the §2 file) | 2026-10-06 (owner) |
| TCVN-5575-2024 | `8ca84143-…cca02d` (owner: uploaded 2026-10-06) | read in B0 | `87b3fd22…893124` (owner: uploaded from the §2 file) | 2026-10-06 (owner) |
| TCVN-8794-2011 | `8ca84143-…cca02d` (owner: uploaded 2026-10-06) | read in B0 | `827c9676…dd688f` (owner: uploaded from the §2 file) | 2026-10-06 (owner) |

Sync identity rules:
- A mapping gets `sync.sha256` = the §2 hash only when the owner states that the source was uploaded from that
  exact file.
- Otherwise `sync` stays absent. The evidence is then `SYNC_IDENTITY_MISSING` and stays `UNKNOWN`, never
  `VERIFIED`.
- The M01 injection source and any other source in the notebook are never mapped. A response citing them is
  discarded whole: no answer, no evidence, no cache (F12; case P10).
- Owner input 2026-10-06: all three sources were uploaded from the exact `C:\Vanban_XDCB` files, the law re-uploaded
  that day. This is owner provenance; NotebookLM exposes no file hash, so `sync.sha256` records the owner's statement,
  not a hash Claude measured.
- If B0 finds two sources with the same title (e.g. the old M01 law source next to the re-upload), neither is mapped
  until the owner names the source ID to use. The Gateway never picks one.

Whitelists: `whitelist.documents` = the documents in section 2; `whitelist.notebooklm_notebooks` = only the
notebook(s) above. Mappings are read from the owner's notes and M01-approved read tools; nothing is uploaded,
synced or edited in NotebookLM by Claude.

## 6. Pilot cases and PASS/FAIL criteria

Stage A runs with `notebooklm.mode: disabled` (local only). Stage B runs only after it is approved separately, in the
M01 locked context, with `mcp_stdio` against the M01 gated server (the four read tools only).

| ID | Stage | Case | PASS when |
|---|---|---|---|
| P1 | A | Exact/local lookup of one owner-confirmed clause per document. The clauses are picked from the IDs that `discover` finds locally; keyword `CANDIDATES` never count as an exact clause | `FOUND`, that clause, route `LOCAL`, `notebooklm_calls: 0`; `VERIFIED` for the law and TCVN 8794 (with `COND-TRUONG-TRUNG-HOC: true`), `UNKNOWN` for TCVN 5575 (`COND-KET-CAU-THEP` unknown) |
| P2 | A | `standards_verify` on P1 evidence (object and `evidence_id`); then on in-memory JSON copies with a tampered clause, source hash, excerpt or version (the source is never edited) | genuine → same status as P1 with every identity check `PASS`; tampered → `FAILED` |
| P3 | A | TCVN 8794 clause without work_code / without `COND-TRUONG-TRUNG-HOC`; TCVN 5575 with `COND-KET-CAU-THEP` unknown | `UNKNOWN`, with the missing input listed |
| P4 | A | Drift simulated by changing the hash in a **temporary copy of the pilot INDEX** (the real file is never edited) | `SOURCE_DRIFT`, no `VERIFIED` |
| P5 | B | Semantic question: capture the real `notebook_query` citation shape (key names, counts, source ids only) | citations map to whitelisted source ids; unmatched shape → documented, never `VERIFIED` |
| P6 | B | Cold vs cache hit for the same semantic question | second call `cache_hit: true`, identity re-checked, no extra backend call |
| P7 | B | Revoke the notebook in the temporary pilot INDEX copy | lookup excludes it; old evidence verifies `FAILED` (MAPPING) |
| P8 | B | Timeout recovery: pilot config with a small `timeout_s` | structured `TIMEOUT`, process retired, next call starts and validates a fresh server |
| P9 | A+B | Model isolation: Claude Code locked to the pilot Gateway (`--tools= --strict-mcp-config`, `m02-pilot/gateway.pilot.stage-a.mcp.json`) | exactly the 3 Gateway tools visible; no raw NotebookLM tools; pilot files unchanged |

Any FAIL stops the pilot. The result is reported as FAIL with the case ID; nothing is patched during the live run.

Stage A also records `discover` (not a PASS/FAIL gate for the clauses themselves): extraction status, line and
section counts and section IDs per document, Q-S1 with `document_id` TCVN-8794-2011 (`CANDIDATES`, keyword heuristic)
and Q-S1 without `document_id` (`UNKNOWN`, every document excluded as `MAPPING_MISSING`, 0 NotebookLM calls).

## 6a. Stage A preflight and run (GPT_REVIEW_V1 at `a4b630b`)

These were the stage A start conditions; all held for the 2026-10-06 run (result at the end of this section). Had one not held, the run would have stopped before any content read and reported what was missing; no other source would have been chosen.

1. **Owner approval.** The owner approves stage A directly, naming the three files and SHA-256 values in §2. A
   generic "continue" is not approval of a real-source run.
2. **Token and effective access.** The run is non-elevated, as the account that runs Claude Code and the Gateway.
   `tests/m02/pilot_preflight.py` evaluates effective rights with the Windows `AccessCheck` API on the real process
   token (user and group SIDs, deny-only groups, integrity label), not by reading single ACE lines. It examines the
   parent (`C:\`), the root and the three files. PASS needs all of:
   - no write, create, modify, delete, delete-child, permission-change or ownership right on the root or the files;
   - no delete-child, `WRITE_DAC` or `WRITE_OWNER` on the parent;
   - a token that is not elevated, at most Medium integrity, and holds no ACL-bypass privilege.
   ACLs are never edited and privileges are never raised to get past a FAIL. Filtered evidence goes to
   `tests/m02/evidence/local/`.
3. **Only the three files.** For each file the preflight checks it is a regular file, has no reparse point or Cloud
   Files placeholder/offline attribute, has hard-link count 1, and has SHA-256 equal to the pilot INDEX. It runs
   right before and right after the run (`--phase before|after`). A file with several links, a reparse point or
   placeholder, a hash mismatch, or rights that cannot be determined stops the pilot. The adapter is not changed
   to get past it.
4. **Provenance.** The copies count as Nextcloud copies on the owner's statement only, not as hash-compared
   originals or a synchronized mirror. No Nextcloud placeholder is opened or hydrated. A local `SOURCE_HASH`
   proves the local copy only, never a NotebookLM sync identity.
5. **Separate pilot config.**
   - Files: [`m02-pilot/gateway.pilot.stage-a.json`](m02-pilot/gateway.pilot.stage-a.json) (`notebooklm.mode:
     disabled`, `source_root` `C:\Vanban_XDCB`) and the pilot INDEX `m02-pilot/INDEX.pilot.draft.yaml`
     (whitelist: exactly the three documents).
   - Not added to the project `.mcp.json`. P9 uses its own `m02-pilot/gateway.pilot.stage-a.mcp.json`.
   - Context: assessment_date 2026-10-06, WORK_CODE `THIET-KE-DAN-DUNG`.
   - Conditions: only `COND-TRUONG-TRUNG-HOC: true` (TCVN 8794 / Q-S1). `COND-KET-CAU-THEP` stays unset.
6. **Meaning of results.**
   - Keyword `CANDIDATES` are never reported as a verified exact clause. P1 uses only clauses that exist locally and
     that the owner confirms.
   - `VERIFIED` covers evidence identity and INDEX applicability only, never design compliance or legal validity.
   - TCVN 5575 applicability is not widened because a project has a steel structure. Building types or conditions
     outside this scope stay `UNKNOWN` or excluded.
7. **Limits and temporary data.**
   - DOCX limits stay as configured (`max_source_bytes` 20 MB, `max_docx_uncompressed_bytes` 50 MB). A file that
     exceeds them is a finding; limits are not raised.
   - P2–P4 use in-memory JSON and a temporary INDEX copy; no real file is edited.
   - P9 sees exactly the three tools and the sources do not change.
   - Raw outputs stay in the git-ignored `tests/m02/evidence/local/`.

Run order on the owner's machine (non-elevated), with `$G` = `uv run --no-project --python 3.11 --with
pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z`:

```powershell
$G python tests/m02/pilot_preflight.py --phase before                       # must be PASS
$G python tests/m02/pilot_stage_a.py discover                                # clause IDs, Q-S1 candidates
#   owner confirms one clause per document for P1
$G python tests/m02/pilot_stage_a.py run --p1 "LUAT-135-2025-QH15=<clause>" --p1 "TCVN-5575-2024=<clause>" --p1 "TCVN-8794-2011=<clause>"
$G python tests/m02/m02_surface.py surface --mcp-config docs/m02-pilot/gateway.pilot.stage-a.mcp.json   # P9
$G python tests/m02/pilot_preflight.py --phase after                        # must be PASS, same hashes
```

Each script refuses to start unless `notebooklm.mode` is `disabled`, the INDEX whitelists exactly the three
documents and every file hash equals the INDEX. Each script writes a `.summary.json` file and, where it reads
content, a `.raw.json` file:
- `.summary.json` holds IDs, statuses, codes, check results, counts, hashes and timings only. Only these files are
  copied into a committed evidence folder.
- `.raw.json` holds the full responses, including excerpts, plus SIDs and SDDL. These stay local.

The report is `M02_STAGE_A_LOCAL_REPORT` with HEAD/CODE_COMMIT, OWNER_AUTHORIZATION_REFERENCE, READ_ONLY_PROOF,
HASH_CHECKS_BEFORE_AFTER, CASE_RESULTS, SOURCE_UNCHANGED, OPEN_ISSUES and NEXT_REQUEST: REQUEST_GPT_REVIEW.

**Stage A result (2026-10-06, owner machine, non-elevated).**
- Preflight before and after: PASS. Discover: PASS. P1–P4: 16/16 PASS. P9: PASS. Source files unchanged.
- P1 clauses (owner-confirmed): law "Điều 1", TCVN 8794 "6.2.1". No TCVN 5575 clause was given, so P3 checks it on
  keyword candidates.
- Open finding: section IDs are not unique in the real documents (table-of-contents entries and numbered table rows
  parse as sections), and lookup returns the first match, which can be a table-of-contents line marked `VERIFIED`.
  Not patched during the pilot; a fix needs a code change and review.
- Evidence: [`tests/m02/evidence/windows-ducdq-2026-10-06-stage-a/`](../tests/m02/evidence/windows-ducdq-2026-10-06-stage-a/README.md).

## 6b. Stage B plan (prepared; not authorized)

NEXT_ALLOWED_STEP `OWNER_STAGE_B_INPUTS_AND_SEPARATE_PLAN_REVIEW_ONLY` (GPT_REVIEW_V1 at `5f6f254`). Nothing in this
section has been run.
- `notebooklm.mode` stays `disabled` in every committed config.
- Claude does not log in to or call NotebookLM, and does not add or change sources.
- Stage B runs only after a GPT review of this plan **and** the owner's separate, direct approval.

Config: [`m02-pilot/gateway.pilot.stage-b.json`](m02-pilot/gateway.pilot.stage-b.json). It is the stage-A config
plus the NotebookLM client settings:
- `mcp_config` = the project `.mcp.json`, i.e. the M01 gated server with the four read tools, pin and profile
  unchanged;
- `timeout_s` 60, `max_attempts` 2, `total_budget_s` 120;
- `mode: disabled`. It is switched to `mcp_stdio` only in a temporary local copy at run time, after approval, and
  never committed.

The Gateway's client refuses any tool surface other than the four M01 read tools, and Claude still sees only the
three Gateway tools (P9).

Approval: B0 is a real NotebookLM call. It runs only under the owner's direct approval of this exact plan
(GPT_REVIEW_V1 at `a9877ec`: one approval may cover B0 and B2 when it says so). Owner inputs are not that approval.

Owner approval received (Claude chat, 2026-10-07): "Tôi chấp thuận B0 theo kế hoạch tại commit 31bd239: một lần
notebook_get trên notebook 8ca84143-c240-4fcb-98fe-e1f8c6cca02d, chỉ đọc ID/tên/số lượng source. Chưa chấp thuận
B2." (B0 approved; B1/B2 not approved.)
- B0 runs in the M01 locked session, which the owner starts (`scripts\m01\m01-session.ps1`) and drives.
- Claude records only the returned source IDs, titles and count.

Steps after approval:
- **B0, mapping, read-only.** In the M01 locked session (`scripts/m01/m01-session.ps1`), one `notebook_get` on
  `8ca84143-…`. Record source IDs, titles and the source count; no content is read. Map only sources whose titles
  match the three §2 files.
- **B1, INDEX.**
  - In a temporary INDEX copy, set `notebooklm: {notebook_id, source_id, sync: {sha256, synced_at}}` per mapped
    document, following the §5 sync rules.
  - Set `whitelist.notebooklm_notebooks: [8ca84143-…]`.
  - Leave unmapped documents `null`. Commit the mapping metadata only after review.
- **B2, runs** (Gateway with the temporary `mcp_stdio` copy):
  - P5 citation shape (Q-S1 without `document_id`);
  - P6 cold lookup vs cache hit;
  - P7 notebook removed from the whitelist in a temporary copy;
  - P8 timeout recovery with a small `timeout_s` copy;
  - P9 surface;
  - **P10 (gate, F12)**: the out-of-scope boundary on live responses. The client sends only the mapped,
    whitelisted `source_ids`. Record those ids, and for each response the cited and `sources_used` ids (ids and
    counts only). Exactly one of two outcomes PASSes:
    - **P10-A `OUT_OF_SCOPE_NOT_OBSERVED`.** Every cited and `sources_used` id is in the sent `source_ids`, or
      there is no citation outside them.
      - Record that the backend kept to the requested scope, and that the live F12 branch was not triggered.
      - Out-of-scope handling then rests on the offline F12 regressions (`F12OutOfScopeCitations`).
    - **P10-B `OUT_OF_SCOPE_OBSERVED`.** A response cites an id outside the sent `source_ids`, or a citation has no
      source id. PASS requires all of:
      - the Gateway returns `ERROR CITED_SOURCE_NOT_WHITELISTED`;
      - no answer text and no evidence;
      - no cache entry (a repeat lookup queries the backend again);
      - 0 `VERIFIED`.
    - **FAIL**, which stops stage B: any other behaviour, e.g. an out-of-scope id with a `FOUND`/`VERIFIED` result,
      an answer or evidence kept, a cached result, or ids that cannot be recorded.
    - **Not allowed:** forcing P10-B by adding the M01 injection source (or any other unmapped source) to
      `source_ids`, the INDEX mapping or the whitelist. That would make it an allowed source, stop testing the
      whitelist boundary, and widen the source set beyond what the owner approved.
    - The mixed M01 notebook may be used only because the Gateway now fails closed on out-of-scope citations.
      The F12 code fix is `028535d`, and the review at `8ac4e6b` confirmed it; that review's PATCH_REQUIRED was for
      these P10 criteria only.
  - **P11**: a document whose source has no sync identity gives `SYNC_IDENTITY_MISSING` / `UNKNOWN`.
  - Preflight before and after, as in stage A.
- **B3, report.** IDs, counts, citation key names, statuses, codes, hashes and timings only. No answer text,
  excerpts, raw payloads or transcripts. NotebookLM chat history may keep the queries (M01 query exception); no
  notebook or source is changed.

Stop conditions:
- any tool surface other than the four read tools;
- `AUTH_REQUIRED` (the owner signs in with `scripts\m01\m01-login.ps1`; Claude never asks for credentials);
- a mapped source title that does not match;
- any P-case FAIL.

Rollback: delete the temporary config/INDEX copies; the committed configs are already `disabled`.

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
| 1 | Source path, Claude account, sync state, `icacls` output | RECEIVED: `source_root` `C:\Vanban_XDCB` (outside the Nextcloud sync root); ACL reading PASS when non-elevated (§1); effective access is proven again with `AccessCheck` on the real token by the §6a preflight before and after stage A; optional deny-write hardening |
| 2 | 1–3 documents: ID, title, version, format, path, status/effectivity | RECEIVED: 3 files inventoried (§2); IDs, types, status and effective dates owner-confirmed (dates web-sourced, not checked on official sites); Nextcloud-copy match owner-confirmed. Metadata in `m02-pilot/INDEX.pilot.draft.yaml` |
| 3 | WORK_CODE, assessment_date, conditions, exact + semantic questions | RECEIVED: WORK_CODE `THIET-KE-DAN-DUNG`, assessment_date 2026-10-06, conditions COND-KET-CAU-THEP / COND-TRUONG-TRUNG-HOC, Q-S1; semantic-first (exact cases drawn in stage A and confirmed by the owner) |
| 4 | Applicability reviewer and reviewed metadata | RECEIVED: reviewer is the owner; metadata owner-reviewed 2026-10-06 (`reviewed: true`) |
| 5 | NotebookLM notebook/source mapping and sync proof per file | PARTIAL: notebook `8ca84143-c240-4fcb-98fe-e1f8c6cca02d` (TVXD-M01-TEST; holds the M01 injection source too). RECEIVED (owner, 2026-10-06): all three files uploaded to this notebook from the exact §2 files (law re-uploaded, TCVN added) on 2026-10-06. Source IDs and titles are read in B0 with `notebook_get`; duplicate titles stop the mapping |
| 6 | Approval of the live scope (stages A and B) after review of this plan | Stage A: approved by the owner (OWNER_AUTHORIZATION_V1 on PR #5, and directly in the Claude chat and the executing session) and run 2026-10-06 (§6a). Stage B: needs its own review and approval |
