# Kế hoạch M04-B: chạy bộ kiểm chỉ đọc trên một bản vẽ thật

Trạng thái: **bản nháp, chờ REVIEW_V1 và chủ repo phê duyệt**. Kế hoạch này chưa cho phép chạy bất cứ thứ gì.

## 1. Căn cứ

- Spec `docs/M04_CAD_AUDIT_READONLY.md` (duyệt tại `a031fc2`):
  - §6: M04-B cần kế hoạch riêng, ít nhất một quy tắc APPROVED bên CHUAN-HOA-CAD, quyết định dữ liệu thật nào được đưa vào repo (mặc định chỉ báo cáo đã lọc), REVIEW_V1 và chủ repo phê duyệt;
  - §7: mốc M04-B, và cách đóng M04 có giới hạn sau M04-A và M04-B.
- `CLAUDE.md`, mục "M04 rules": các giới hạn vẫn có hiệu lực.
- M04-A đã được chủ repo nghiệm thu tại `c486c8e` (PR #18, merge `a2a3557`).
- Bên CHUAN-HOA-CAD:
  - **HAP-M04B-RULES-01:** `approved/check_rules.approved.yaml` có hai quy tắc APPROVED, `CHC-XREF-RESOLVED` và `CHC-LAYER-V2` (PR #66, merge `0b3c5c5`). Hai giới hạn đi kèm:
    - Q1a: với `VB-XREFS` hiện có, quy tắc xref chỉ cho PASS hoặc UNKNOWN;
    - Q2: ban đầu chỉ áp cho bản vẽ dựng từ mẫu V2.
  - Q3: layer đọc bằng LibreDWG, xref lấy từ `VB-XREFS`.
  - Q4: chỉ báo cáo `cadaudit` đã lọc được đưa sang TVXD.
  - Đề nghị phạm vi bộ xuất CAD_READ v1 pha 1 (chỉ fixture) đang chờ review: CHUAN-HOA-CAD PR #68.

## 2. Mục tiêu

Chạy `cadaudit` của repo này, không sửa mã, trên **một** bản trích xuất CAD_READ v1 thật, với tệp quy tắc đã duyệt. Bản trích xuất do bộ xuất của CHUAN-HOA-CAD tạo ra từ **một** bản vẽ được chọn.

Mục tiêu là chứng minh cả chuỗi chạy đúng trên dữ liệu thật: trích xuất, kiểm, báo cáo, truy vết. Chuỗi phải không sửa bản vẽ và không đưa dữ liệu thật ngoài phạm vi vào repo.

M04-B **không** nhằm kết luận bản vẽ đạt tiêu chuẩn. Nó cũng không nhằm kết luận bản vẽ đúng quy ước công ty, ngoài đúng hai quy tắc đã duyệt.

## 3. Điều kiện trước khi chạy

| # | Điều kiện | Ở đâu | Hiện trạng |
|---|---|---|---|
| G1 | Có ít nhất một quy tắc kiểm APPROVED | CHUAN-HOA-CAD | Đạt: HAP-M04B-RULES-01, `0b3c5c5` |
| G2 | Bộ xuất CAD_READ v1 pha 1 được viết, kiểm trên fixture và nghiệm thu | CHUAN-HOA-CAD | Chưa: đề nghị phạm vi ở PR #68 |
| G3 | Gói duyệt cho lần đọc thật, theo kiểu L01: | CHUAN-HOA-CAD | Chưa |
| | • SHA-256 của bản vẽ được duyệt trước; | | |
| | • đọc trên bản sao; | | |
| | • chạy `dwgread` và `l01_readonly.py`; | | |
| | • tệp nguồn không đổi sau khi đọc | | |
| G4 | Chọn bản vẽ (Q5) có căn cứ thuộc phạm vi mẫu V2 (Q2), và chốt dữ liệu nào được đưa vào repo này | chủ repo | Chưa |
| G5 | Kế hoạch này có REVIEW_V1 và được chủ repo phê duyệt | repo này | Chưa |
| G6 | `cadaudit` dùng nguyên bản tại một SHA ghim (đề xuất `9f11076`). Nếu phải sửa mã thì làm PR riêng, review riêng, trước khi chạy | repo này | Không cần sửa theo hiểu biết hiện tại |

Chỉ chạy khi G1–G6 đều đạt.

## 4. Luồng chạy dự kiến

1. **Trích xuất** (bên CHUAN-HOA-CAD, trên máy người dùng, theo gói G3).
   - Bộ xuất tạo một tệp CAD_READ v1 từ đầu ra của `dwgread` và `VB-XREFS`.
   - Tệp này ở lại máy người dùng, không commit vào repo nào.
2. **Kiểm** (trên máy người dùng).
   - Chạy `python -m cadaudit check --input <tệp CAD_READ> --rules <approved/check_rules.approved.yaml> --out <tệp báo cáo mới>`.
   - Dùng bản checkout của repo này ở SHA ghim, và tệp quy tắc ở commit `0b3c5c5` của CHUAN-HOA-CAD, kiểm sha256.
   - Bộ ghi của `cadaudit` chỉ tạo tệp mới (D6).
3. **Lọc và đưa evidence vào repo này**, theo quyết định B1 (mục 8).
   - Mặc định chỉ có bản tóm tắt; báo cáo đầy đủ ở lại máy người dùng.
4. **Nghiệm thu:** CLAUDE_EXECUTION_REPORT, REVIEW_V1 tại HEAD, chủ repo nghiệm thu.

Các bước 1 và 2 chạy trên máy người dùng. Môi trường cloud không nhận bản trích xuất thật.

## 5. Evidence yêu cầu

- `RUN_MANIFEST` bên CHUAN-HOA-CAD cho lần trích xuất. Gồm:
  - sha256 của tệp nguồn trước và sau khi đọc;
  - phiên bản LibreDWG;
  - run `VB-XREFS`;
  - sha256 của tệp CAD_READ tạo ra.
- Trong repo này, tại `tests/m04/evidence_b/` (tên chốt ở B5):
  - **Bản tóm tắt** gồm:
    - sha256 của tệp CAD_READ, của tệp quy tắc và của báo cáo đầy đủ;
    - SHA `cadaudit`;
    - `overall`, `all_rules_approved`;
    - kết luận, lý do và số đếm theo từng quy tắc;
    - coverage của `layers` và `xrefs`.
  - Báo cáo `cadaudit` đầy đủ chỉ được đưa vào nếu B1 chọn như vậy.
- Lệnh đã chạy và output dòng lệnh, đã bỏ đường dẫn máy.

## 6. Nghiệm thu

| Mốc | Mục tiêu | Evidence yêu cầu | Điều kiện đạt | Người duyệt |
|---|---|---|---|---|
| M04-B | Chuỗi trích xuất → kiểm → báo cáo chạy đúng trên một bản vẽ thật, không sửa bản vẽ | Mục 5 | Xem bảng điều kiện đạt bên dưới | REVIEW_V1 tại HEAD, chủ repo |

Điều kiện đạt của M04-B:

| # | Điều kiện |
|---|---|
| 1 | G1–G6 đạt trước khi chạy |
| 2 | sha256 tệp nguồn không đổi trước và sau trích xuất |
| 3 | `cadaudit` chạy thành công, báo cáo hợp schema `cad_audit_report.v1` |
| 4 | sha256 của tệp quy tắc trong báo cáo trùng với `approved/check_rules.approved.yaml` tại `0b3c5c5` |
| 5 | `CHC-XREF-RESOLVED` cho PASS hoặc UNKNOWN. Nếu ra FAIL thì đó là dấu hiệu lỗi ánh xạ, vì trái Q1a, và phải điều tra trước khi nghiệm thu |
| 6 | `CHC-LAYER-V2` cho kết luận bất kỳ, nhưng mọi kết quả truy được về đối tượng trong bản trích xuất qua evidence ID |
| 7 | Báo cáo không kết luận đạt tiêu chuẩn |
| 8 | Không có bản trích xuất đầy đủ hay đường dẫn máy nào bị commit |

## 7. Đóng M04 có giới hạn

Sau khi M04-B được nghiệm thu, một PR riêng ghi bản đóng M04, có REVIEW_V1. Bản đóng nêu rõ phần chưa làm:
- M04-C chưa làm, và mục `STANDARD_REQUIRED` vẫn là UNKNOWN `STANDARD_LOOKUP_NOT_ENABLED`;
- giới hạn Q1a của quy tắc xref;
- chỉ một bản vẽ.

Điều kiện thoát "retrieve evidence" của Issue #2 chỉ đạt một phần.

## 8. Các quyết định cần chủ repo chốt

| # | Câu hỏi | Đề xuất của LEAD |
|---|---|---|
| B1 | Đưa gì vào repo này: chỉ bản tóm tắt, hay cả báo cáo `cadaudit` đầy đủ (có tên layer, tên xref, sha256 tệp nguồn) | Chỉ bản tóm tắt; báo cáo đầy đủ ở lại máy người dùng |
| B2 | Số bản vẽ cho M04-B | Một bản vẽ dựng từ mẫu V2 |
| B3 | Bước kiểm chạy ở đâu | Trên máy người dùng (ducdq), không đưa bản trích xuất lên cloud |
| B4 | SHA ghim của `cadaudit` | `9f11076` (`main` hiện tại; `cadaudit/` không đổi từ `c486c8e`) |
| B5 | Thư mục evidence | `tests/m04/evidence_b/` |

## 9. Rủi ro và giới hạn đã biết

- Kết quả đọc bằng LibreDWG chưa được đối chiếu với AutoCAD.
- Coverage `layers` có thể INCOMPLETE, nếu không xác minh được số mục của bảng layer trong JSON của `dwgread` (CHUAN-HOA-CAD PR #68, mục 3.2).
- Quy tắc xref không phát hiện được xref thiếu tệp với nguồn hiện có (Q1a).
- Một bản vẽ không đại diện cho cả bộ hồ sơ.

## 10. Không thuộc M04-B

- Ghi hay sửa DWG; nâng A2.
- Sửa CHUAN-HOA-CAD từ repo này.
- Gọi Gateway hay NotebookLM.
- M04-C, M05, M06.
- Kết luận pháp lý hay đạt tiêu chuẩn.
- Thêm code mở DWG vào repo này.
