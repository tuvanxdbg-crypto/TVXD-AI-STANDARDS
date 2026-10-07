# M02 stage B, step B2: Gateway semantic route against NotebookLM (owner machine ducdq, 2026-10-07)

Approved by the owner directly in the Claude chat (2026-10-07): "Tôi chấp thuận chạy B2 theo kế hoạch và code tại
commit 67874a3: Gateway gọi notebook_query tới notebook 8ca84143-c240-4fcb-98fe-e1f8c6cca02d, chỉ với 3 source đã
ánh xạ, các ca P5–P11, cùng preflight trước và sau." Plan and runner: `docs/M02_PILOT_PLAN.md` §6b and
`tests/m02/pilot_stage_b.py` at `67874a3` (GPT_REVIEW_V1 PASS).

How it ran:
- The owner ran the three commands of plan §6b in PowerShell on ducdq, non-elevated.
  - Repo at HEAD `67874a372672c99224c834957284bd643a22c651`; `git rev-parse HEAD` checked first.
  - Runtime: `uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z`.
- An earlier attempt in cmd.exe and a second one from the wrong working directory ran nothing: no preflight, no
  runner, no NotebookLM call.
- The runner wrote a temporary `mcp_stdio` copy of `docs/m02-pilot/gateway.pilot.stage-b.json`; the committed config
  stays `mode: disabled`. The Gateway started the M01 gated server from the project `.mcp.json`.
- No `AUTH_REQUIRED`, no login, no MFA. The implementer did not call NotebookLM.
- The owner pasted the console output and the three summary files into the chat. The `.raw.json` file stayed on the
  owner's machine and is not committed.

Files (copied from `tests\m02\evidence\local\` on ducdq):
- `preflight-before-20261007-092720.summary.json`: PASS. Token not elevated (Limited, Medium), no ACL-bypass
  privileges, read-only rights on `C:\`, `Vanban_XDCB` and the three files, hashes equal the INDEX.
- `stage-b-20261007-092728.summary.json`: **FAIL** (stopped after P8).
- `preflight-after-20261007-093001.summary.json`: PASS. Same rights; hashes unchanged.

## Results

| Case | Result | Observed |
|---|---|---|
| P5 | PASS | One `notebook_query`, exactly the 3 mapped ids; Gateway `ERROR CITED_SOURCE_NOT_WHITELISTED` |
| P10 | PASS, reported as P10-B | First and repeat lookups both discarded (no answer, no evidence, not cached, 0 VERIFIED). See finding F13: the "out of scope" trigger was the citation shape, not an out-of-scope id |
| P6 | NOT_OBSERVED | P5 had no FOUND result |
| P7 | NOT_OBSERVED | Lookup half met: UNKNOWN, all three `NOTEBOOK_NOT_WHITELISTED`, 0 backend calls. Verify half did not occur: no NotebookLM evidence from P5 |
| P11 | NOT_OBSERVED | The response was discarded, so no TCVN 8794 result to check |
| P8 | **FAIL** | 1 s budget gave a structured `TIMEOUT` (1031 ms); `process_retired: false`; the recovery lookup completed (attempt 5 `returned`). See finding F14 |
| P9 | not run | Separate command; not part of this run |

Audit (`notebook_query_attempts`):
- 5 attempts, all `sent_to_backend: true`. Each sent exactly
  `8b75af2d-…`, `8ccb8115-…` and `d54bb084-…`.
- `injection_source_requested: false`, `attempts_with_wrong_source_set: []`, `unfinished_attempts: []`,
  `source_gate: null`.
- Attempts 1, 2, 3 and 5 `returned` with `status: success`. The result keys were `answer`, `citations`,
  `conversation_id`, `question`, `references`, `sources_used` and `status`.
  - `citations_container: dict`, `citation_item_keys: []`, 6–7 citations, `cited_source_ids: []`.
  - `sources_used: [8ccb8115-…]`, i.e. TCVN 8794 only, `out_of_scope_source_ids: []`.
  - `unattributed_citation: true`; answers of 2770–3152 characters were discarded.
- Attempt 4 (P8, 1 s budget): `exception_after_caller_timeout`, `TIMEOUT`, worker finished at 3077 ms.

## Findings

**F13: the real `notebook_query` citation shape is not parsed, so every live answer is discarded (fail closed).**
- In `notebooklm-mcp-cli==0.15.1`, `citations` is a dict that maps a citation number to a source id **string**, for
  example `{"1": "<source id>"}`. `references` is a list of `{source_id, citation_number, cited_text}`, and
  `sources_used` is the list of unique values of `citations`.
  - Sources: wheel `notebooklm_mcp_cli-0.15.1-py3-none-any.whl`, sha256
    `4bfd21d83b0636210d72a1678f82b7f4b8d33c90b6504718c694a6b46c14d57f`.
  - `core/conversation.py` lines 385–388 (docstring) and 989–1050 (`_extract_citation_data`).
  - `services/chat.py` lines 285–292, and `mcp/tools/chat.py` line 59 (`{"status": "success", **result}`).
  - The package was downloaded and read only, never run.
- `gateway/adapters/notebooklm.py` `_parse_citations` accepts only dict items with a `source_id` key. Each string
  value counts as an unattributed citation, so F12 discards the whole response.
- Consequences:
  - The Gateway stayed safe: no answer, no evidence, nothing VERIFIED, nothing cached.
  - The semantic route can never return FOUND against the real server, so P6, P7 (verify half) and P11 could not be
    observed.
  - The runner's own `Recorder` used the same rule, so it classified P10 as P10-B.
- Real scope of the answers:
  - In 0.15.1, `sources_used` is built from the values of `citations`.
  - All five responses had `sources_used` = TCVN 8794 only.
  - So by the package code, every citation pointed at a mapped, in-scope source, and no out-of-scope id was observed
    (in substance P10-A).
  - Caveat: the runner did not record the citation values themselves; this conclusion rests on `sources_used` and
    the package code.
- Offline reproduction: `tests/m02/evidence/sandbox-linux-2026-10-07-b2-analysis/`.

**F14: the P8 `process_retired` check samples the client before the abandoned worker has torn it down.**
- The runner reads `client8._proc` as soon as the tool call returns `TIMEOUT` (1031 ms).
- The timed-out attempt's worker kept running until 3077 ms (`exception_after_caller_timeout`).
- In `McpStdioNotebookLMClient`, every exit path of a failed start or a timed-out in-flight call terminates the
  process and sets `_ready = False`, so the next call starts and validates a fresh server. The recovery call did
  complete.
- But the check ran before that teardown, so `false` is the state at sampling time, not proof of a leak.
- On Linux the same scenario (fake server, 2.5 s startup, 1 s budget) shows the process already gone at sampling
  time, so the race did not reproduce there. On Windows it did.
- Open points for the fix:
  - P8 should check after the timed-out attempt reached its terminal outcome.
  - On Windows, `proc.kill()` ends `uvx.exe`; whether the `notebooklm-mcp` child process also ends is not verified
    by this run.
  - `sent_to_backend: true` for attempt 4 comes from a `request_id` on the TIMEOUT. That id may belong to the
    `initialize` request, so whether `notebook_query` itself reached the server is not known. The count is
    conservative.

Metadata only: ids, statuses, codes, counts, key names and timings. No answer text, passages, raw payloads or
transcripts.
