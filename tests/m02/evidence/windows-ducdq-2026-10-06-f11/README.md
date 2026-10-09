# M02 F11 patch: stage-A re-run on the real pilot files (owner machine ducdq, 2026-10-06)

M02_PATCH_AMBIGUOUS_CLAUSE_RESOLUTION_ONLY (GPT_REVIEW_V1 at `fb14c65`): the stage-A local pilot re-run at the F11
commit `09c1b7876910e078e8ee96a7c5c6b5b77038dc80`.
- Local only, `notebooklm.mode: disabled`, no NotebookLM call; only the three owner-named files in `C:\Vanban_XDCB`.
- The owner typed the approval directly in the executing session `session_01NrPmcpAcZqTnpiKPKYa6Sw` (bridge
  environment, non-elevated). That session listed no folder, edited no tracked file, and did not commit, push or post.
- It printed the summary files below, with `section_ids` lists replaced by their length and the JSON line-joined.
  The implementer copied them here. The `.raw.json` files stay git-ignored on that machine and were never printed.

Environment: Windows 10 (10.0.19045), Python 3.11.16 (uv), PyYAML 6.0.2, Claude Code 2.1.281.

| File | What | Result |
|---|---|---|
| `preflight-before-20261006-070135.summary.json` | token, AccessCheck `0x1200a9` on `C:\`/root/files, 1 hard link, hashes = INDEX | PASS |
| `stage-a-discover-20261006-070140.summary.json` | outline counts; duplicate section IDs (findings: law 2, TCVN 5575 72, TCVN 8794 20); Q-S1 | PASS 6/6 |
| `stage-a-run-20261006-070149.summary.json` | P1–P4 plus `PA-ambiguous-<doc>` | PASS 19/19 |
| `m02-surface-20261006-140209.json` | P9: exactly the 3 Gateway tools, 1 server, no NotebookLM tool (file name in local time; `utc` 07:02:03Z) | PASS |
| `preflight-after-20261006-070214.summary.json` | same checks after the run; hashes unchanged | PASS |

F11 on the real files:
- Every `PA-ambiguous-*` case returns `ERROR CLAUSE_AMBIGUOUS`, no results, 0 NotebookLM calls, with the right count:
  - law "Điều 93 khoản 1 điểm a": 2 occurrences;
  - TCVN 5575 "1": 9 occurrences;
  - TCVN 8794 "1": 2 occurrences.
- Before the patch, the TCVN 8794 and law lookups returned the first occurrence as `VERIFIED`; see
  `../windows-ducdq-2026-10-06-stage-a/`.
- Keyword candidates with a repeated ID (TCVN 5575 "1", twice in P3) now carry `CLAUSE_AMBIGUOUS` and stay `UNKNOWN`.
- P1 clauses "Điều 1" and "6.2.1" are unique and still `VERIFIED`.

No credentials, document text, excerpts, answers, SIDs, SDDL or transcripts here.
