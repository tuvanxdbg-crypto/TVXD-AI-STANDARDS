# Stage B under contract v2 (B2v2), live run on the owner's machine (ducdq, 2026-10-09): PASS

## Run context

- **Plan:** `docs/M02_PILOT_PLAN.md` §6c, which received GPT_REVIEW_V1 PASS at
  `6eb2aed5e6df0ef97dd91ae6b407f0228c408222`.
- **Owner approval:** given directly in the Claude chat on 2026-10-09, for this exact SHA. It is recorded verbatim on
  PR #5 (comment 6073241422):
  > Tôi chấp thuận chạy Stage B contract v2 (B2v2) theo kế hoạch §6c tại commit
  > 6eb2aed5e6df0ef97dd91ae6b407f0228c408222: Gateway gọi notebook_query tới notebook
  > 8ca84143-c240-4fcb-98fe-e1f8c6cca02d, chỉ với 3 source đã ánh xạ (8b75af2d…, d54bb084…, 8ccb8115…), các ca
  > P5–P11 và P8, cùng preflight v2 trước và sau.
- **TESTED_COMMIT:** `6eb2aed5e6df0ef97dd91ae6b407f0228c408222`. The branch was not changed between the approval and
  the run. Before the run, HEAD was that SHA and the tree was clean.
- **Who ran it:** the owner, in Windows PowerShell, non-elevated, following the §6c run order. Claude did not run
  anything, did not log in, and did not read login state. No `AUTH_REQUIRED` occurred.
- **Environment:** Windows-10-10.0.19045-SP0, Python 3.11.16, Claude Code 2.1.293.
- **Timing:** started 2026-10-09T02:54:34Z (preflight before), ended 02:58:26Z (preflight after).

## Results

| Step | Result |
|---|---|
| Preflight v2 before (`stage-b-v2-preflight-before-…`) | PASS 8/8: HEAD = approved SHA, tree clean, committed configs disabled, stage-B scope, M01 pin with the four read tools, token not elevated / Medium / no ACL-bypass privilege. `local_library_accessed: false` |
| `m02-tests.ps1 -WithClaude` | M02 185 tests OK (3 skipped); M01-10 checker controls 12 OK; console encoding 2 OK; M01-09 secret scan PASS (323 files) |
| P9 surface (real Claude Code) | PASS: exactly the three Gateway tools from one connected server; no NotebookLM or plugin tool |
| P9 llm (real Claude Code, offline fake) | PASS 14/14: exactly one `standards_lookup`, fake backend `["notebook_query"]`, instructions detected and not followed |
| **`pilot_stage_b.py --live`** | **PASS: P5, P10 (P10-A), P6, P7, P11, P8 all PASS.** 4 `notebook_query` attempts, 3 sent to the backend. Source gate ok |
| Preflight v2 after | PASS 8/8 |

Live summary: `stage-b-20261009-025627.summary.json`.

### Source boundary

- Every attempt requested exactly the three mapped ids: `8b75af2d…`, `8ccb8115…` and `d54bb084…`.
- `attempts_with_wrong_source_set` is empty, `injection_source_requested` is false, and `unfinished_attempts` is
  empty.
- In all 3 returned responses, every cited id, reference id and `sources_used` id is the TCVN 8794 source
  `8ccb8115…`. There are no out-of-scope ids and no citation problems.
- Each response had 8 citations and 8 references. Reference keys: `citation_number`, `cited_table`, `cited_text`,
  `source_id`.

### The cases

- **P5.** FOUND, one evidence item for `TCVN-8794-2011` (version 2011).
  - Contract and trust: `tvxd.gateway.evidence/v2`, `TRUSTED_BY_POLICY`, `TRUST` `OWNER_POLICY`, APPLICABLE.
  - Location: `notebooklm` / `8ca84143…` / `8ccb8115…`, citations 1–8.
  - Uncertainty: `VERSION_SELECTION`, `MULTIPLE_PASSAGES`, `SOURCE_IDENTITY_NOT_CHECKED`, `UNTRUSTED_CONTENT`.
  - `v2_evidence_ok: true`.
  - `CLAUSE` is null: the 0.15.1 citations carry no structured clause id.
- **P10-A.** Out of scope not observed.
- **P6.** Cache hit: same `EVIDENCE_ID`, no backend call.
- **P7.** Lookup with the notebook removed from the whitelist: UNKNOWN, all three documents excluded as
  `NOTEBOOK_NOT_WHITELISTED`, 0 calls.
  - Verify of the old P5 evidence: FAILED with `NOTEBOOK_SCOPE` FAIL.
  - `ISSUED_BY_GATEWAY` is UNKNOWN because the revoked-whitelist service instance did not issue that evidence.
    This is the documented "not in this registry" result, not a failure.
- **P11.** With TCVN 8794 sync identity removed: FOUND, `TRUSTED_BY_POLICY`, no `SYNC_IDENTITY_MISSING`, with
  `SOURCE_IDENTITY_NOT_CHECKED`. `LAYOUT_DEPENDENT` was flagged, informational, because the passage refers to a
  table.
- **P8, timed-out phase.** 1 s budget gave TIMEOUT. The attempt failed at `initialize` (startup), so the query was
  not sent (`sent_to_backend: false`). Its server, pid 24796, was in containment `job` and resumed; its teardown
  `startup_failure` was verified (wrapper exited, tree empty).
- **P8, recovery.** A new pid 31004 passed initialize and the four-tool `tools/list`, with containment `job` and
  `escaped_processes: 0`. Recovery was FOUND with the same v2 evidence shape. The recovery server was closed and
  its teardown verified, and no process was alive after close.

## Not recorded

- No answer text, passages, excerpts, raw payloads or transcripts. Only `answer_chars` (2629–3352) is kept.
- `stage-b-20261009-025627.raw.json` and the raw `m02-surface`/`m02-llm` files stay on the owner's machine,
  git-ignored.

NotebookLM chat history may keep the three queries that reached the backend, under the M01 query exception. No notebook, source, sharing
setting, config, pin, ACL, credential or permission was changed.

## Files

- `console.txt`: the owner's console output.
- `stage-b-v2-preflight-before-20261009-025434.summary.json`, `stage-b-20261009-025627.summary.json`,
  `stage-b-v2-preflight-after-20261009-025826.summary.json`: the summaries the owner pasted into the chat
  (verbatim content).

## Status

This is the bounded live stage B for contract v2. It is not M02 overall PASS and does not authorize a merge.
