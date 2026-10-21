# Kế hoạch M04-B: chạy bộ kiểm chỉ đọc trên một bản vẽ thật

Trạng thái: **đã duyệt**. REVIEW_V1 PASS tại `00595f6` (review 5567822283), merge vào `main` tại `21eda0b` (PR #20). Chủ repo chốt B1–B5 ngày 2026-10-19 (mục 8). Kế hoạch vẫn chưa cho phép chạy: chỉ chạy khi G1–G7 đều đạt (mục 3).

Bản vá theo REVIEW_V1 `pullrequestreview-5566700969` (PATCH_REQUIRED tại `e690cd8`):
- F01: G2, G3, mục 1, mục 4 bước 1 và mục 5 ràng với hợp đồng bộ xuất đã duyệt;
- F02: mục 5.1 mới, G7, điều kiện 6, B1 và mục 9.

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
  - **Hợp đồng bộ xuất CAD_READ v1 pha 1:** đề nghị `runs/M04BEXSPEC-20261016-01/` tại `f19021b75404d96dc1b077c04a468f60f059beaa` (CHUAN-HOA-CAD PR #68).
    - GPT review PASS (`pullrequestreview-5562423230`).
    - Người dùng duyệt X1–X7 ngày 2026-10-19 (HAP-M04B-EXPORTER-P1-01, ghi nhận ở CHUAN-HOA-CAD PR #70).
    - Hợp đồng có bốn đầu vào: JSON `dwgread`, hồ sơ lần đọc `--dwgread-record` (`chc.dwgread_record/v1`), `l01_result.json` đầy đủ, và `--meta`.
    - Điều kiện chấp nhận a1–a8 và b1–b4 ở mục 2.1 của đề nghị.
    - Bộ xuất được viết sau đó ở run `M04BEX-20261019-01`; hiện trạng xem G2 (mục 3).

## 2. Mục tiêu

Chạy `cadaudit` của repo này, không sửa mã, trên **một** bản trích xuất CAD_READ v1 thật, với tệp quy tắc đã duyệt. Bản trích xuất do bộ xuất của CHUAN-HOA-CAD tạo ra từ **một** bản vẽ được chọn.

Mục tiêu là chứng minh cả chuỗi chạy đúng trên dữ liệu thật: trích xuất, kiểm, báo cáo, truy vết. Chuỗi phải không sửa bản vẽ và không đưa dữ liệu thật ngoài phạm vi vào repo.

M04-B **không** nhằm kết luận bản vẽ đạt tiêu chuẩn. Nó cũng không nhằm kết luận bản vẽ đúng quy ước công ty, ngoài đúng hai quy tắc đã duyệt.

## 3. Điều kiện trước khi chạy

| # | Điều kiện | Ở đâu | Hiện trạng |
|---|---|---|---|
| G1 | Có ít nhất một quy tắc kiểm APPROVED | CHUAN-HOA-CAD | Đạt: HAP-M04B-RULES-01, `0b3c5c5` |
| G2 | Bộ xuất CAD_READ v1 pha 1 được viết theo đúng hợp đồng bốn đầu vào đã duyệt tại `f19021b` (HAP-M04B-EXPORTER-P1-01), kiểm trên fixture, GPT review PASS và người dùng nghiệm thu **tại một SHA cụ thể**. Lần chạy thật dùng đúng SHA đó | CHUAN-HOA-CAD | Đạt: bộ xuất `M04BEX-20261019-01` tại `0223f8ee5f8d56cdd89d7c93347fd206c4b9bfa1` (`tools/cadread_export.py` sha256 `8de2ea099ff1fea1480ea06d0c369281fe17894ad2fc9fd58dd9d04cb48b551e`), GPT review PASS 5568559484 tại SHA đó, CHUAN-HOA-CAD PR #73 merge `3bc809e`. Chủ repo nghiệm thu trong chat ngày 2026-10-19 và xác nhận lại trực tiếp trên GitHub ngày 2026-10-21 ([bình luận 6305937402](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/pull/24#issuecomment-6305937402)), nguyên văn: "Tôi nghiệm thu bộ xuất CAD_READ pha 1 M04BEX-20261019-01 tại commit 0223f8ee5f8d56cdd89d7c93347fd206c4b9bfa1, giữ LAYER_CONTROL_T_VERIFIED = True." Biên bản `runs/M04BEXNT-20261019-01/` (PR #75, GPT review PASS 5573337156, merge `0ed4c5d`). Chỉ nghiệm thu trên fixture; lần chạy thật dùng đúng SHA này, sửa bộ xuất thì G2 mất hiệu lực |
| G3 | Gói duyệt cho lần đọc thật, theo kiểu L01, có review và phê duyệt riêng, gồm: | CHUAN-HOA-CAD | Chưa |
| | • SHA-256 của bản vẽ được duyệt trước; đọc trên bản sao; | | |
| | • **script đọc tạo hồ sơ `chc.dwgread_record/v1`**: đo hash bản sao trước, chạy `dwgread`, đo hash và kích thước byte của JSON, đo hash bản sao sau. Script được review và duyệt tại SHA cụ thể; | | |
| | • chạy `l01_readonly.py` (cầu COM đã nghiệm thu, không sửa); | | |
| | • bộ xuất tại SHA của G2 kiểm a1–a8 (hậu kiểm L01: `STATE` = `L0_L1_PASSED`, `POSTCHECK_ERRORS` rỗng, hash trước = sau, `SOURCE_UNCHANGED` và `WC_UNCHANGED` = `true`) và b1–b4 (JSON → hồ sơ → hash nguồn → `--meta` → L01). Sai một điều kiện thì không có bản trích xuất | | |
| G4 | Chọn bản vẽ (Q5) có căn cứ thuộc phạm vi mẫu V2 (Q2), và chốt dữ liệu nào được đưa vào repo này | chủ repo | Chưa |
| G5 | Kế hoạch này có REVIEW_V1 và được chủ repo phê duyệt | repo này | Đạt: REVIEW_V1 PASS tại `00595f6f681efe2494956d19a210d20b995e0ee9` (review 5567822283); chủ repo ra lệnh merge sau PASS ("merge #20", "Chờ PASS rồi merge") và PR #20 merge tại `21eda0bb84600a5aa2bf9d7a06af9c136925c14d`; chủ repo chốt B1–B5 ngày 2026-10-19 (mục 8). Đây là duyệt kế hoạch, không phải quyền chạy |
| G6 | `cadaudit` dùng nguyên bản tại một SHA ghim (đề xuất `9f11076`). Nếu phải sửa mã thì làm PR riêng, review riêng, trước khi chạy | repo này | Đạt: chủ repo chốt B4 = `9f11076` (mục 8); `cadaudit/` dùng nguyên bản, không cần sửa theo hiểu biết hiện tại. Nếu sau này phải sửa mã thì G6 mất hiệu lực cho tới khi có PR riêng được review |
| G7 | Có phép kiểm truy vết cục bộ (mục 5.1) đã được review và duyệt tại SHA cụ thể. Phép kiểm này dùng cách giải evidence ID độc lập với `cadaudit`, theo `resolve_evidence` trong `tests/m04/m04_helpers.py` | repo này, PR riêng có review | Đạt: `scripts/m04b/kiem_truy_vet.py` tại `af82d368066ade4a91e6750d08726fc04a7c7079` (sha256 `e8e6ec93549e134e799c8fcbbf24e8ff8014ce871b1e81b3e602afc6eef1ef8a`), PR #23, REVIEW_V1 PASS 5593897008 tại SHA đó. Chủ repo nghiệm thu trên GitHub ngày 2026-10-21 ([bình luận 6305938721](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/pull/24#issuecomment-6305938721)), nguyên văn: "Tôi nghiệm thu script kiểm truy vết G7 tại commit af82d368066ade4a91e6750d08726fc04a7c7079." Chỉ kiểm trên dữ liệu giả; lần chạy thật dùng đúng script này, sửa script thì G7 mất hiệu lực |

Chỉ chạy khi G1–G7 đều đạt.

Nếu hợp đồng bộ xuất đổi sau HAP-M04B-EXPORTER-P1-01, phải đối chiếu lại kế hoạch này và review lại trước khi chạy. Ví dụ: thêm hoặc bớt đầu vào, đổi điều kiện 2.1, đổi chính sách coverage.

## 4. Luồng chạy dự kiến

1. **Trích xuất** (bên CHUAN-HOA-CAD, trên máy người dùng, theo gói G3).
   - Script đọc đã duyệt tạo JSON `dwgread` và hồ sơ `chc.dwgread_record/v1`. `l01_readonly.py` tạo `l01_result.json`.
   - Bộ xuất tại SHA của G2 nhận bốn đầu vào, kiểm a1–a8 và b1–b4, rồi tạo một tệp CAD_READ v1.
   - Các tệp này ở lại máy người dùng, không commit vào repo nào.
2. **Kiểm** (trên máy người dùng).
   - Chạy `python -m cadaudit check --input <tệp CAD_READ> --rules <approved/check_rules.approved.yaml> --out <tệp báo cáo mới>`.
   - Dùng bản checkout của repo này ở SHA ghim, và tệp quy tắc ở commit `0b3c5c5` của CHUAN-HOA-CAD, kiểm sha256.
   - Bộ ghi của `cadaudit` chỉ tạo tệp mới (D6).
3. **Kiểm truy vết cục bộ** (trên máy người dùng, mục 5.1), trên đúng tệp CAD_READ, tệp quy tắc và báo cáo đã ghim hash.
4. **Lọc và đưa evidence vào repo này**, theo quyết định B1 (mục 8).
   - Mặc định có bản tóm tắt và output đã lọc của mục 5.1; báo cáo đầy đủ ở lại máy người dùng.
5. **Nghiệm thu:** CLAUDE_EXECUTION_REPORT, REVIEW_V1 tại HEAD, chủ repo nghiệm thu.

Các bước 1–3 chạy trên máy người dùng. Môi trường cloud không nhận bản trích xuất thật, JSON `dwgread` hay báo cáo đầy đủ.

## 5. Evidence yêu cầu

- `RUN_MANIFEST` bên CHUAN-HOA-CAD cho lần trích xuất. Gồm:
  - RUN_ID của lần đọc, của run L01, và SHA bộ xuất (G2) cùng SHA script đọc (G3) đã dùng;
  - sha256 của tệp nguồn trước và sau khi đọc;
  - phiên bản LibreDWG và mã thoát `dwgread`;
  - sha256 của JSON `dwgread`, của hồ sơ `chc.dwgread_record/v1`, của `l01_result.json`, của `--meta` và của tệp CAD_READ tạo ra;
  - kết quả từng điều kiện a1–a8 và b1–b4 do bộ xuất báo;
  - không ghi đường dẫn máy.
- Trong repo này, tại `tests/m04/evidence_b/` (tên chốt ở B5):
  - **Bản tóm tắt** gồm:
    - sha256 của tệp CAD_READ, của tệp quy tắc và của báo cáo đầy đủ;
    - SHA `cadaudit`;
    - `overall`, `all_rules_approved`;
    - kết luận, lý do và số đếm theo từng quy tắc;
    - coverage của `layers` và `xrefs`.
  - **Output đã lọc của phép kiểm truy vết** (mục 5.1).
  - Báo cáo `cadaudit` đầy đủ chỉ được đưa vào nếu B1 chọn như vậy.
- Lệnh đã chạy và output dòng lệnh, đã bỏ đường dẫn máy.

### 5.1 Kiểm truy vết cục bộ

Hash và hợp schema không thay cho kiểm truy vết. Phép kiểm này chạy trên máy người dùng, ngay sau bước kiểm. Đầu vào là đúng ba tệp đã ghim sha256 ở mục 5: tệp CAD_READ, tệp quy tắc, báo cáo. Script kiểm đã được duyệt theo G7.

Phép kiểm làm các việc sau:
1. Kiểm sha256 của ba tệp trùng giá trị ghi trong evidence; sai thì dừng.
2. Kiểm báo cáo hợp schema `cad_audit_report.v1`.
3. Với **mọi** evidence ID trong báo cáo, cả ở cấp quy tắc (`rules[].evidence_ids`) lẫn ở từng dòng kết quả layer và xref (`results[].evidence_ids`), kể cả ID cấp `FILE` như `coverage.layers.status`:
   - đúng dạng `CADEV:<file_id>:<handle|FILE>:<trường>`, và `file_id` trùng `drawing.file_id`;
   - giải bằng cách độc lập với `cadaudit` ra **đúng một** giá trị trong tệp CAD_READ.
4. Với mỗi dòng kết quả có `actual`, kiểm `actual` bằng giá trị mà evidence ID của trường được kiểm trỏ tới.
5. Đếm lại theo từng quy tắc từ `results[]`: số dòng PASS, FAIL, UNKNOWN và tổng số dòng. Đối chiếu với `rules[].counts` và `rules[].objects_in_scope`.
6. Đối chiếu `coverage_complete`, verdict và `reasons` của từng quy tắc với `coverage` của tệp CAD_READ và với các dòng kết quả, theo thứ tự kết luận D5.
7. Mọi FAIL và UNKNOWN có ít nhất một evidence ID.

**Output đã lọc** đưa vào repo này. Output không có tên layer, tên xref, handle hay đường dẫn máy, và gồm:
- sha256 của ba tệp đầu vào và SHA của script kiểm;
- kết quả kiểm schema;
- tổng số evidence ID; số giải đúng một giá trị; số không giải được; số giải ra nhiều giá trị; số sai dạng hoặc sai `file_id`;
- số dòng có `actual` lệch;
- kết quả đối chiếu số đếm, coverage và verdict theo từng quy tắc (khớp hoặc lệch, kèm số lệch);
- người chạy, thời điểm chạy, người duyệt.

**Không đạt** khi có bất kỳ trường hợp nào sau:
- sai hash;
- báo cáo không hợp schema;
- có evidence ID không giải được, giải ra nhiều giá trị, sai dạng hoặc sai `file_id`;
- có dòng `actual` lệch;
- có số đếm, coverage hay verdict lệch;
- có FAIL hoặc UNKNOWN không có evidence ID.

Không đạt, hoặc chưa chạy phép kiểm này, thì dừng nghiệm thu M04-B.

**Phân vai và giới hạn:**
- Chủ repo chạy phép kiểm trên máy ducdq, hoặc Claude chạy trên máy đó theo quyền chủ repo cấp.
- Reviewer trên cloud chỉ thấy output đã lọc và các hash. Reviewer không đọc dữ liệu thô, nên không tự giải lại evidence ID được.
- Mức tin cậy của điều kiện 6 vì vậy dựa vào script kiểm đã duyệt (G7) và hash đã ghim. Chủ repo nghiệm thu dựa trên đó.

## 6. Nghiệm thu

| Mốc | Mục tiêu | Evidence yêu cầu | Điều kiện đạt | Người duyệt |
|---|---|---|---|---|
| M04-B | Chuỗi trích xuất → kiểm → báo cáo chạy đúng trên một bản vẽ thật, không sửa bản vẽ | Mục 5 | Xem bảng điều kiện đạt bên dưới | REVIEW_V1 tại HEAD, chủ repo |

Điều kiện đạt của M04-B:

| # | Điều kiện |
|---|---|
| 1 | G1–G7 đạt trước khi chạy |
| 2 | sha256 tệp nguồn không đổi trước và sau trích xuất; bộ xuất báo a1–a8 và b1–b4 đều đạt, đúng SHA bộ xuất của G2 |
| 3 | `cadaudit` chạy thành công, báo cáo hợp schema `cad_audit_report.v1` |
| 4 | sha256 của tệp quy tắc trong báo cáo trùng với `approved/check_rules.approved.yaml` tại `0b3c5c5` |
| 5 | `CHC-XREF-RESOLVED` cho PASS hoặc UNKNOWN. Nếu ra FAIL thì đó là dấu hiệu lỗi ánh xạ, vì trái Q1a, và phải điều tra trước khi nghiệm thu |
| 6 | `CHC-LAYER-V2` cho kết luận bất kỳ, nhưng mọi kết quả truy được về đối tượng trong bản trích xuất qua evidence ID: phép kiểm mục 5.1 đạt, có output đã lọc trong evidence |
| 7 | Báo cáo không kết luận đạt tiêu chuẩn |
| 8 | Không có bản trích xuất đầy đủ hay đường dẫn máy nào bị commit |

## 7. Đóng M04 có giới hạn

Sau khi M04-B được nghiệm thu, một PR riêng ghi bản đóng M04, có REVIEW_V1. Bản đóng nêu rõ phần chưa làm:
- M04-C chưa làm, và mục `STANDARD_REQUIRED` vẫn là UNKNOWN `STANDARD_LOOKUP_NOT_ENABLED`;
- giới hạn Q1a của quy tắc xref;
- chỉ một bản vẽ.

Điều kiện thoát "retrieve evidence" của Issue #2 chỉ đạt một phần.

## 8. Các quyết định của chủ repo

Chủ repo chốt trong chat ngày 2026-10-19, khoảng 13:49 +07:00, nguyên văn: "Tôi chốt B1–B5 theo đề xuất của LEAD." Vì vậy cột "Đề xuất của LEAD" dưới đây là quyết định đã chốt.

| # | Câu hỏi | Đề xuất của LEAD |
|---|---|---|
| B1 | Đưa gì vào repo này: chỉ bản tóm tắt và output đã lọc của mục 5.1 (bắt buộc trong mọi lựa chọn), hay thêm báo cáo `cadaudit` đầy đủ (có tên layer, tên xref, sha256 tệp nguồn) | Chỉ bản tóm tắt và output đã lọc; báo cáo đầy đủ ở lại máy người dùng |
| B2 | Số bản vẽ cho M04-B | Một bản vẽ dựng từ mẫu V2 |
| B3 | Bước kiểm chạy ở đâu | Trên máy người dùng (ducdq), không đưa bản trích xuất lên cloud |
| B4 | SHA ghim của `cadaudit` | `9f11076` (`main` hiện tại; `cadaudit/` không đổi từ `c486c8e`) |
| B5 | Thư mục evidence | `tests/m04/evidence_b/` |

## 9. Rủi ro và giới hạn đã biết

- Kết quả đọc bằng LibreDWG chưa được đối chiếu với AutoCAD.
- Coverage `layers` có thể INCOMPLETE, nếu không xác minh được số mục của bảng layer trong JSON của `dwgread` (CHUAN-HOA-CAD PR #68, mục 3.2).
- Quy tắc xref không phát hiện được xref thiếu tệp với nguồn hiện có (Q1a).
- Một bản vẽ không đại diện cho cả bộ hồ sơ.
- Hồ sơ lần đọc chỉ chứng minh các tệp nhất quán với nhau, không tự chứng minh `dwgread` đã đọc đúng tệp đó. Mức tin cậy dựa vào script đọc đã duyệt (G3).
- Reviewer cloud không đọc dữ liệu thô; truy vết được chứng minh qua script kiểm đã duyệt (G7) và output đã lọc (mục 5.1).

## 10. Không thuộc M04-B

- Ghi hay sửa DWG; nâng A2.
- Sửa CHUAN-HOA-CAD từ repo này.
- Gọi Gateway hay NotebookLM.
- M04-C, M05, M06.
- Kết luận pháp lý hay đạt tiêu chuẩn.
- Thêm code mở DWG vào repo này.
