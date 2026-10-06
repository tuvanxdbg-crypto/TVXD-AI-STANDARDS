# M02 bounded pilot, stage A (owner machine ducdq, 2026-10-06)

M02_STAGE_A_PREFLIGHT_AND_OWNER_APPROVAL (GPT_REVIEW_V1 at `a4b630b`, plan `docs/M02_PILOT_PLAN.md` §6a).
Local only: `notebooklm.mode: disabled`, no NotebookLM call, only the three owner-named files in `C:\Vanban_XDCB`.

Owner authorization:
- OWNER_AUTHORIZATION_V1 on PR #5;
- the owner's direct approval in the Claude chat;
- for steps 1–5, a direct approval typed by the owner in the executing session itself.

P1 clauses were confirmed by the owner: the law "Điều 1" and TCVN 8794 "6.2.1". No TCVN 5575 clause was given.

Two Claude Code sessions ran on the owner's Windows machine (bridge environment, non-elevated):
- `session_01JxLr4fuxwuBTFKQpLYVxQc`: preflight and discover, at `3b33efc`.
- `session_01BThLKLTPYGHDRKo8wRcxnC`: preflight before, P1–P4, P9 and preflight after, at `43f9ef4`.

Neither session listed the folder, edited a tracked file, committed, pushed or posted. They printed the summary files
below; the implementer copied them here, so JSON whitespace may differ. The `.raw.json` files hold excerpts, SIDs and
SDDL; they stay git-ignored in `tests\m02\evidence\local\` on that machine and were never printed. In the discover
summary each `section_ids` list was replaced by its length before printing.

Environment: Windows 10 (10.0.19045), Python 3.11.16 (uv), PyYAML 6.0.2, Claude Code 2.1.281. Gateway code is
`746fac2`; the scripts are `tests/m02/pilot_preflight.py`, `pilot_stage_a.py` and `m02_surface.py`.

| File | What | Result |
|---|---|---|
| `preflight-before-20261006-035517.summary.json` | preflight before discover (`3b33efc`) | PASS |
| `stage-a-discover-20261006-035523.summary.json` | outline counts, Q-S1 by document (CANDIDATES) and without document (UNKNOWN, all MAPPING_MISSING) | PASS, 6/6 |
| `preflight-before-20261006-063633.summary.json` | preflight right before the run (`43f9ef4`) | PASS |
| `stage-a-run-20261006-063644.summary.json` | P1–P4, SOURCE-UNCHANGED, plus findings (ambiguous clause IDs) | PASS, 16/16 |
| `m02-surface-20261006-133702.json` | P9: Claude Code locked to the pilot Gateway sees exactly the 3 tools, 1 server, no NotebookLM tools | PASS |
| `preflight-after-20261006-063711.summary.json` | preflight right after; same hashes as before and as INDEX | PASS |

The surface file name uses local time; the `utc` field inside is 06:36:56Z.

Preflight details:
- The token is non-elevated (Limited), Medium integrity, and holds no ACL-bypass privilege.
- AccessCheck grants `0x1200a9` (read/execute/read-attributes/read-control only) on `C:\`, the root and each file.
- Each file has 1 hard link and no reparse or placeholder attribute.
- Each SHA-256 equals the INDEX value, before and after.

Finding (open, not patched during the pilot): section IDs are not unique in the real documents.
- Causes: table-of-contents entries and numbered table rows or list items parse as sections.
- The Gateway returns the first section with a matching ID, so an ambiguous reference can return a table-of-contents
  line as `VERIFIED`. Recorded probes:
  - TCVN 8794 "1": lines 7 and 36; lookup returned line 7, `VERIFIED`.
  - Law "Điều 93 khoản 1 điểm a": lines 880 and 882; returned line 880, `VERIFIED`.
  - TCVN 5575 "1": 9 occurrences; returned line 9, `UNKNOWN` (condition).
- P1 accepted only clause IDs that occur exactly once.

No credentials, document text, excerpts, answers or transcripts here.
