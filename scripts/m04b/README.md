# Kiểm truy vết cục bộ M04-B (G7)

`kiem_truy_vet.py` hiện thực phép kiểm ở mục 5.1 của `docs/M04_B_PLAN.md`. Đây là điều kiện G7.

Script chạy trên máy người dùng (B3), ngay sau `python -m cadaudit check`. Nó chỉ đọc ba tệp đã ghim sha256:
- tệp CAD_READ;
- tệp quy tắc;
- báo cáo.

Script chỉ tạo một tệp output mới. Nó không gọi mạng, AutoCAD, Gateway hay NotebookLM.

Có script này chưa có nghĩa là G7 đạt. G7 chỉ đạt khi script có REVIEW_V1 PASS và chủ repo duyệt **tại một SHA cụ thể**. Lần chạy thật phải dùng đúng SHA đó.

## Cách chạy

Chạy từ một bản checkout của repo tại SHA đã duyệt cho G7:

```text
python scripts/m04b/kiem_truy_vet.py \
    --cad-read <tệp CAD_READ> --rules <check_rules.approved.yaml> --report <báo cáo cadaudit> \
    --sha256-cad-read <hex> --sha256-rules <hex> --sha256-report <hex> \
    --out <tệp output mới> [--nguoi-chay <tên>] [--nguoi-duyet <tên>]
```

- Ba giá trị `--sha256-*` lấy từ evidence đã ghim (mục 5 của kế hoạch), không lấy bằng cách tính lại ngay trước khi chạy.
- `--out` phải chưa tồn tại. Script mở tệp bằng chế độ `x` và không ghi đè.
- Script đọc `gateway/schema.py` và `cadaudit/schemas/*.json` từ chính bản checkout. B4 ghim `cadaudit` tại `9f11076`, nên trước khi chạy phải kiểm `git diff --stat 9f11076 HEAD -- cadaudit/` rỗng. Lệnh `cadaudit check` chạy theo mục 4, bước 2 của kế hoạch.

## Exit code

| Mã | Ý nghĩa | Có ghi output |
|---|---|---|
| 0 | `DAT` | có |
| 1 | `KHONG_DAT`, gồm cả sai hash ở bước 1 | có |
| 2 | Lỗi đầu vào: tệp không đọc được, không phải JSON/YAML, khóa JSON trùng, hash truyền vào sai dạng, `--out` đã tồn tại | không |
| 70 | Lỗi nội bộ | không |

Lỗi trên stderr chỉ ghi mã lỗi, không ghi đường dẫn.

## Các bước kiểm

Bảy bước của mục 5.1:
1. sha256 ba tệp. Sai thì dừng, vẫn ghi output `KHONG_DAT`.
2. Báo cáo hợp schema `cad_audit_report.v1`.
3. Mọi evidence ID, cả cấp quy tắc, cấp dòng và cấp `FILE`, phải đúng dạng, đúng `file_id` và giải ra đúng một giá trị đơn.
4. `actual` của từng dòng bằng giá trị tại evidence ID của trường được kiểm.
5. Đếm lại PASS/FAIL/UNKNOWN và số dòng theo quy tắc.
6. Đối chiếu `coverage_complete`, verdict, `reasons` theo thứ tự D5.
7. Mọi FAIL và UNKNOWN có ít nhất một evidence ID.

Phần bổ sung chặt hơn mục 5.1. Mỗi phần sai đều cho `KHONG_DAT`:
- **2b:** tệp CAD_READ hợp schema `cad_read.v1`.
- **2c:** bất biến coverage D1 của CAD_READ, viết độc lập theo loader. Mọi nhóm phải có mục coverage; `enumerated` bằng số phần tử mảng; `COMPLETE` có `expected` nguyên, `expected == enumerated` và `reason` null; `INCOMPLETE` có `expected` null hoặc lớn hơn `enumerated` và có `reason`; `NOT_EXTRACTED` có `expected` null, `enumerated` 0 và có `reason`. Sai thì `CAD_READ_COVERAGE_SAI`, `buoc2_schema.cad_read.so_nhom_coverage_sai` ghi số nhóm sai, và script dừng trước bước 3 như khi sai schema.
- **4b:** tính lại verdict từng dòng `INTERNAL_ONLY` có `reason` null, bằng phép kiểm viết lại độc lập cho cả sáu loại check. Nhờ vậy bắt được báo cáo ghi PASS cho một layer ngoài danh sách V2.
- **4c:** metadata từng dòng. `rule_status`, `classification` (phân loại D4 tính lại) và `standard_hint` của mỗi dòng phải bằng tệp quy tắc và bằng mục `rules[]` tương ứng. Lệch thì `DONG_METADATA_LECH`.
- **Cha thiếu:** dòng UNKNOWN/`COVERAGE_INCOMPLETE` vì cha thiếu chỉ hợp lệ khi nhóm là `attributes`, selector có khóa `layer` hoặc `block_name`, cha vắng trong `block_refs`, `block_refs` chưa `COMPLETE` và mọi khóa selector khác thỏa. Quy tắc không cần cha (ví dụ `selector: {}`) thì dòng phải được tính như dòng thường. Dòng ghi `COVERAGE_INCOMPLETE` mà không đủ điều kiện bị đánh dấu lệch lý do, và vẫn bị kiểm trường, `actual`, verdict trực tiếp.
- **5b:** tính lại phạm vi từng quy tắc từ selector, rồi so với các dòng báo cáo. Nhờ vậy bắt được trường hợp bỏ sót đối tượng, kể cả khi số đếm, verdict và phần tổng hợp đã được sửa cho tự nhất quán.
- **Liên kết:**
  - báo cáo khớp tệp: `file_id`, `input_sha256`, `dwg_sha256`, `rules_sha256`, `rules_version`;
  - metadata quy tắc khớp tệp YAML: trạng thái, phân loại D4, `reads_groups`, thứ tự `rule_id`;
  - phần `summary` khớp các dòng.

Script không import `cadaudit`:
- Evidence ID được giải theo logic của `resolve_evidence` trong `tests/m04/m04_helpers.py`.
- Schema được kiểm bằng `gateway.schema.validate` (M02).

## Output đã lọc

Schema `tvxd.m04b.kiem_truy_vet/v1`. Output gồm:
- hash ba tệp: tính được, ghim, khớp;
- sha256 của script: `sha256_tho` và `sha256_lf`;
- kết quả schema;
- số evidence ID theo loại;
- số dòng lệch theo loại;
- kết quả đối chiếu theo từng quy tắc;
- `ket_luan`, `ly_do_khong_dat`, `nguoi_chay`, `nguoi_duyet`, `chay_luc` (UTC+7).

Output không có tên layer, tên xref, handle, giá trị `actual`/`expected` hay đường dẫn máy. `rule_id` lạ được thay bằng `RULE_<số>`. Đây là tệp đưa vào `tests/m04/evidence_b/` theo B1 và B5.

Khi đối chiếu SHA của script, dùng `sha256_lf`. Checkout trên Windows có `core.autocrlf` có thể đổi kết thúc dòng, làm `sha256_tho` khác.

## Giới hạn

- Chỉ kiểm trên dữ liệu giả trong `tests/m04/test_m04b_kiem_truy_vet.py`. Chưa chạy trên bản trích xuất thật.
- Verdict của dòng UNKNOWN và dòng `STANDARD_REQUIRED` không được tính lại, vì chúng không có PASS/FAIL. Các dòng này được kiểm bằng lý do, metadata, trường nguồn null, coverage và điều kiện `parent_unknown` ở trên. Dòng UNKNOWN do trường null chỉ được xác nhận là trường nguồn thật sự null; dòng UNKNOWN do coverage chỉ được xác nhận theo bất biến coverage và điều kiện cha thiếu.
- Script chỉ kiểm bất biến coverage của loader. Các kiểm khác của loader (handle trùng, tham chiếu treo, tag trùng) không nằm trong script; chúng đã được `cadaudit` kiểm khi tạo báo cáo.
- Script tin vào tệp quy tắc đã ghim hash. Nó không đánh giá nội dung quy tắc đúng hay sai.
- `DAT` chỉ nói báo cáo truy được về bản trích xuất. Nó không kết luận bản vẽ đạt tiêu chuẩn, hợp pháp hay phù hợp thiết kế.

## Bản tóm tắt (`tom_tat.py`)

`tom_tat.py` tạo **bản tóm tắt** theo mục 5 của `docs/M04_B_PLAN.md` và quyết định B1: repo chỉ nhận bản tóm tắt và output đã lọc của G7. Báo cáo `cadaudit` đầy đủ, tệp CAD_READ và tệp quy tắc ở lại máy người dùng. Chạy trên máy người dùng, sau `kiem_truy_vet.py`. Chỉ đọc bốn tệp đầu vào, chỉ tạo một tệp output mới (`xb`, không ghi đè). Chỉ dùng thư viện chuẩn; không import `cadaudit`, `gateway` hay `kiem_truy_vet`. Có script này chưa có nghĩa là bước tóm tắt đã được duyệt: cần REVIEW_V1 và chủ repo duyệt tại một SHA cụ thể.

```text
python scripts/m04b/tom_tat.py \
    --cad-read <tệp CAD_READ> --rules <check_rules.approved.yaml> --report <báo cáo cadaudit> \
    --kiem-truy-vet <output của kiem_truy_vet.py> \
    --sha256-cad-read <hex> --sha256-rules <hex> --sha256-report <hex> \
    --cadaudit-sha <40 hex> --out <tệp output mới>
```

Sai bất kỳ điều kiện đầu vào nào thì exit 2, không ghi gì, và lỗi trên stderr chỉ là mã, không có đường dẫn:
- sha256 tính được của ba tệp khác giá trị ghim;
- JSON có khóa trùng hoặc NaN/Infinity (CAD_READ, báo cáo, tệp kiểm truy vết);
- tệp kiểm truy vết sai `schema`, có `sha256.*.tinh_duoc` khác hash vừa tính, hoặc `buoc_da_chay` không đủ `1`..`7` (G7 dừng sớm thì bị từ chối);
- báo cáo có `rules_file.sha256` khác hash tệp quy tắc, hoặc `input.input_sha256` khác hash tệp CAD_READ;
- trường được đọc sai kiểu hoặc sai enum (kể cả `coverage.layers` và `coverage.xrefs` của CAD_READ, và mã `ly_do_khong_dat` không nằm trong danh sách mã của G7);
- `--cadaudit-sha` không đúng 40 hex; `--out` đã tồn tại (tệp, thư mục hay symlink).

Exit: 0 đã ghi output; 2 lỗi đầu vào; 70 lỗi nội bộ. Bản tóm tắt chỉ mô tả, nên kết luận `KHONG_DAT` của G7 vẫn được ghi và chép nguyên (`ket_luan`, `ly_do_khong_dat`), không bị đổi thành lỗi.

Output `tvxd.m04b.tom_tat/v1` được dựng từ danh sách trường cố định, gồm:
- `sha256` của CAD_READ, quy tắc, báo cáo và tệp kiểm truy vết; `cadaudit_sha`, `report_schema`;
- `overall`, `all_rules_approved`, `overall_note`, `rules_by_verdict`, `rules_by_status`, `results_by_verdict`;
- `quy_tac`: từng quy tắc theo thứ tự báo cáo, có `rule_id` (sai dạng thì thành `RULE_<số thứ tự>`), `rule_status`, `classification`, `verdict`, `reasons`, `counts`, `objects_in_scope`, `coverage_complete`;
- `coverage`: `layers` và `xrefs` với `status`, `expected`, `enumerated`, `reason` (enum); không có `note`;
- `kiem_truy_vet`: `ket_luan`, `ly_do_khong_dat`, `script_sha256_lf`; `script`: `sha256_tho`, `sha256_lf` của chính `tom_tat.py`; `tao_luc` (UTC+7).

Mọi chuỗi trong output chỉ là hex, enum cố định, `rule_id` đúng regex (hoặc `RULE_<số thứ tự>`) hoặc `tao_luc`. Không có chuỗi văn bản tự do. `cadaudit_version` và `rules_version` không được chép vì hai nhãn này có thể mang đường dẫn; `cadaudit_sha` và `sha256.quy_tac` đã định danh phiên bản.

Output không có `drawing`, `file_id`, hash DWG, `results[]`, handle, tên layer hay xref, `actual`/`expected` của dòng, evidence ID, `note` tự do hay đường dẫn. Khi đối chiếu SHA của script, dùng `sha256_lf`.

Giới hạn: bản tóm tắt không tự kiểm lại báo cáo (việc của G7) và không kết luận bản vẽ đạt tiêu chuẩn. Chỉ kiểm trên dữ liệu giả trong `tests/m04/test_m04b_tom_tat.py`; chưa chạy trên dữ liệu thật.
