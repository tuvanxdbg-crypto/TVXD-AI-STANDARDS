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
- **4b:** tính lại verdict từng dòng `INTERNAL_ONLY` có `reason` null, bằng phép kiểm viết lại độc lập cho cả sáu loại check. Nhờ vậy bắt được báo cáo ghi PASS cho một layer ngoài danh sách V2.
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
- Verdict của dòng UNKNOWN và dòng `STANDARD_REQUIRED` không được tính lại. Các dòng này được kiểm bằng lý do, trường nguồn null và coverage.
- Script tin vào tệp quy tắc đã ghim hash. Nó không đánh giá nội dung quy tắc đúng hay sai.
- `DAT` chỉ nói báo cáo truy được về bản trích xuất. Nó không kết luận bản vẽ đạt tiêu chuẩn, hợp pháp hay phù hợp thiết kế.
