# M02 — Standards Gateway (offline-first)

Status: **IN_PROGRESS / OFFLINE_VALIDATED candidate**. The Gateway core, adapters, schemas and
tests are built and run against **fixture data only**. This is not an M02 overall PASS. Real
library pilot, live NotebookLM calls from the Gateway, merge, M03 and AutoCAD are **not
authorized** in this round.

Authority: [Issue #4](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/issues/4) (specification and
execution request, kept verbatim in the appendix) and the roadmap
[Issue #2](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/issues/2). Baseline: `main` at
`70c5e08e289505909b3619becc3ed03fc49f599b` (M01 closed). M01 security limits stay in force unchanged.

## 1. What was built

| Part | Where | Notes |
|---|---|---|
| MCP stdio server, exactly 3 public tools | `gateway/server.py` | `standards_lookup`, `standards_verify`, `standards_status`. stdout = JSON-RPC only; JSON-line logs on stderr. |
| Core pipeline | `gateway/service.py` | validate → INDEX → document → whitelist → version → applicability → cache → LOCAL or NOTEBOOKLM → identity checks → evidence |
| Versioned schemas | `gateway/schemas/*.v1.json`, validator `gateway/schema.py` | requests, responses, evidence, INDEX, config; every response is self-checked against its schema before it is returned |
| INDEX loader | `gateway/index.py` | YAML (safe loader, timestamps kept as text) + schema + semantic checks; version selection; applicability |
| Local adapter (read-only) | `gateway/adapters/local.py`, `gateway/extract.py`, `gateway/clauses.py`, `gateway/paths.py` | path confinement, md/txt/docx, numeric and Vietnamese article clause schemes |
| NotebookLM adapter | `gateway/adapters/notebooklm.py` | backend interface over the four M01 read tools; MCP stdio client that fails closed; **disabled** in this round |
| Cache | `gateway/cache.py` | in-memory, identity-bound key, re-validated hits |
| Retry/timeout | `gateway/retry.py` | bounded attempts and total budget; only transient errors retried |
| Logs | `gateway/logs.py` | whitelisted keys only; no query, context or source text |
| Fixtures | `tests/m02/fixtures/` | fake library, `INDEX.yaml`, `INDEX.md`, config, fixture MCP config |
| Tests | `tests/m02/test_gateway_*.py`, `tests/m02/m02_surface.py` | 121 offline unit/contract tests (44 regressions for the review findings F1–F12 in `test_gateway_regressions.py`; 4 Windows-only junction/reparse controls in `test_gateway_windows.py`, skipped elsewhere) + real Claude Code checks on the fixture Gateway |
| Windows runner | `scripts/m02/m02-tests.ps1` | fail-fast; `-WithClaude` adds the real Claude Code checks |

## 2. Implementation decisions

1. **Python 3.11, standard library + one pinned dependency: PyYAML 6.0.2** (MIT), resolved with
   `--exclude-newer 2026-10-03T00:00:00Z` like M01. PyPI SHA-256: win_amd64 cp311 wheel
   `e10ce637b18caea04431ce14fabcf5c64a1c61ec9c56b071a4b7ca131ca52d44`; manylinux cp311 wheel
   `3ad2a3decf9aaba3d29c8f537ac4b243e36bef957511b4766cb0057d32b0be85`; sdist
   `d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e`. Only `yaml.SafeLoader` (subclass) is used.
   No MCP SDK: the stdio server and client are small and auditable, like the M01 harness.
2. **JSON Schema files are the contract** and are enforced: a minimal validator implements exactly the keywords
   the schemas use and refuses schema files that use anything else, so a schema cannot claim an unchecked rule.
3. **The Gateway never generates answers.** `ANSWER.text` is null for local evidence; for the NotebookLM route it
   carries NotebookLM's answer, labelled `origin: NOTEBOOKLM`. Claude evaluates `EVIDENCE.text`.
4. **Evidence `STATUS`:** `VERIFIED` only when source identity (whitelist, unambiguous version, file hash equal to
   INDEX, or NotebookLM mapping with a sync identity equal to the INDEX hash) **and** INDEX applicability for the
   given `work_code`/`assessment_date`/conditions all pass, and no blocking uncertainty remains. `NOT_APPLICABLE`
   when INDEX says it does not apply. Otherwise `UNKNOWN`. `VERIFIED` is never a legal-validity or design-compliance
   conclusion (stated in every response's `disclaimer`). Blocking uncertainty codes: `APPLICABILITY_UNKNOWN`,
   `MAPPING_MISSING`, `SYNC_IDENTITY_MISSING`, `SOURCE_DRIFT`, `PASSAGE_NOT_FOUND`, `NO_PASSAGE`,
   `LOCAL_REREAD_FAILED`, `VERSION_UNRESOLVED`, `LOCAL_IDENTITY_UNAVAILABLE`.
5. **Applicability comes only from owner-reviewed INDEX metadata** plus request context: missing `work_code` or
   `assessment_date`, an undefined work code, unreviewed metadata, unknown effective dates or unanswered conditions
   → `UNKNOWN` with a `missing` list. The Gateway never infers applicability from a document's existence.
6. **Routing:** `document_id`, or exactly one INDEX code named in the query (diacritic-insensitive, word-bounded),
   selects the **local** route; NotebookLM is not called (tests assert zero calls). Several codes in one query →
   `UNKNOWN` asking for `document_id`. No code → **semantic** route over whitelisted documents that have a NotebookLM
   mapping in a whitelisted notebook; everything else is listed in `excluded` with a reason.
7. **NotebookLM results:** a response that cites any source outside the queried, whitelisted, mapped source ids (or a
   citation without a source id, in `citations` or `sources_used`) is discarded as a whole (F12): no answer, no
   evidence, no cache entry, structured error `CITED_SOURCE_NOT_WHITELISTED` listing the out-of-scope ids. A citation
   is accepted directly only with a sync identity equal to the INDEX hash, the authoritative local file's current
   SHA-256 equal to the INDEX hash (an identity check only, no content reread; drift → `SOURCE_DRIFT`, unreadable →
   `LOCAL_IDENTITY_UNAVAILABLE`, both blocking) and no reread trigger. Reread triggers:
   no passage, table/figure/note wording, several passages of one document, suspected drift. A reread locates the
   passage verbatim (whitespace-normalized) in the authoritative file; if it is not found → `UNKNOWN` without text.
   Missing mapping/sync identity or drift is never `VERIFIED`.
8. **Clauses:** `numeric` scheme (TCVN/QCVN headings "2", "2.1", "2.1.3.") and `article` scheme ("Chương", "Điều N",
   khoản "N.", điểm "a)"). Keywords are matched accent-insensitively, but point letters keep `đ` distinct from `d`
   ("điểm d" and "điểm đ" are different points, in documents and in requests). Without a clause, a keyword search
   returns `CANDIDATES` marked `HEURISTIC_MATCH`, never an exact match.
9. **Cache** key = normalized request + context + resolved identities (document, version, INDEX file hash,
   NotebookLM mapping and sync identity) + INDEX file hash + INDEX/rules versions. Hits are re-validated against the
   current INDEX and the current authoritative files before being returned: a local-route hit re-hashes the file
   (drift evicts the entry and returns `SOURCE_DRIFT`); a semantic-route hit re-hashes every cited source (NotebookLM
   and reread evidence alike) and compares it with the identity recorded when the entry was built; any change
   evicts the entry and the query runs again, so drifted or unreadable sources come back as blocking uncertainty.
   Entries from an older INDEX are dropped when the INDEX hash changes. In-memory per process (no persistence in v1).
10. **INDEX is re-read on every request** (hash compare, re-parse on change). An invalid INDEX fails closed
    (`INDEX_INVALID` for lookups/verify, `ERROR` status).
11. **`standards_verify` trusts nothing in the evidence object.** It runs these checks against the current INDEX and
    the authoritative file:
    `EVIDENCE_ID` (the id matches the evidence content: a consistency check, not a signature),
    `DOCUMENT_WHITELISTED`, `SOURCE_ID` (`SOURCE_ID` and `DOCUMENT.title` equal INDEX), `VERSION_RESOLVED` (same rules
    as date-based selection: draft/withdrawn never eligible, overlap ambiguous, must be the version in force),
    `SOURCE_LOCATION` (kind consistent with `RETRIEVAL_PATH`, path equal to INDEX), `SOURCE_HASH` (file hash equal to
    INDEX, and every field of the evidence `SOURCE_HASH` equal to what the Gateway derives now), `EXCERPT_MATCH` (text
    and truncated/layout flags reproduce the file at the stated lines, or the NotebookLM passage is found in the
    file), `CLAUSE` (the clause that contains the excerpt in the file; a NotebookLM passage may claim none),
    `MAPPING` (notebook still in the INDEX notebook whitelist, ids and sync identity equal INDEX) and `APPLICABILITY`.
    `VERIFIED` needs every check to `PASS`, except `MAPPING`, which is `SKIPPED` for LOCAL-route evidence. Evidence
    without an excerpt is `UNKNOWN`; any `FAIL` makes the result `FAILED`. `ANSWER.text` (NotebookLM's generated
    answer) is bound into `EVIDENCE_ID` but never verified as a statement; Claude evaluates `EVIDENCE.text`.
12. **Explicit `version` in a lookup only names the file to read.** It is checked with the same rules as
    `standards_verify` (`VERSION_RESOLVED`); anything but `PASS` adds the blocking `VERSION_UNRESOLVED` uncertainty,
    so a withdrawn/draft version or an overlapping effectivity is never `VERIFIED`.

## 3. Formats and extraction limits

| Format | Support | Limits / behaviour |
|---|---|---|
| `md`, `txt` | yes | UTF-8 (BOM allowed), NFC. Table rows (`|`) and image refs flagged `LAYOUT_DEPENDENT`. Invalid UTF-8 → `EXTRACTION_FAILED`. |
| `docx` | yes (text) | `word/document.xml` paragraphs in order; tables flattened to `| a | b |`; images → `[IMAGE]` (both `LAYOUT_DEPENDENT`). Headers/footers, footnotes, comments, tracked changes not extracted. Zip: ≤ 2000 entries, ≤ 50 MB uncompressed (configurable), ratio ≤ 200; DTD/ENTITY refused. |
| `pdf`, `doc`, other | no | `UNSUPPORTED_FORMAT`; no text is guessed. |
| any | — | file ≤ `max_source_bytes` (20 MB default); excerpt ≤ `max_excerpt_chars` (4000) with `TRUNCATED`. |

## 4. Errors

`INVALID_REQUEST`, `INDEX_INVALID`, `SOURCE_NOT_ALLOWED`, `SOURCE_NOT_FOUND`, `VERSION_AMBIGUOUS`, `SOURCE_DRIFT`,
`APPLICABILITY_UNKNOWN`, `BACKEND_UNAVAILABLE`, `AUTH_REQUIRED`, `TIMEOUT` (Issue #4 minimum) plus
`UNSUPPORTED_FORMAT`, `EXTRACTION_FAILED`, `INTERNAL_ERROR`, `CLAUSE_AMBIGUOUS` (F11: an exact clause ID that
occurs more than once in the file; `details` carries `clause`, `occurrences` and up to 20 `line_starts`) and
`CITED_SOURCE_NOT_WHITELISTED` (F12: a NotebookLM response cited a source outside the queried, whitelisted sources;
`details` carries `notebook_id`, `count` and up to 20 `out_of_scope_source_ids`). Errors are structured
(`code`, `message`, `retryable`, `details`); unexpected exceptions are reported by type only.
Retries: only transient `TIMEOUT`/`BACKEND_UNAVAILABLE`, `max_attempts` (default 2) and `total_budget_s`
(default 120 s), exponential backoff. Auth, permission, version, mapping and scope errors are never retried; the
Gateway never signs in, switches backend or widens the whitelist to get past an error. Each attempt carries an
absolute deadline (never past the total budget) and a cancel flag that is set when the caller stops waiting. The
NotebookLM client honours it: an attempt that is expired or cancelled while queued for the client never sends, every
response wait uses one absolute deadline (notifications do not extend it), and an in-flight request that times out is
cancelled (`notifications/cancelled`) and its server process killed, so no backend work of a timed-out attempt
continues after the caller has received `TIMEOUT`. Writes to the server's stdin are made by a per-process writer
thread; the caller only waits for a write until its deadline, so a server that stops reading cannot hold the caller,
the client lock or the worker. Retiring a timed-out request first hands `notifications/cancelled` to the writer
best-effort, waiting at most 50 ms, and then kills the process. `_terminate` kills the process before closing any
stream (the kill also unblocks a stuck write). `close` stops gracefully: once the writer has drained it closes stdin
so the server exits on EOF, and it kills the process when the writer is stuck or the server does not exit. Neither
closes or flushes a stdin that a blocked write still holds.
`APPLICABILITY_UNKNOWN` normally appears as an evidence uncertainty (not a request error), with the missing inputs.

## 5. Security boundary

* **Public surface:** exactly three tools. Raw NotebookLM tools and mutation tools are unknown to the Gateway
  (`Unknown tool`). Claude Code is started locked to the Gateway (`--tools= --strict-mcp-config`, only
  `tests/m02/fixtures/gateway.mcp.json`) for the model-visible check.
* **NotebookLM:** config `notebooklm.mode` is `disabled` by default and in all fixtures. The MCP stdio client
  (`mode: mcp_stdio`) launches the pinned M01 gated server from the project `.mcp.json`, refuses to proceed unless
  `tools/list` is exactly the four M01 read tools, and refuses to call any other tool name. A process is used only
  after `initialize` and that surface check both succeeded; any startup error or timeout kills it, and the next call
  starts and validates a fresh process. Startup steps, calls and stdin writes are bounded by absolute deadlines
  (section 4).
  Enabling it is part of
  the live pilot and needs a new review. M01 pin, `.mcp.json`, `.claude/settings.json` and
  `config/m01-tool-policy.yaml` are unchanged.
* **Local source root:** callers never pass paths; INDEX paths must be relative, `/`-separated, NFC, without `..`,
  `:`, drive letters, UNC, reserved device names or trailing dots/spaces. Each component is `lstat`ed; symlinks and
  Windows reparse points (junctions) are refused; the resolved path must stay inside the resolved root and be a
  regular file; the opened handle must match the checked file. The adapter only opens files `rb`; tests assert the
  fixture tree is byte-identical before and after.
* **Untrusted content:** `EVIDENCE.text` and `ANSWER.text` are labelled untrusted (`untrusted_data: true`,
  `UNTRUSTED_CONTENT`), and every response carries the disclaimer. The Gateway's code never interprets source text
  as instructions.
* **Logs:** whitelisted keys only; the query appears as a 12-hex SHA-256 prefix; no context, source text, answers,
  cookies, tokens or environment.

## 6. Offline acceptance (Issue #4 §6) — evidence map

Mock = fake NotebookLM backend / fixture library. Real = real Claude Code CLI against the fixture Gateway.
No real NotebookLM call and no real library in this round.

| Issue #4 §6 item | Test(s) | Kind |
|---|---|---|
| Public tools/list exactly three; raw NotebookLM/mutation tools not exposed | `test_gateway_server.McpSurface`; `m02_surface.py surface` (+ negative control without `--tools=`: FAIL, 39 extra tools) | mock + real Claude Code |
| Exact local lookup makes 0 NotebookLM calls | `ExactLocal.test_exact_lookup_reads_local_and_never_calls_notebooklm`, `DataBoundary` | mock |
| Semantic lookup only within whitelist | `Semantic.test_only_whitelisted_mapped_sources_are_queried_and_kept`, `ServiceLevel.test_auth_error_has_no_fallback_and_no_whitelist_widening` | mock |
| Wrong/absent mapping, unknown applicability/version, drift → no verified evidence | `Semantic.*sync*`, `*drift*`, `*passage_absent*`; `Applicability.*`; `ExactLocal.test_structured_errors` (VERSION_AMBIGUOUS); `Verify.*`; `LocalAdapter.test_hash_mismatch_is_drift` | mock |
| Cache invalidation on source/INDEX/rules/mapping change; cache never bypasses checks | `Cache.*` | mock |
| Embedded instructions cause no action, file or policy change | `DataBoundary`; `m02_surface.py llm` | mock + real Claude Code |
| Source root unchanged; traversal/escape refused | `SourceRootImmutable`, `LocalAdapter.test_traversal_*`, `test_symlink_*`, `Paths`, `IndexValidation.test_*path*` | mock |
| Timeout, retry exhaustion, unavailable backend, missing input → structured | `test_gateway_resilience.*`, `ExactLocal.test_structured_errors` | mock |
| Windows Unicode and published formats work or fail structurally | `LocalAdapter.test_unicode_windows_filename`, `*docx*`, `*pdf*`, `*utf8*`, `Paths` (NFD rejected); `.gitattributes` keeps fixture bytes on Windows | mock |
| Model-visible isolation with evidence, mock vs real distinguished | `m02_surface.py` evidence records `kind` | real Claude Code |
| Review findings F1–F12 (GPT_REVIEW_V1 at `d35b574`, `eeb76bc`, `cb26095`, `fb14c65`, `a9877ec`) | `test_gateway_regressions.F1…F12*` (see sections 11–15) | mock |
| Related M01 regression and secret scan PASS | `tests/m01/test_m01_10_llm_check.py`, `test_m01_console.py`, `check_no_secrets.py`; M01 surface acceptance | regression |

Test-suite strength: 9 hand-made mutations of the Gateway (whitelist, sync identity, cache drift check,
applicability gate, citation filter, public tool list, path confinement, verify excerpt check, retry
classification): 8 make the suite fail; the remaining one (applicability gate in `decide`) is masked by a second,
independent guard (an unknown applicability always adds the blocking `APPLICABILITY_UNKNOWN` uncertainty), so the
behaviour does not change. Round 2: reverting each F1–F7 fix separately (F1 also check by check, 7 checks; F6 hit
and miss separately) makes exactly the matching regression class fail. Round 3: reverting all of F8, or F9, makes F8/F9
regression tests fail. Two F8 parts are layered guards: the queued-attempt check in `_tool` is backed by the
before-send check in `_request` (reverting both fails `test_queued_attempts_never_send_after_expiry`), and the cancel
flag fires at the same instant as the absolute deadline, so reverting it alone changes no observable behaviour.

## 7. How to run (Windows, from the repo root)

Prerequisites as in M01: Claude Code, Git, uv. Nothing is installed globally.

```powershell
# offline tests (fixture library, fake NotebookLM) + related M01 regression
powershell -ExecutionPolicy Bypass -File scripts\m02\m02-tests.ps1
# add the real Claude Code checks against the fixture Gateway (a few cents of Claude usage)
powershell -ExecutionPolicy Bypass -File scripts\m02\m02-tests.ps1 -WithClaude

# start the Gateway MCP server by hand (fixture config)
uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z `
    python -m gateway.server --config tests\m02\fixtures\gateway.fixture.json
```

A Claude Code session locked to the fixture Gateway:
`claude --permission-mode dontAsk --tools= --allowedTools mcp__tvxd-standards-gateway__standards_lookup,mcp__tvxd-standards-gateway__standards_verify,mcp__tvxd-standards-gateway__standards_status --mcp-config tests\m02\fixtures\gateway.mcp.json --strict-mcp-config`.
The Gateway is **not** added to the project `.mcp.json`, so ordinary sessions do not load it.

## 8. Assumptions

* A1. The Nextcloud library will be exposed as a read-only local sync/mount folder (Issue #2 amendment 4); the
  Gateway does not talk to Nextcloud APIs.
* A2. INDEX paths are relative to that folder and written in NFC with `/` separators.
* A3. NotebookLM `notebook_query` returns `answer` and citations with a source id and passage text. The fake
  backend uses `citations: [{"source_id", "passage"}]`; the parser also accepts `cited_text`/`text` and
  `sources_used`. The real 0.15.1 citation structure must be confirmed in the live pilot (M01 recorded only
  citation counts).
* A4. A NotebookLM source's sync identity is the SHA-256 of the exact file uploaded/synced; the owner records it
  in INDEX when syncing.
* A5. Clause recognition follows the two schemes above; documents with other layouts need a scheme extension.
* A6. All fixture metadata (effective dates, applicability, reviewers, mappings) is fake and says nothing about
  real documents.

## 9. MISSING_OWNER_INPUTS (needed before any live pilot; they do not block the offline build)

1. Path of the Nextcloud sync/mount folder on the pilot machine and confirmation it is read-only for the Claude
   user (or how write access is prevented).
2. The bounded pilot document set (document codes), with file formats, exact files and their SHA-256.
3. Which `WORK_CODE`s and project contexts the pilot covers, with their definitions.
4. Who reviews effectivity dates and applicability metadata (`reviewed_by`), and the reviewed values.
5. NotebookLM mapping for each pilot file (notebook id, source id) and the sync proof (hash of the synced file,
   sync time).
6. Whether PDF sources are in scope (needs a reviewed extraction dependency) and how scanned PDFs are handled.
7. Approval to switch `notebooklm.mode` to `mcp_stdio` for the pilot, after GPT review of this code.

## 10. Known limitations / open items

* Clause heading detection is pattern-based; a body line that starts like a heading ("2.1 ...") is taken as one.
  Real documents therefore repeat IDs (table of contents, numbered table rows). Since F11 a repeated ID fails
  closed (`CLAUSE_AMBIGUOUS`, never `VERIFIED`), so such clauses cannot be looked up exactly until the parser
  learns to skip tables of contents; this is a usability limit, not a safety gap.
* Local passage matching is exact after whitespace normalization; NotebookLM paraphrases will not match (→ `UNKNOWN`).
* Cache and evidence registry are in memory; `standards_verify` by `evidence_id` only works in the same server
  process (the evidence object can always be passed instead).
* `standards_status` `deep` re-hashes every INDEX file (fine for a pilot set, slow for a large library).
* The semantic route hashes each cited authoritative file on every lookup, including cache hits (source identity
  check, F6); fine for a pilot set, to be revisited with a persistent identity cache for a large library.
* Windows junction/reparse refusal is exercised by `tests/m02/test_gateway_windows.py` (Windows only; skipped
  elsewhere): a junction or file symlink inside a throwaway fixture root that points outside must be refused and the
  outside canary never read or returned; a normal path stays readable. File symlinks need Developer Mode, so that
  sub-check may report SKIP. Hard links are not reparse points and are not detected; the source root must stay
  read-only for the Claude user (MISSING_OWNER_INPUTS 1).

## 11. Review round 2 — GPT_REVIEW_V1 at `d35b574` (PATCH_REQUIRED)

| Finding | Fix | Regression tests (`tests/m02/test_gateway_regressions.py`) |
|---|---|---|
| F1 [P1] verify accepted modified CLAUSE, SOURCE_ID, SOURCE_HASH | verify derives every identity field from INDEX and the file: checks `EVIDENCE_ID`, `SOURCE_ID`, `SOURCE_LOCATION`, `SOURCE_HASH` claims, excerpt flags and `CLAUSE` (decision 11) | `F1VerifyBindsEvidenceFields`: 15 field tampers, each with the id unchanged and with the id recomputed; NotebookLM evidence tampers; lookup→verify never upgrades |
| F2 [P1] NO_PASSAGE evidence became VERIFIED | a missing excerpt is `UNKNOWN`; `VERIFIED` needs `PASS` everywhere (only `MAPPING` may be `SKIPPED`, for LOCAL evidence) | `F2NoExcerptIsNotVerified`: sources_used without passage, passage not found, failed local reread (unmodified lookup evidence) |
| F3 [P1] explicit version bypassed eligibility/overlap | `index.version_check()` shared by lookup and verify; non-PASS → blocking `VERSION_UNRESOLVED` (decision 12) | `F3ExplicitVersionEligibility`: withdrawn, draft, TCVN-FAKE-9999 overlap; eligible explicit versions still work |
| F4 [P1] points d) and đ) collided | `textnorm.letters()` keeps `đ`; used for point letters in parsing and `canonical_clause` | `F4PointLetters`: parser/canonical units and an end-to-end lookup + verify with both points in one khoản |
| F5 [P1] revoked notebook still verified | `MAPPING` requires the notebook in the current INDEX whitelist for NOTEBOOKLM and NOTEBOOKLM_LOCAL_REREAD evidence | `F5NotebookWhitelistRevocation` |
| F6 [P1] semantic cache hit survived local drift | cache entries record each cited source's file identity; hits compare it and re-run on change; the miss path also requires the current file hash (decisions 7, 9) | `F6SemanticSourceIdentity`: hit after drift, still drifted, restored, cold lookup with drifted or missing file |
| F7 [P2] retry after startup timeout reused an unvalidated MCP process | client readiness flag set only after `initialize` + exact `tools/list`; startup errors kill the process; reader bound to its own process | `F7McpStartupReadiness` with `tests/m02/fake_mcp_server.py`: initialize timeout, restart re-checks the surface, tools/list timeout, dead process |

Also changed: `verify.response.v1.json` lists the new check names (the schema is still unreleased draft v1);
`EVIDENCE_ID` material now also covers `SOURCE_ID`, the excerpt flags and `ANSWER`.

## 12. Review round 3 — GPT_REVIEW_V1 at `eeb76bc` (PATCH_REQUIRED, F1–F7 confirmed fixed)

| Finding | Fix | Regression tests (`tests/m02/test_gateway_regressions.py`) |
|---|---|---|
| F8 [P2] a timed-out attempt kept running; a queued retry could send after the caller got `TIMEOUT` | `retry.Deadline` (absolute deadline + cancel flag) per attempt, visible to the backend through `retry.current_deadline()`; the MCP client acquires its lock only within the deadline, refuses to send when the attempt is expired or cancelled, bounds startup and calls by it, and retires a timed-out in-flight request (`notifications/cancelled`, then kills the process) | `F8NoBackendWorkAfterTheBudget`: the reviewer's repro (0.35 s server, 0.05 s attempts, 0.1 s budget) checks the fake server's timestamped call log one second after the caller returned; queued attempts behind a held client lock never send; repeated timeouts leave no late calls; a fast call still succeeds |
| F9 [P2] notifications restarted the response wait | `_request` computes one monotonic deadline and only waits for its remainder (polling the cancel flag); expiry is checked even while messages keep arriving | `F9AbsoluteResponseDeadline`: notification streams during `initialize`, `tools/list` (with F7 cleanup preserved) and `tools/call`, plus an endless stream |

The offline stand-in `tests/m02/fake_mcp_server.py` gained `--call-delay`, `--notify` and a timestamped `--times` log.

## 13. Review round 4 — GPT_REVIEW_V1 at `cb26095` (PATCH_REQUIRED, F1–F9 covered)

| Finding | Fix | Regression tests (`tests/m02/test_gateway_regressions.py`) |
|---|---|---|
| F10 [P2] a synchronous stdin write could block before the deadline loop; cleanup also wrote to the blocked pipe | `_StdinWriter` thread per process; `_send` waits for the write only until the request/attempt deadline (and the cancel flag), then raises `TIMEOUT` so the call is retired; `_retire` sends `notifications/cancelled` best-effort (≤ 50 ms) and kills; `_terminate`/`close` kill first and never close a stdin still held by a blocked write | `F10StalledStdin` with `fake_mcp_server.py --stall-after-list --small-stdin-pipe` (one-page pipe on Linux; Windows pipes are small by default) and the schema-maximum query of 2,000 `đ` (~12 KB after JSON escaping): the reviewer's repro returns `TIMEOUT` and within 0.5 s the lock is free, no worker or writer thread is alive and the old process is dead; a direct call without a retry deadline; recovery through a fresh validated process; `close()` while a write is stuck; the same large request still succeeds when the server reads |

Against the previous client (`e361f42`) the four stalled-stdin tests hang (caught); the positive control passes on both.

## 14. Stage A review — GPT_REVIEW_V1 at `fb14c65` (PATCH_REQUIRED, ambiguous clause IDs)

| Finding | Fix | Regression tests (`tests/m02/test_gateway_regressions.py`) |
|---|---|---|
| F11 [BLOCKER] exact lookup took the first section with a matching ID; real files repeat IDs (table of contents, repeated point letters), so an arbitrary occurrence (e.g. a table-of-contents line) came back `VERIFIED`; verify only checked the chosen span | `local.find_clauses()` returns every match: 0 → `SOURCE_NOT_FOUND`, 1 → continue, more → structured error `CLAUSE_AMBIGUOUS` with the occurrence count and line starts, no evidence. Evidence built for a section whose ID repeats (heuristic candidates, NotebookLM local reread) carries the blocking uncertainty `CLAUSE_AMBIGUOUS` (`STATUS: UNKNOWN`). `standards_verify` returns `CLAUSE: UNKNOWN` when the claimed clause ID occurs more than once in the current file, so legacy evidence is never `VERIFIED`. `find_clause()` returns `None` unless the ID is unique | `F11AmbiguousClause`: numeric table-of-contents/body duplicate (query and explicit `clause`), article nested point duplicate (`Điều 4 khoản 1 điểm a` twice), heuristic candidates with a duplicated ID, legacy evidence verified after the file gained a second occurrence (hash, excerpt still `PASS`; clause `UNKNOWN`), and match counting; unique IDs in the same files stay `VERIFIED` |

Against the pre-fix Gateway all five F11 tests fail (2 errors, 3 failures). `CLAUSE_AMBIGUOUS` is added to
`errors.py` and the `common.v1.json` error enum. The stage-A runner now checks ambiguous IDs as cases
(`PA-ambiguous-<doc>`: `ERROR CLAUSE_AMBIGUOUS`, occurrence count, no results).

## 15. Stage B plan review — GPT_REVIEW_V1 at `a9877ec` (PATCH_REQUIRED, out-of-scope citations)

| Finding | Fix | Regression tests |
|---|---|---|
| F12 [BLOCKER] citations outside the whitelist were dropped, but the full NotebookLM `ANSWER` was kept and attached to evidence from the allowed citations, so out-of-scope content (e.g. the M01 injection source) could shape a `FOUND`/`VERIFIED`, cached result | `NotebookLMAdapter.query` treats any citation or `sources_used` entry outside the queried source ids, or without a source id, as out of scope and returns no answer and no citations, only the out-of-scope ids. The service then raises `CITED_SOURCE_NOT_WHITELISTED` before any evidence is built, across all notebooks of the lookup, so nothing is returned, registered or cached | `test_gateway_regressions.F12OutOfScopeCitations`: mixed allowed + injection source, out-of-scope `sources_used`, unattributed citation (each: error, no answer/passage text in the response or logs, no registered evidence, the repeat lookup queries the backend again), the all-whitelisted control (`VERIFIED`, cached), and the adapter unit; `test_gateway_service.Semantic`: mixed response discarded, only-out-of-scope response, no-citation response `UNKNOWN`, queried-set control |

Against the pre-fix Gateway the six new negative tests fail (5 errors, 1 failure); the controls pass on both.

## Appendix — Issue #4 specification (verbatim)

CLAUDE_EXECUTION_V1

SCOPE: M02_STANDARDS_GATEWAY_IMPLEMENTATION_OFFLINE_FIRST
AUTHORIZATION: Owner explicitly asked ChatGPT to publish this draft and implementation request on GitHub for Claude to build, followed by GPT review.
BASELINE: M01 CLOSED; main merge 70c5e08e289505909b3619becc3ed03fc49f599b.
ARCHITECTURE_AUTHORITY: Issue #2.
STATUS: Implementation authorized in the bounded scope below; no merge or real-library pilot authorized yet.

### Yêu cầu Claude thực hiện

Đọc Issue #2 và các review M01 trước khi làm. Kiểm tra main hiện tại và tạo branch M02 riêng từ main, không làm tiếp trên branch M01, không push trực tiếp main.

Lưu đặc tả này thành docs/M02_STANDARDS_GATEWAY.md, ghi rõ quyết định triển khai, giả định và phần cần chủ máy cung cấp. Xây Gateway cùng kiểm thử bằng dữ liệu giả trên branch đó. Mở draft PR, liên kết issue này và yêu cầu GPT review tại HEAD cụ thể. Không dừng ở bản kế hoạch nếu phần triển khai offline có thể thực hiện.

Có thể chọn công nghệ phù hợp repo; ghi dependency/version và cách chạy Windows. Bổ sung phạm vi M02 vào hướng dẫn repo trên branch, giữ nguyên giới hạn bảo mật M01. Không sửa pin, config hoặc permission M01 để thuận tiện triển khai.

### 1. Mục tiêu và công cụ công khai

Claude chỉ thấy ba tool Gateway:
- standards_lookup: tìm tài liệu/điều khoản và trả bằng chứng.
- standards_verify: kiểm tra danh tính nguồn, phiên bản, hash, mapping và phạm vi áp dụng của bằng chứng; không chứng nhận thiết kế hay tính hợp pháp.
- standards_status: trạng thái INDEX, local adapter, cache, NotebookLM adapter và thời điểm kiểm tra.

Nextcloud là nguồn có thẩm quyền. Local sync/mount phục vụ đọc nhanh, NotebookLM phục vụ tìm kiếm ngữ nghĩa. Adapter local độc lập backend, không phụ thuộc nội bộ NotebookLM.

### 2. Luồng xử lý

Request -> validate input/WORK_CODE -> INDEX -> applicability/version/whitelist -> valid CACHE -> chọn LOCAL hoặc NOTEBOOKLM -> kiểm tra danh tính nguồn -> normalized evidence.

Cache có thể được kiểm tra sớm, nhưng kết quả chỉ được trả sau khi xác nhận nguồn/quy tắc hiện tại còn hợp lệ.
- Biết tài liệu/điều khoản: local, không gọi NotebookLM.
- Cần khám phá ngữ nghĩa: NotebookLM trong tập nguồn được phép.
- Không xác định được phạm vi áp dụng: UNKNOWN và dữ liệu còn thiếu.
- Không đủ bằng chứng: UNKNOWN hoặc ERROR; không tạo điều khoản/trích dẫn.

Không bắt buộc đọc lại local sau NotebookLM khi mapping tới nguồn có thẩm quyền, phiên bản xác định, whitelist hợp lệ và danh tính đồng bộ không có bất định trong lần chạy. Đọc lại khi câu trả lời mơ hồ, phụ thuộc bảng/hình/chú thích, mapping không chắc chắn hoặc nghi drift; không kiểm tra được thì UNKNOWN.

### 3. Schema và metadata

Tạo schema versioned cho request/response, INDEX và mapping.
lookup input: query, work_code, assessment_date, project_context; document_id/clause nếu biết.
verify input: evidence hoặc evidence_id, assessment_date/context.
status input: phạm vi kiểm tra tùy chọn.

Mỗi bằng chứng có các trường Issue #2:
STATUS, DOCUMENT, VERSION, CLAUSE, APPLICABILITY, SOURCE_ID, SOURCE_LOCATION, SOURCE_HASH, RETRIEVAL_PATH, EVIDENCE, ANSWER, UNCERTAINTY, VERIFIED_AT.
Định nghĩa kiểu dữ liệu, enum, trường bắt buộc/null và ý nghĩa verification. Các trường chưa biết phải có lý do; không tự điền.

INDEX.yaml cho máy; INDEX.md cho người đọc. Metadata: document ID/title/version, source path/hash, hiệu lực/ngày hiệu lực, điều kiện áp dụng, topic tags, NotebookLM mapping nếu có.
Không coi markdown tóm tắt là tài liệu gốc. Metadata hiệu lực/phạm vi trong fixture là giả, không tự suy luận hiệu lực tài liệu thật.

Cache key gắn với nội dung request/context, nguồn/phiên bản/hash, INDEX/rule version và mapping/sync identity. Thay đổi các yếu tố này phải vô hiệu hóa kết quả liên quan; không dùng cache để bỏ qua whitelist hoặc drift.

### 4. Adapter và giới hạn nguồn

Triển khai local adapter chỉ đọc, tìm mã/heading/clause; khóa đường dẫn trong source root được cấu hình, xử lý traversal/symlink/junction và Unicode Windows. Không ghi hoặc sửa file nguồn.
Định nghĩa format hỗ trợ và giới hạn trích xuất; format chưa hỗ trợ trả lỗi có cấu trúc, không bịa nội dung.

Triển khai NotebookLM adapter qua giao diện backend, dùng các khả năng đọc đã nghiệm thu M01. Viết contract tests bằng fake backend; chưa gọi NotebookLM thật trong vòng offline này. Raw NotebookLM tools không được lộ qua public Gateway. Thiếu mapping hoặc sync identity phải trả UNKNOWN, không được tuyên bố verified.

### 5. Lỗi, thời gian và dữ liệu

Mã lỗi tối thiểu:
INVALID_REQUEST, INDEX_INVALID, SOURCE_NOT_ALLOWED, SOURCE_NOT_FOUND,
VERSION_AMBIGUOUS, SOURCE_DRIFT, APPLICABILITY_UNKNOWN,
BACKEND_UNAVAILABLE, AUTH_REQUIRED, TIMEOUT.

Timeout và retry có số lần/tổng thời gian hữu hạn. Không retry lỗi quyền/phiên bản/mapping/phạm vi. Không tự login, chuyển backend hoặc mở whitelist để vượt lỗi.
Log tối thiểu: request/evidence ID, adapter/path, timing/status/error code; không cookie/token/auth, source text hoặc context nhạy cảm mặc định.
Tài liệu trả về là dữ liệu không đáng tin cậy; chỉ thị nhúng không được gây gọi tool, sửa policy/file hay lộ secret.

### 6. Nghiệm thu offline, cần có negative controls

- Public tools/list đúng ba tool; raw NotebookLM tools/mutation không lộ.
- Exact local lookup không gọi NotebookLM (assert call count=0).
- Semantic lookup chỉ dùng source whitelist.
- Wrong/absent mapping, unknown applicability/version hoặc source drift không trả verified evidence.
- Cache invalidation đúng khi nguồn/INDEX/rules/mapping đổi; cache không vượt source checks.
- Fixture có chỉ thị nhúng không làm phát sinh hành động hoặc thay đổi file/policy.
- Source root bất biến trước/sau; traversal/escape bị từ chối.
- Timeout, transient retry exhaustion, unavailable backend và missing input có kết quả có cấu trúc.
- Unicode Windows và các format đã công bố hoạt động hoặc fail có cấu trúc.
- Model-visible Gateway isolation có evidence, phân biệt kiểm thử mock với kiểm thử Claude/NotebookLM thật.
- M01 regression có liên quan vẫn PASS; secret scan PASS.
Không ghi OFFLINE_PASS thành M02 overall PASS.

### 7. Thư viện thật: bước sau review

Chưa có đủ đường dẫn thư viện Nextcloud, quyền đọc, tài liệu pilot/hash/format, WORK_CODE/context, người duyệt hiệu lực/applicability, mapping và sync proof.
Không tự chọn thư viện thật hay bulk-ingest dữ liệu. Ghi MISSING_OWNER_INPUTS rõ ràng; phần thiếu này không chặn xây core và tests bằng fixture.
Live pilot chỉ mở sau GPT_REVIEW_V1 cho code mới và chủ máy cung cấp phạm vi nguồn cụ thể.

### 8. Giới hạn và báo cáo

Không merge; không M03 governance rollout; không AutoCAD/DWG; không NotebookLM source/notebook/share mutation; không đổi credential/pin/permission M01; không thu thập cookie cloud; không commit standards PDF/raw transcript/source text nhạy cảm.

Khi xong, post trên draft PR:
CLAUDE_EXECUTION_REPORT
HEAD_COMMIT: <full SHA>
BASE_COMMIT: <full SHA>
SCOPE: M02_STANDARDS_GATEWAY_IMPLEMENTATION_OFFLINE_FIRST
IMPLEMENTED:
TEST_RESULTS: <commands/results, negatives and mock/live distinction>
ENVIRONMENT:
SECURITY_BOUNDARY:
OPEN_ISSUES:
MISSING_OWNER_INPUTS:
M02_STATUS: IN_PROGRESS / OFFLINE_VALIDATED (không tự đóng M02)
NEXT_REQUEST: REQUEST_GPT_REVIEW

GPT sẽ review architecture/schema/security/tests tại exact HEAD. Nếu PATCH_REQUIRED, sửa cùng PR trong phạm vi review; chưa merge hay chạy pilot thật trước gate tiếp theo.
