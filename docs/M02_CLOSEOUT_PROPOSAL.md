# M02 — Closeout proposal (DRAFT for GPT review; M02 is NOT closed and NOT merged)

**Status: PROPOSAL.** This document proposes how to close M02. It changes no code, config, INDEX, pin, policy or
permission.

Closing M02 needs three things in order:
1. a GPT_REVIEW_V1 PASS of this proposal at its exact SHA;
2. the owner's direct decision in the Claude chat;
3. a merge that the owner performs, or explicitly authorizes for that exact SHA.

Claude does not close M02, mark the PR ready, or merge.

## 1. Authority

- GPT_REVIEW_V1 PASS at `eb235d4aa89c52b6c6fe9f602408716499afdfef` (the live B2v2 result) set NEXT_ALLOWED_STEP
  `OWNER_DECIDE_M02_CLOSEOUT_DRAFT_OR_FURTHER_BOUNDED_LIVE_COVERAGE_ONLY`.
- The owner chose option 1 in the Claude chat on 2026-10-09: "Soạn đề xuất đóng M02". The option read: "Chấp nhận
  kết quả Q-S1. Tôi chỉ soạn đề xuất đóng M02 (closeout/status): đã làm gì, giới hạn còn lại, điều kiện merge. Đề
  xuất commit mới và gửi GPT review riêng. Chưa merge, không chạy live thêm."
- That choice authorizes this draft only. It is not approval to merge, to run anything live, or to start M03.

## 2. Proposed M02 status

`M02_STATUS: CLOSEOUT_PROPOSED`. The basis:
- **OFFLINE_VALIDATED (contract v2):** on Linux, and on the owner's Windows machine at `f9c1061`.
- **LIVE_STAGE_B_V2_PASS:** a bounded live run at `6eb2aed` on 1 notebook, 3 sources and query Q-S1, reviewed PASS
  at `eb235d4`.

Proposed closing statement, if the review and the owner accept it:

> **M02 CLOSED (bounded).** The Standards Gateway contract v2 is implemented, tested offline on Linux and Windows,
> and passed one bounded live stage B against NotebookLM. It covered the three owner-confirmed sources in notebook
> `8ca84143-…` with query Q-S1, under the owner policy `M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE`.
>
> This closes the M02 implementation milestone. It is not a statement that any standard is applicable, legally
> valid or correctly answered. It does not enable the Gateway for ordinary sessions.

## 3. What M02 delivered

- **Gateway (`gateway/`).**
  - MCP stdio server with exactly three tools: `standards_lookup`, `standards_verify`, `standards_status`.
  - Contract v2 (design doc §0): NotebookLM is the primary source, limited to the INDEX notebook/source scope.
  - Evidence `tvxd.gateway.evidence/v2` with `TRUSTED_BY_POLICY` / `NOT_APPLICABLE` / `UNKNOWN`, and a `TRUST` block
    that lists the checks performed and the checks not performed.
  - Strict citation checking: out-of-scope, missing, malformed or contradictory entries discard the whole answer
    (F12/F13).
  - Verify v2, including `ISSUED_BY_GATEWAY`.
  - A cache bound to contract, policy, scope and INDEX, with a TTL.
  - Bounded deadlines and retries (F7–F10).
  - Process containment with verified teardown (F14), including the Windows suspended start (§20).
- **NotebookLM access.** Only through the M01 gated server: `notebooklm-mcp-cli==0.15.1`, four read tools, pin
  unchanged. The client refuses any other tool surface. Every committed config stays `notebooklm.mode: disabled`;
  `mcp_stdio` is only ever enabled in a temporary copy.
- **Model-visible isolation.** Claude Code locked to the three Gateway tools. The injected-data gate (`m02_surface.py
  llm`) requires exactly one `standards_lookup`, no other tool attempt, and embedded instructions detected but not
  followed.
- **Pilot tooling.**
  - Stage B runner with a sealed audit and a per-attempt source gate.
  - Contract-v2 preflight that never touches the local library.
  - Synthetic stand-ins and fake backends for offline dry runs.
- **Tests.** 185 offline unit, contract and regression tests, 8 of them Windows-only, plus the real Claude Code
  `surface`/`llm` checks.
- **Docs.** `docs/M02_STANDARDS_GATEWAY.md` (§0 contract v2, §18 migration, §19–§20), `docs/M02_PILOT_PLAN.md` (§6c
  stage B v2), the CLAUDE.md M02 section, the README.

## 4. Acceptance against Issue #4 §6 (as amended by OWNER_ARCHITECTURE_CHANGE_V1)

| Issue #4 §6 item | Status | Evidence |
|---|---|---|
| Public `tools/list` exactly three; raw NotebookLM/mutation tools not exposed | Met | `McpSurface`; real Claude Code `surface` on Linux and the owner's Windows (`windows-ducdq-2026-10-09-f14`, `-b2v2`) |
| Exact local lookup makes 0 NotebookLM calls | **Superseded** by contract v2: a known document/clause also goes to NotebookLM (§18) | §18 migration table |
| Semantic lookup only within the whitelist | Met, offline and live | F12/F13 regressions; B2v2: every attempt sent exactly the 3 mapped ids; injection source never sent |
| Wrong/absent mapping, unknown applicability/version, drift → no verified evidence | Met in v2 form: no `VERIFIED` status; mapping/hash/sync **superseded** by owner policy and reported as not checked | §18; P7 (`NOTEBOOK_SCOPE` FAIL), P11 live |
| Cache invalidation; the cache never bypasses checks | Met in v2 form (contract/policy/scope/INDEX bound, TTL) | `Cache.*`; P6 live |
| Embedded instructions cause no action, file or policy change | Met | `DataBoundary`, `test_gateway_surface_harness`, `ToolTraceGate`; real Claude Code `llm` 14/14 on Linux and Windows |
| Source root unchanged; traversal/escape refused | Met offline. Contract v2 reads no local file, so it is not exercised live | `LocalSourceAdapter` controls, Windows junction/reparse controls |
| Timeout, retry exhaustion, unavailable backend, missing input → structured | Met, offline and live | `test_gateway_resilience`, F7–F10, F14; P8 live |
| Windows Unicode and published formats work or fail structurally | Met offline (local adapter); not used by contract v2 | `LocalAdapter.*`, Windows suite |
| Model-visible isolation with evidence, mock vs real distinguished | Met | `m02_surface.py` records `kind`; evidence folders name mock / stand-in / real Claude Code / live |
| Related M01 regression and secret scan PASS | Met | every evidence round, latest at `6eb2aed` on Windows (323 files) |
| No OFFLINE_PASS reported as M02 overall PASS | Kept | every report; this proposal is the first that asks for closure |

## 5. Evidence index (contract v2, current)

| Folder | Commit | What | Result |
|---|---|---|---|
| `sandbox-linux-2026-10-09-contract-v2` | `68f924b` | contract v2 offline suite, fake and stand-in stage B | PASS |
| `sandbox-linux-2026-10-08-contract-v2-surface` | `d026ec3` | model-visible data boundary through the fake NotebookLM | PASS |
| `sandbox-linux-2026-10-08-contract-v2-tooltrace` | `fa1ab74` | no-extra-tool-attempt gate | PASS |
| `windows-ducdq-2026-10-09-contract-v2` | `eec1680` | owner Windows offline acceptance | FAILED (containment race, fixed) |
| `sandbox-linux-2026-10-09-f14-suspended-start` | `981f15d` | F14 Windows suspended start, Linux | PASS |
| `windows-ducdq-2026-10-09-f14` | `f9c1061` | owner Windows offline acceptance | PASS |
| `sandbox-linux-2026-10-09-stage-b-v2-plan` | `d007e4e` | stage B v2 plan, preflight, offline | PASS |
| `windows-ducdq-2026-10-09-b2v2` | `6eb2aed` | **live stage B v2** (owner-approved, owner-run) | **PASS** |

The other evidence folders certify contract v1 at their own commits and are history:
- stage A;
- B0;
- B2 at `67874a3`, which FAILed at P8;
- the F11–F14 rounds.

## 6. What the bounded live PASS does not show

- **Content.** It says nothing about the correctness of NotebookLM answers, their legal validity, applicability to
  a real project, or design compliance. No answer text was committed or reviewed.
- **Coverage.**
  - Only Q-S1 was asked, and every response cited only TCVN 8794. LUAT-135-2025-QH15 and TCVN-5575-2024 were in
    scope but not cited.
  - There is no clause-level evidence: `CLAUSE` is always null, because the 0.15.1 citations carry no structured
    clause id.
  - No other notebook, source, query set or work code was exercised.
- **Live branches not triggered.** The F12 negative branch did not occur live (P10-A, out of scope not observed);
  it rests on offline regressions.
- **Identity.** Source identity (hash, sync, local mapping) is not checked. That is intended under the owner policy,
  and every evidence item says so.

## 7. Open items carried past M02 (not blockers for this closeout, per proposal)

1. Further bounded live coverage: LUAT-135, TCVN-5575, and clause-level behaviour. Each needs its own reviewed plan
   and the owner's approval of an exact SHA.
2. No local fallback when NotebookLM is unavailable. This is an owner decision; today the Gateway returns
   `BACKEND_UNAVAILABLE`.
3. `CLAUSE` stays null until NotebookLM provides structured clause metadata, or a reviewed design adds it without
   inventing values.
4. Environment risk: Claude Code plugins that add MCP tools make the surface checks fail closed. None were present on
   the owner's machine, but the account-synced cloud sandbox had them.
5. Contract-v1 local tooling stays as history: stage A, `pilot_preflight.py`, `LocalSourceAdapter`. It is not used by
   the contract-v2 Gateway.
6. Operational enablement is out of M02 and needs separate authorization. This covers:
   - adding the Gateway to the project `.mcp.json`;
   - a committed `mcp_stdio` config;
   - any wider source set or notebook.

   M03 (governance), M04/M05/M06 (AutoCAD) are not started.

## 8. Proposed merge conditions (for the owner and the reviewer to decide)

1. GPT_REVIEW_V1 PASS of this proposal at its exact SHA.
2. The owner's direct decision in the Claude chat to close M02 and merge PR #5, naming the exact head SHA.
3. The PR moves from draft to ready, and is merged into `main`. The owner does this, or explicitly authorizes it for
   that SHA. Claude does not merge on its own.
4. After the merge, a status-only follow-up on a new branch and PR:
   - the CLAUDE.md "Current milestone" text set to "M02 closed (bounded), see docs/M02_CLOSEOUT_PROPOSAL.md";
   - the README M02 status line.

   It changes no rule or permission.
5. Unchanged by closing: every M01 rule; the M02 rules on tool isolation, the three tools, committed `mode:
   disabled`, untrusted content, and no PDFs or raw transcripts in git.

## 9. Not authorized by this proposal

Merge, marking the PR ready, any live run, login, any change to sources, notebook, scope, mapping, configs, pin,
ACL, credentials or permissions, M03, and AutoCAD.
