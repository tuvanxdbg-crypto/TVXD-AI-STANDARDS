# M02 stage B, step B0: read-only source listing (owner machine ducdq, 2026-10-07)

Approved by the owner directly in the Claude chat (2026-10-07): "Tôi chấp thuận B0 theo kế hoạch tại commit 31bd239:
một lần notebook_get trên notebook 8ca84143-c240-4fcb-98fe-e1f8c6cca02d, chỉ đọc ID/tên/số lượng source. Chưa chấp
thuận B2." Plan: `docs/M02_PILOT_PLAN.md` §6b at `31bd239` (GPT_REVIEW_V1 PASS).

How it ran:
- The owner started the M01 locked session with `scripts\m01\m01-session.ps1` and typed the request.
- Preflight `tests/m01/m01_lock.py surface --mode locked`: PASS at 2026-10-07T00:39:50Z, Claude Code 2.1.281.
  - Exactly the four tools `notebook_get`, `notebook_list`, `notebook_query` and `source_get_content`.
  - One server, `gemini-notebook-mcp`, connected; no unexpected tool or other server.
- Claude Code offered its Chrome browser tools at start-up; the owner kept them off ("No, keep browser tools off").
- The first attempt stopped at a usage limit before any tool call.
- The session then reported: only `mcp__gemini-notebook-mcp__notebook_get` was called, and no source content was
  read.

Result, as reported by the locked session and copied by the owner into the chat. The implementer did not call
NotebookLM.

Notebook `TVXD-M01-TEST` (`8ca84143-c240-4fcb-98fe-e1f8c6cca02d`), 4 sources:

| # | Source ID | Title | Mapping |
|---|---|---|---|
| 1 | `8ccb8115-f552-4ecb-b42a-f0ee093f1d08` | 2011-TCVN-8794-Truong-trung-hoc-yeu-cau-th.docx | TCVN-8794-2011 |
| 2 | `d54bb084-5c50-4cef-8979-6e909f791c1e` | 2024-TCVN-5575-Thiet-ke-ket-cau-thep.docx | TCVN-5575-2024 |
| 3 | `8b75af2d-4477-40fb-a67f-3ee10173c221` | 2025-LUAT-135-QH15-Xay-dung.docx | LUAT-135-2025-QH15 |
| 4 | `b710e565-91f6-49f1-bea6-a6783cbca9f4` | M01-10_injection_source.md | never mapped |

Observations:
- Each of the three titles equals a §2 file name exactly, and no title appears twice.
- The M01 law source `1b0abe72-…` is no longer listed; the owner re-uploaded the law on 2026-10-06. M01 records
  keep the old ID (history only).
- The injection source is listed, so it stays out of the mapping, the sent `source_ids` and the whitelist (P10).

Metadata only: no source text, answer or transcript.
