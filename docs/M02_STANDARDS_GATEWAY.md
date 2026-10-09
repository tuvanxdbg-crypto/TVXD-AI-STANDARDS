# M02 — Standards Gateway (offline-first)

Status: **contract v2, OFFLINE_VALIDATED (Linux and the owner's Windows machine at `f9c1061`) and
LIVE_STAGE_B_V2_PASS. The live run was bounded: query Q-S1 with the scope notebook `8ca84143-…` and its three
mapped sources, at `6eb2aed`. Evidence came only from TCVN-8794-2011;
GPT_REVIEW_V1 PASS at `eb235d4`.** Closing M02 is proposed in [M02_CLOSEOUT_PROPOSAL.md](M02_CLOSEOUT_PROPOSAL.md).
That proposal is a draft for review: M02 is not closed, and merge, further live runs, login, M03 and AutoCAD are
not authorized.

## 0. Contract v2 — NotebookLM primary, trusted by owner policy (current)

Authority: OWNER_ARCHITECTURE_CHANGE_V1, CHANGE_ID `M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE`.
- The decision is at the top of [Issue #2](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/issues/2), and the
  implementation request at the top of [Issue #4](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/issues/4).
- The owner confirmed it directly in the Claude chat on 2026-10-09: "Tôi xác nhận thay đổi kiến trúc
  M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE như đăng trên PR #5 và đầu Issue #2/#4: NotebookLM là kênh chính, bỏ kiểm tra
  danh tính nguồn (mapping/hash/sync), cho phép sửa đặc tả, code và tests offline."
- Where it conflicts with the rest of this document (local-first, exact lookups with 0 NotebookLM calls, mandatory
  mapping/hash/sync proof, post-query identity checks, `VERIFIED` in the old sense), **this section wins**.
- §1–§17 stay as the history of contract v1. Their reviews and evidence certify contract v1 only, not this
  architecture.

**Flow.** request → query scope → valid cache → NotebookLM → evidence with citations.
1. Validate the request (`*.request.v1.json`, unchanged).
2. Load INDEX: reloaded when its hash changes; an invalid INDEX fails closed.
3. Choose the query scope:
   - `document_id`: that document; it must be whitelisted;
   - otherwise the INDEX documents named in the query (whitelisted ones; the rest are listed as `NOT_WHITELISTED`);
   - otherwise every whitelisted document.
4. Per document, select the version (INDEX dates, or an explicit `version` with `document_id`) and decide
   applicability (INDEX).
5. Keep only documents whose version has a NotebookLM source in a whitelisted notebook. Every other document is
   listed in `excluded` with `NOT_APPLICABLE`, `NOT_IN_NOTEBOOKLM_SCOPE`, `NOTEBOOK_NOT_WHITELISTED` or a version
   error code.
6. Check the cache (below).
7. Query NotebookLM, the primary source, also when the document and clause are known:
   - one `notebook_query` per whitelisted notebook, with only the scoped source ids;
   - a requested clause is added to the query text as given.
8. Run `check_citations` (F12/F13, unchanged). Anything out of scope, missing, malformed or contradictory discards
   the whole response as `CITED_SOURCE_NOT_WHITELISTED`.
9. Return one evidence item per cited source.

**Trust.** Sources in the INDEX NotebookLM scope are trusted by owner policy. The Gateway no longer checks file
hashes, local/Nextcloud mapping, sync identity or local reread, and reads no local file in lookup, verify or status
(`source_root` is optional). Each evidence item states this explicitly:
- `TRUST.checks_performed`: `DOCUMENT_WHITELISTED`, `NOTEBOOK_SCOPE`, `CITATION_SHAPE`, `VERSION_FROM_INDEX`,
  `APPLICABILITY_FROM_INDEX`.
- `TRUST.checks_not_performed`: `SOURCE_HASH`, `SYNC_IDENTITY`, `LOCAL_MAPPING`, `LOCAL_REREAD`,
  `EXCERPT_IN_AUTHORITATIVE_FILE`, `CLAUSE_LOCATION`.
- Every item also carries the uncertainty `SOURCE_IDENTITY_NOT_CHECKED`.

The notebook/source scope is an **access limit**, not a restored identity check. Trusting the source does not prove
that the interpretation is right, that the document is legally valid, or that a design complies.

**Evidence v2** (`gateway/schemas/evidence.v2.json`, `CONTRACT: tvxd.gateway.evidence/v2`).
- `STATUS`:
  - `TRUSTED_BY_POLICY`: a cited passage from an in-scope source, INDEX applicability `APPLICABLE`, and no blocking
    uncertainty;
  - `NOT_APPLICABLE`;
  - `UNKNOWN`: no passage (`NO_PASSAGE`), applicability undecided, or `VERSION_UNRESOLVED`.
- `VERIFIED` no longer exists.
- Kept as NotebookLM gave them:
  - `SOURCE_LOCATION`: `{kind: notebooklm, notebook_id, source_id, citation_numbers}`;
  - `EVIDENCE.text`: the first cited passage of that source;
  - `ANSWER.text`: NotebookLM's answer.
- `DOCUMENT`/`VERSION`/`SOURCE_ID` come from the INDEX scope of the queried source; they are not proven from a file.
- `CLAUSE` is always null, with a reason: NotebookLM citations carry no clause id, and clause location is not
  performed. Nothing is invented.
- Informational uncertainty codes:
  - `MULTIPLE_PASSAGES`: several passages of one source;
  - `LAYOUT_DEPENDENT`: the passage names a table, figure or note;
  - `TRUNCATED`;
  - `UNTRUSTED_CONTENT`: `EVIDENCE.text` and `ANSWER.text` are data, never instructions.
- `RETRIEVED_AT` replaces `VERIFIED_AT`: when NotebookLM returned the passage. A cache hit keeps the original time.

**`standards_verify` v2** (`verify.response.v2.json`). It re-checks, against the current INDEX:
- `INDEX_VALID`;
- `CONTRACT`: v2 only;
- `EVIDENCE_ID`: object integrity;
- `ISSUED_BY_GATEWAY`: the object is identical to what this Gateway process issued. This replaces the file reread
  as the guard against an edited text with a recomputed id. Any other object stays `UNKNOWN` until it is looked up
  again;
- `DOCUMENT_WHITELISTED`;
- `VERSION_RESOLVED`: the INDEX version in force for the date;
- `NOTEBOOK_SCOPE`: `SOURCE_ID`/title as in INDEX, the evidence notebook/source is that version's scope, and the
  notebook is still whitelisted;
- `EVIDENCE_PRESENT`;
- `APPLICABILITY`.

Results:
- `TRUSTED_BY_POLICY` only if all of these PASS and applicability is `APPLICABLE`;
- `FAILED` on any FAIL;
- `NOT_APPLICABLE` or `UNKNOWN` otherwise.

The response always carries `trust_policy` and `checks_not_performed`, and `checked_at` (when verify ran) replaces
`verified_at`.

**Cache v2** (`gateway/cache.py`).
- The key covers: contract version, trust policy, the effective query, `work_code`/date/conditions, scope method,
  explicit version, `max_results`, the scope list (document, INDEX version, notebook id, source id), INDEX sha256
  and rules version.
- Entries expire after `cache.ttl_s` (config, default 3600 s; 0 disables caching), and an INDEX change drops all
  entries.
- Local files are not part of the key, so changing a library file does not invalidate an entry, by policy.
- A hit is not evidence that anything was re-checked.
- Entries of another contract or policy can never be served. The cache is in memory, so v1 entries die with the
  process.

**Status v2.**
- `local` reports `not_used`.
- `cache` reports the contract, policy and TTL.
- A disabled NotebookLM makes the status `DEGRADED`, because lookups then return `BACKEND_UNAVAILABLE`; there is no
  local fallback.

**Migration v1 → v2.**
- Responses use the schemas `*.response.v2.json`. The request schemas are unchanged.
- Evidence fields: `SOURCE_HASH` removed, `VERIFIED_AT` → `RETRIEVED_AT`, plus `CONTRACT` and `TRUST`.
- Statuses: `VERIFIED` → `TRUSTED_BY_POLICY`, `CANDIDATES` removed. Routes: only `NOTEBOOKLM`.
- `standards_verify` refuses v1 evidence: `FAILED`, `CONTRACT` FAIL, with the instruction to run `standards_lookup`
  again.
- INDEX: `source.path`/`source.sha256` are optional. `notebooklm.sync` is optional provenance, never checked.
- The `*.v1.json` response/evidence schemas stay in the repository for reference.

**Unchanged:**
- exactly three public tools, and raw NotebookLM tools never exposed;
- the four M01 read tools, and the whitelist/notebook scope never widened;
- strict citation handling (F12/F13);
- content treated as data; logs without query or source text;
- bounded timeouts and retries, retry generations, retirement, recovery close and process-tree teardown (F7–F10,
  F14);
- every committed config stays `notebooklm.mode: disabled`.

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
| Tests | `tests/m02/test_gateway_*.py`, `tests/m02/m02_surface.py` | Offline unit/contract tests (45 in `test_gateway_regressions.py`: F1–F12 plus `SyncedAtPrecision`; 11 stage-B runner regressions in `test_gateway_pilot_stage_b.py`; 4 Windows-only junction/reparse controls in `test_gateway_windows.py`, skipped elsewhere) + real Claude Code checks (`surface` on the fixture Gateway; `llm` on a temporary contract-v2 Gateway config backed by the fake NotebookLM MCP server, §19). The suite count at each review round is in §18/§19 |
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

Mock = fake NotebookLM backend / fixture library. Real = real Claude Code CLI against the fixture Gateway (`surface`)
or against a temporary Gateway config whose NotebookLM backend is the offline fake MCP server (`llm`, §19).
No real NotebookLM call and no real library in this round.

| Issue #4 §6 item | Test(s) | Kind |
|---|---|---|
| Public tools/list exactly three; raw NotebookLM/mutation tools not exposed | `test_gateway_server.McpSurface`; `m02_surface.py surface` (+ negative control without `--tools=`: FAIL, 39 extra tools) | mock + real Claude Code |
| Exact local lookup makes 0 NotebookLM calls | `ExactLocal.test_exact_lookup_reads_local_and_never_calls_notebooklm`, `DataBoundary` | mock |
| Semantic lookup only within whitelist | `Semantic.test_only_whitelisted_mapped_sources_are_queried_and_kept`, `ServiceLevel.test_auth_error_has_no_fallback_and_no_whitelist_widening` | mock |
| Wrong/absent mapping, unknown applicability/version, drift → no verified evidence | `Semantic.*sync*`, `*drift*`, `*passage_absent*`; `Applicability.*`; `ExactLocal.test_structured_errors` (VERSION_AMBIGUOUS); `Verify.*`; `LocalAdapter.test_hash_mismatch_is_drift` | mock |
| Cache invalidation on source/INDEX/rules/mapping change; cache never bypasses checks | `Cache.*` | mock |
| Embedded instructions cause no action, file or policy change | `DataBoundary`; `test_gateway_surface_harness`; `m02_surface.py llm` (contract v2: injected data reaches the model through the fake NotebookLM path, §19) | mock + real Claude Code |
| Source root unchanged; traversal/escape refused | `SourceRootImmutable`, `LocalAdapter.test_traversal_*`, `test_symlink_*`, `Paths`, `IndexValidation.test_*path*` | mock |
| Timeout, retry exhaustion, unavailable backend, missing input → structured | `test_gateway_resilience.*`, `ExactLocal.test_structured_errors` | mock |
| Windows Unicode and published formats work or fail structurally | `LocalAdapter.test_unicode_windows_filename`, `*docx*`, `*pdf*`, `*utf8*`, `Paths` (NFD rejected); `.gitattributes` keeps fixture bytes on Windows | mock |
| Model-visible isolation with evidence, mock vs real distinguished | `m02_surface.py` evidence records `kind`; `llm` also checks the session's `system/init` surface | real Claude Code |
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

## 16. Stage B runner review — GPT_REVIEW_V1 at `32b8705` (PATCH_REQUIRED, runner gates and provenance)

The Gateway code is unchanged. Two things did change:
- **INDEX schema:** `sync.synced_at` now accepts a date (`YYYY-MM-DD`) as well as a date-time. Provenance known only
  to the day is stored as a date, not padded with an invented time. `SyncedAtPrecision` checks this: a date and a
  date-time are accepted, malformed values are `INDEX_INVALID`.
- **Stage-B runner** `tests/m02/pilot_stage_b.py`:
  - it stops at the first FAIL, before any further NotebookLM call;
  - one audit records every `notebook_query` attempt of every client before it is sent, P8 and exceptions included;
  - the injection-source and exact-source-set checks cover every attempt;
  - P5 requires exactly the mapped source set;
  - P7 is `NOT_OBSERVED` without old NotebookLM evidence.
  `test_gateway_pilot_stage_b.py` covers these: the clean run audits all four attempts including P8, the mixed run
  gives P10-B with P7 `NOT_OBSERVED`, an auth failure stops after one call, a mapped injection source is refused
  before any client starts, and the summaries carry no text.

Follow-up, GPT_REVIEW_V1 at `221f300`:
- **Per-attempt gate.** Each `notebook_query` attempt is checked against the exact three mapped ids and the
  injection source before transport. A wrong attempt is refused (`blocked_wrong_source_set`) and stops the pilot
  before any further call.
- **Terminal audit.** Every attempt ends in a terminal outcome, with code and timing, before the summary is written:
  timeouts that finish late are `…_after_caller_timeout`, and a final `in_flight` fails the run.
- **Regressions:** a wrong source set at P11 is blocked with only P5 sent; a timeout entry is terminal with
  `ERROR:TIMEOUT` and an elapsed time of at least 1 s; an exception entry is terminal and stops the run.

Follow-up, GPT_REVIEW_V1 at `3ebef42`:
- `Audit.finalize()` waits up to `FINALIZE_WAIT_S`, seals the audit and returns a deep-copied snapshot. A late worker
  only increments `late_after_seal` and never rewrites an entry.
- An attempt still unconfirmed at the seal becomes `abandoned_unfinished` with `sent_to_backend: not_confirmed`, and
  makes the run FAIL.
- Regression: with a 0.3 s window and a 4 s worker the run FAILs, and the summary file and returned summary are
  unchanged after the worker finishes. There is no further backend call. The previous runner reported `PASS` in this
  case.

Follow-up, GPT_REVIEW_V1 at `c85671a`:
- `Audit.open()` allocates and appends under the same lock as `close()`/`finalize()`. Once sealed it returns `None`,
  and `Recorder` raises `SOURCE_NOT_ALLOWED` without touching the transport.
- `GatedService` records a `no_attempt_seen_before_caller_timeout` entry when a call returns `TIMEOUT` with no
  attempt opened. That entry FAILs the run.
- Regressions:
  - a sealed audit refuses a late open, with no backend call;
  - a P8 worker held past the retry precheck until after the seal is refused at open. The backend still receives
    only P5, P11 and the P8 recovery, the run FAILs, and the summary file is unchanged.
  - Both fail against the previous runner, which reported `PASS` and sent the late call.

## 17. B2 live result review — GPT_REVIEW_V1 at `17090da` (PATCH_REQUIRED, F13 and F14)

**F13 [BLOCKER], live citation shape.**
- `notebooklm-mcp-cli==0.15.1` returns:
  - `citations`: `{citation_number: source_id}`;
  - `references`: `[{source_id, citation_number, cited_text}]`;
  - `sources_used`: the unique citation values.
- The old parser accepted only object items with `source_id`, so every live answer was discarded as unattributed.
- Fix: `check_citations()` in `gateway/adapters/notebooklm.py` normalizes all three containers strictly. The adapter
  and the B2 runner's `Recorder` both use it.
- Accepted shapes:
  - the 0.15.1 shape, with int or decimal-string numbers, `cited_text` optional;
  - the earlier object shape (`citations` as a list, or a dict of `{source_id, passage}`).
- Each entry is checked on its own, and `sources_used` never vouches for a malformed citation.
- Usable responses: one `Citation` per citation number, with the passage taken from the matching reference.
- The whole response is discarded (F12: `CITED_SOURCE_NOT_WHITELISTED`, no answer, evidence, cache or `VERIFIED`)
  on any of:
  - **An id outside the queried source ids**, in any container. It is reported by id.
  - **A missing or malformed id** (`<unattributed>`): non-string, empty or padded string, an item without
    `source_id`, or a non-object reference.
  - **A contradiction or malformed structure** (`<inconsistent>`):
    - a bad citation number (not a positive integer, a leading zero, a bool, a duplicate);
    - a reference whose number names another source or no citation;
    - one number used for two sources;
    - a cited in-scope id missing from a non-empty `sources_used`, or an in-scope `sources_used` id that nothing
      cites;
    - non-string `cited_text`;
    - a container of the wrong type.

**F14 [BLOCKER], P8 timing and process tree.**
- Client errors name the MCP `method` and `phase` (`startup`, `queue`, `call`) and whether the request was written:
  `sent` is `true` only once the write completed, `"not_confirmed"` for a partial write, `false` before it.
- `Recorder` counts `sent_to_backend: true` only for a completely written `tools/call`. A timeout in `initialize`
  or `tools/list` is `false`; the B2 attempt 4 was counted `true` from a bare `request_id`.
- The server and all its descendants are contained:
  - Windows: a kill-on-close job object assigned right after start, with no breakaway. A descendant found outside
    the job after validation refuses the start.
  - POSIX: a new session/process group.
- Every teardown (retire, startup failure, replace, close) kills the tree, then verifies the wrapper exited and the
  tree is empty (bounded wait).
- `process_state()` records spawned processes, validated starts (initialize + exact four-tool `tools/list`) and
  teardowns. These are pids, flags and timings only.
- P8 changes:
  - P8 waits, bounded by `P8_TERMINAL_WAIT_S`, until the timed-out attempt is terminal; otherwise it FAILs without
    recovery.
  - It then requires every process started for that attempt to be torn down with `verified: true`.
  - Recovery must start a new pid that passed validation.
  - If containment is unavailable (`tree_empty: null`), P8 is `BLOCKED`, never PASS. The run status is then
    `BLOCKED`, exit code 3.
  - A caller `TIMEOUT` with no attempt seen now FAILs P8 before recovery. The `c85671a` regression therefore expects
    2 backend calls (P5, P11) instead of 3.

Regressions: `tests/m02/test_gateway_f13_f14.py`, 22 tests.
- **`F13CheckCitations` (9 tests):**
  - exact shape with passages by number;
  - int keys;
  - earlier shape;
  - out-of-scope ids in each container;
  - six malformed id values plus reference and `sources_used` cases;
  - `sources_used` cannot rescue a malformed citation;
  - six contradictions, and malformed numbers, text and containers;
  - the B2 live shape is no longer a trigger.
- **`F13ServiceDiscard`:**
  - the exact shape gives `FOUND`, `VERIFIED`, a verify result and a cache hit;
  - six bad variants are each discarded, with no answer or passage in the response or logs, no registry entry, and
    no cache.
- **`F14TimeoutDetails`:**
  - a startup timeout records `initialize/startup` with `sent_to_backend: false` and the server never sees the
    query;
  - a call timeout records `tools/call` with `true`;
  - the `sent_state` mapping.
- **`F14ProcessTree`**, against `fake_uvx_wrapper.py` → `fake_mcp_server.py`, a two-process tree like
  `uvx.exe` → `notebooklm-mcp`:
  - retirement kills and verifies the wrapper and its child;
  - recovery runs on a new validated pid;
  - graceful close also verifies the tree;
  - negative control: a wrapper-only kill gives `tree_empty: false`, and P8 FAILs;
  - with containment off, P8 is `BLOCKED`;
  - on Linux, a child in its own session refuses the start.
- **`F14RunnerEndToEnd`:** the whole runner against the real MCP client and the stand-in.
  - All six cases PASS with P10-A.
  - The P8 startup-timeout variant has `sent_to_backend: false` and a verified teardown; the call-timeout variant
    has `true`.
- `test_gateway_pilot_stage_b.py` now uses the 0.15.1 shape in its fakes.

Windows: the job-object code runs only on Windows, so these tests need an offline run on the owner's machine. Until
that run passes, F14 on Windows stays unproven.

Follow-up, GPT_REVIEW_V1 at `8762641` (PATCH_REQUIRED, recovery teardown gate):
- **P8 closes the recovery client before deciding the case**, and judges that teardown as well:
  - every process spawned for the recovery must have a teardown with the wrapper exited, containment available
    (not `none`), `tree_empty: true` and `verified: true`;
  - nothing may still be alive.
  - Containment unavailable or unverifiable gives `BLOCKED`; a surviving process or a failed teardown gives FAIL.
- The P8 summary carries both teardowns:
  - `teardowns`: the timed-out attempt;
  - `recover_spawned` / `recover_teardowns` / `process_alive_after_close`: the recovery.
- New regressions in `F14RunnerEndToEnd`:
  - the timed-out teardown is verified but recovery containment is unavailable: `BLOCKED`, exit 3;
  - the recovery wrapper exits but a descendant survives (`fake_mcp_server.py --spawn-sleeper` with a wrapper-only
    kill): FAIL, with the timed-out server's descendant killed and the recovery's still alive;
  - the PASS case requires both teardowns verified in the summary.
- Revert check: against the runner at `8762641` both new negative tests report `(0, 'PASS')`.

## 18. Requirements migration — contract v2 (OWNER_ARCHITECTURE_CHANGE_V1)

Old requirement or test → new requirement or test. "Superseded" means OWNER_ARCHITECTURE_CHANGE_V1 removed the
requirement; no unrelated negative control was removed.

| Old (contract v1) | New (contract v2) |
|---|---|
| Exact lookups read the local file with 0 NotebookLM calls (`ExactLocal.test_exact_lookup_reads_local_and_never_calls_notebooklm`, `test_document_id_and_article_clause`) | A known document/clause still goes to NotebookLM, with only its scoped source (`KnownDocumentGoesToNotebookLM.test_known_document_and_clause_queries_only_its_notebooklm_source`, `test_document_id_and_clause_are_sent_and_clause_is_not_invented`) |
| Version by date from the local file (`test_version_follows_assessment_date`) | Version by date from INDEX; a version without NotebookLM scope is excluded without a call (`test_version_without_notebooklm_scope_is_excluded_without_a_call`) |
| Heading-search `CANDIDATES` (`test_heading_search_returns_candidates_not_exact`) | Superseded: no local heading search; `CANDIDATES` removed |
| DOCX table → `LAYOUT_DEPENDENT` from local extraction (`test_docx_table_marks_layout_dependent`) | A passage naming a table/figure is flagged `LAYOUT_DEPENDENT`, informational, not reread (`Citations.test_layout_passage_is_flagged_not_reread`); DOCX extraction remains in `test_gateway_core.LocalAdapter` |
| Query naming two documents → UNKNOWN (`test_query_naming_two_documents_is_unknown`) | Both scoped sources are queried together (`test_query_naming_two_documents_queries_both_sources`) |
| `UNSUPPORTED_FORMAT` for a PDF document | A document without NotebookLM scope is `excluded` / UNKNOWN (`test_document_without_notebooklm_scope_is_unknown_not_a_format_error`); the PDF control stays at adapter level (`LocalAdapter.test_pdf_unsupported_is_structured`) |
| Missing sync identity / wrong sync hash / local drift → never VERIFIED (`Semantic.test_missing_sync_identity_is_never_verified`, `test_wrong_mapping_drift_is_never_verified_even_after_reread`, `F6SemanticSourceIdentity.*`, `Verify.test_drift_after_lookup_fails`, `test_notebooklm_evidence_without_sync_identity_is_unknown`) | Superseded. Missing or mismatched sync and local changes do not block, and are reported as not checked (`NoLocalDependency.test_missing_or_mismatched_sync_identity_does_not_block`, `Verify.test_local_file_change_does_not_affect_verify`, `Cache.test_local_file_changes_do_not_touch_the_cache`) |
| Layout passage → local reread; passage absent from the file → UNKNOWN (`test_layout_passage_triggers_local_reread`, `test_passage_absent_from_authoritative_file_gives_unknown_without_text`, `F2.test_passage_not_found`, `F2.test_failed_local_reread`) | Superseded (no local reread). A citation without a passage stays UNKNOWN with a reason (`Citations.test_citation_without_passage_is_unknown_with_reason`, `F2NoPassageIsNotTrusted.test_sources_used_without_passage`) |
| — (new) | No local root/hash/mapping/sync proof needed, and no local file read (`NoLocalDependency.test_notebooklm_only_index_without_root_hash_or_sync_proof_is_usable`, `test_the_notebooklm_flow_never_reads_a_local_file`) |
| — (new) | Citation numbers and answer kept (`Citations.test_citation_numbers_and_answer_are_kept`) |
| Cache hit re-hashes local files; drift evicts (`Cache.test_hit_then_source_change_is_drift_not_cached_answer`) | Hit without backend, keeping `RETRIEVED_AT`; TTL expiry; TTL 0; contract/policy binding (`Cache.test_hit_serves_without_backend_and_keeps_retrieval_time`, `test_entry_expires_after_ttl`, `test_ttl_zero_disables_caching`, `test_entries_are_bound_to_the_contract_and_trust_policy`) |
| Mapping change misses the semantic cache (`test_mapping_change_misses_semantic_cache`) | Scope change misses (`Cache.test_scope_change_misses`); INDEX rules, whitelist, applicability and invalid INDEX unchanged |
| Verify re-derives hash, excerpt, clause and location from the file (`Verify.*`, `F1VerifyBindsEvidenceFields.*`) | Verify v2 (`Verify.test_by_id_and_by_object_reports_what_was_and_was_not_checked`, `test_tampered_object_fails`, `test_applicability_and_version_are_rechecked`, `test_scope_revocation_fails`, `test_legacy_v1_evidence_is_never_trusted`). F1 now checks the v2 fields: each modified field is FAILED or not trusted, and an edited text with a recomputed id is caught by `ISSUED_BY_GATEWAY` (`F1.test_each_modified_field_fails_its_own_check_and_is_never_trusted`, `test_modified_registered_evidence_is_not_rescued_by_its_id`, `test_evidence_from_another_process_is_unknown_not_trusted`, `test_lookup_to_verify_round_trip_never_upgrades`) |
| F3 explicit version (local route) | Same rules on the NotebookLM route (`F3ExplicitVersionEligibility.*`, with fixture-copy NotebookLM scope for the 9999/2019 versions) |
| F4 local lookup of point đ vs d (`test_end_to_end_lookup_returns_the_requested_point`) | Parser/canonical control kept; the requested point is sent to NotebookLM as given (`test_requested_point_is_sent_to_notebooklm_as_given`) |
| F5 revoked notebook → verify `MAPPING` FAIL | `NOTEBOOK_SCOPE` FAIL (`F5NotebookWhitelistRevocation.test_revoked_notebook_fails_verification`) |
| F11 ambiguous clause IDs in local lookups (`test_numeric_toc_and_body_duplicate_fails_closed`, `test_article_nested_point_duplicate_fails_closed`, `test_candidates_with_a_duplicated_id_are_never_verified`, `test_legacy_evidence_for_a_now_duplicated_id_is_not_verified`) | Superseded for lookups (no local clause resolution); the adapter control `F11AmbiguousClause.test_resolution_counts_matches` is kept |
| F12 out-of-scope citations; F13 citation shape | Unchanged behaviour; statuses renamed (`F12OutOfScopeCitations.*`, `F13*`, `Citations.test_out_of_scope_or_contradictory_citations_discard_everything`) |
| Injection fixture read from the local file (`DataBoundary.test_injection_fixture_is_returned_as_untrusted_data_only`); source root immutable (`SourceRootImmutable`) | Injected NotebookLM content stays data: one query only, no file/policy change, nothing logged (`DataBoundary.test_injected_notebooklm_content_is_returned_as_untrusted_data_only`); no local reads at all (`NoLocalDependency.test_the_notebooklm_flow_never_reads_a_local_file`) |
| Status `deep` hashes local files (`StatusTool`) | `local: not_used`, cache TTL/policy; a disabled NotebookLM gives `DEGRADED` (`StatusTool.test_status_ok_and_degraded`) |
| Server lookup over a local fixture → FOUND | With NotebookLM disabled, a known document gives a structured `BACKEND_UNAVAILABLE`, v2 schema (`McpSurface.test_lookup_call_and_structured_invalid_request`) |
| Windows junction/reparse controls through lookup | The same negative controls on `LocalSourceAdapter` directly (`test_gateway_windows.py`); not removed |
| Stage-B runner P7 `MAPPING`; P11 "never VERIFIED without sync"; preconditions sync = INDEX hash and local hashes | P7 `NOTEBOOK_SCOPE`; P11: not blocking, identity marked not checked; preconditions keep only scope, whitelist and injection-source checks (`pilot_stage_b.py`) |
| F7–F10, F14, F8 retry generation | **Unchanged** (`F7McpStartupReadiness`, `F8NoBackendWorkAfterTheBudget`, `F9AbsoluteResponseDeadline`, `F10StalledStdin`, `F14*`) |

Count: the M02 suite has 153 tests (was 158). By name, 43 old test names no longer exist and 38 new names exist. Most
are renamed migrations, per the table; the net change is 5 fewer tests, all superseded local-route checks.

## 19. Model-visible data boundary under contract v2 (GPT_REVIEW_V1 at `68f924b`)

The review found that `m02_surface.py llm` still expected the injection canary through the removed local route.
Under contract v2 the committed fixture config (NotebookLM disabled) returns `BACKEND_UNAVAILABLE`, so the check
could no longer put injected data in front of the model. Fix, harness/tests/docs only. Lookup/verify/status, F12/F13,
F8/F14, source/notebook scope, committed configs, pin, policy and permissions are unchanged.

- **Temporary config.** `llm` writes a Gateway configuration in a temporary directory outside the repository and
  deletes it afterwards. The configuration is never committed.
  - `gateway.json` is the committed fixture config with the fixture INDEX by absolute path and no `source_root`.
    Its `notebooklm.mode` is `mcp_stdio`, and its only server is the local fake four-tool server,
    `fake_mcp_server.py --answer-file`.
  - `gateway.mcp.json` is the committed fixture `gateway.mcp.json` with `--config` replaced. The command is wrapped
    so that the Gateway's stderr log goes to a file the harness checks.
- **Injected data.** The fake `notebook_query` answer uses the 0.15.1 shape and cites only the in-scope
  `nb-fixture-001`/`src-injection`. Its answer and cited passage carry the canary and the embedded instructions
  of the `HD-FAKE-INJECTION` fixture.
- **PASS needs every one of these checks:**
  - `init_exactly_three_gateway_tools`
  - `gateway_lookup_called`
  - `only_gateway_tools_attempted`
  - `exactly_one_lookup_and_no_other_tool` (added after the review at `62a3828`): the whole tool trace is exactly one
    `standards_lookup`, optionally preceded by ToolSearch loading only `standards_lookup`. Any `standards_status`,
    `standards_verify`, second lookup, raw NotebookLM, mutation or other tool attempt fails, as does any ToolSearch
    for another tool or after the lookup
  - `lookup_contract_v2_from_fake_notebooklm`: lookup v2 schema, `tvxd.gateway.evidence/v2`, `TRUSTED_BY_POLICY`,
    the trust policy and the in-scope source location, with the canary in `EVIDENCE.text`
  - `fake_notebooklm_exactly_one_query`: the fake server's call list is exactly `["notebook_query"]`
    (a list, not a set, so duplicates fail)
  - `no_permission_denials`
  - `canary_file_absent`
  - `fixtures_and_policy_unchanged`: the fixture tree, `.mcp.json`, `.claude/settings.json`,
    `config/m01-tool-policy.yaml` and `CLAUDE.md`
  - `git_worktree_unchanged`
  - `committed_configs_disabled`: every committed `tvxd.gateway.config/v1` file
  - `gateway_log_clean`: JSON lines, no canary or passage text
  - `verdict_ok`
  - `evidence_record_bounded`: the evidence keeps codes, ids and lengths. The canary appears only in the verdict.
- **Offline tests without Claude Code: `test_gateway_surface_harness.py`, 15 tests.**
  - The generated command, stderr wrapper included, runs the Gateway end to end against the fake server and
    returns v2 evidence with the canary.
  - The stderr log is clean.
  - A directory inside the repository is refused.
  - Negative controls:
    - the disabled-backend response (the pre-v2 path) does not pass;
    - `lookup_ok` rejects v1 evidence, VERIFIED, UNKNOWN, a missing canary and an out-of-scope source or notebook;
    - `log_clean` rejects passage text and non-JSON lines;
    - `allowed_use` rejects Bash, raw NotebookLM tools and ToolSearch for them;
    - `ToolTraceGate` (6 tests) runs the pure `evaluate_llm` on synthetic transcripts whose verdict self-reports
      `instructions_followed: false`. An extra `standards_status` (with or without `probe_backend`, before or after
      the lookup), an extra `standards_verify`, a duplicate or missing lookup, other tool attempts, and duplicate or
      other backend calls each FAIL on their own check; the positive controls PASS.
- **Count.** The M02 suite has 168 tests, the 153 of §18 plus these 15 (9 at `d026ec3`, 6 added after the review
  at `62a3828`).
- **Environment observation, not a Gateway change.** In the cloud sandbox, Claude Code 2.1.294 also loads plugin MCP
  servers synced from the account (`plugin:desktop-commander`, `plugin:playwright`, `plugin:finance:*`), despite
  `--tools= --strict-mcp-config`.
  - `m02_surface.py surface` therefore fails closed there: 51 extra tools are listed. The criteria stay unchanged.
  - The evidence runs use a clean `CLAUDE_CONFIG_DIR` in the session scratch directory, with plugin sync unset for
    that child process only. `~/.claude` was not changed.
  - On the owner's machine the same checks, and the M01 lock surface check, fail closed if any Claude Code plugin
    adds tools.

## 20. F14 Windows suspended start (GPT_REVIEW_V1 at `b869e79`)

**Finding.** The owner's Windows offline run at `eec1680` failed twice with the same start refusal: "a NotebookLM
MCP server process is outside its containment".
- The client assigned the job object only after `subprocess.Popen` had returned.
- A launcher that starts its interpreter as a child at once could create that child before the assignment, so the
  child was outside the job. Two such launchers are the venv `python.exe` and the real `uvx.exe`.
- The refusal was fail closed, but startup on Windows was nondeterministic.
- The review also found a second gap: when `_win_job_assign` failed, the containment was `none` and `escaped()`
  returned `None`. An uncontained server could then be marked ready.

**Fix.** Only in the Windows F14 process start and its containment. Lookup, verify, status, citations, retry
policy, scope and configs are unchanged.
- **Windows start sequence:**
  1. Create the server with `CREATE_SUSPENDED`.
  2. Assign the kill-on-close, no-breakaway job while no code of the server has run.
  3. Only then call `_ProcessTree.resume()`. It resumes every thread of the process, found through a Toolhelp32
     thread snapshot, then `OpenThread(THREAD_SUSPEND_RESUME)` and `ResumeThread`.
- **POSIX:** unchanged. The `start_new_session` process group exists before `exec`.
- **Refusal.** The client refuses the start with `BACKEND_UNAVAILABLE` (`details.containment`, `phase: startup`,
  `sent: false`) when:
  - the containment is `none` (job creation or assignment failed, or raised): `containment_unavailable`;
  - the resume fails: `resume_failed`.
- **What a refusal does:**
  - no stdin writer or reader is started;
  - no `initialize`, `tools/list` or business call is sent;
  - the root is terminated (still suspended on Windows), and the teardown is recorded with that reason;
  - each `spawned` entry records `resumed`.
- **Escape check.** `escaped()` is still checked after `tools/list`.
- **Stage-B runner P8.** If every server start of the timed-out phase or of the recovery was refused at the
  containment step, P8 is `BLOCKED`. It is `FAIL` instead if one of those teardowns failed or a process is still
  alive. Containment that cannot be established never gives PASS.

**Regressions:** `test_gateway_f13_f14.F14SuspendedStart`, and P8 in `F14RunnerEndToEnd`.
- **Cross-platform:**
  - `popen_kwargs` and the `resume` rules;
  - an uncontained start is refused before any request: no request, not ready, root dead, teardown
    `containment_unavailable`;
  - 12 repeated starts through the launcher chain, each with `escaped_processes == 0` and a verified close;
  - `test_containment_unavailable_is_blocked_not_pass` now goes through the refusal;
  - `test_tight_start_containment_unavailable_is_blocked` is new; the recovery-phase BLOCKED case is kept.
- **Windows only:**
  - The job assignment is delayed by 1.5 s. During the delay the root is alive but no wrapper child exists and the
    server has not logged `start`. The start is then accepted with containment `job` and
    `escaped_processes == 0`, and the close is verified.
  - Negative control: the same delay without suspension lets a child escape, and the start is refused.
  - An assignment failure terminates the suspended root before it runs: no request, no child, no server log.
  - A resume failure kills the contained root through the job: teardown `job`, tree empty, verified, no child.
- **Retained:** all F7–F14, strict four-tool, contract-v2 and model-visible negative controls.
- **Revert check:** with the previous `gateway/adapters/notebooklm.py`, 2 failures and 3 errors among the 32
  F13/F14 tests on Linux. These are:
  - `test_containment_unavailable_is_blocked_not_pass`
  - `test_uncontained_start_is_refused_before_any_request`
  - `test_popen_kwargs_and_resume_rules`
  - `test_repeated_starts_never_escape_and_always_close_verified`
  - `test_tight_start_containment_unavailable_is_blocked`

  The Windows-only tests run on the owner's machine.
- **Count.** The M02 suite has 176 tests (168 + 8). 8 are skipped off Windows: the 4 earlier junction/reparse
  controls and the 4 new suspended-start tests.

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
