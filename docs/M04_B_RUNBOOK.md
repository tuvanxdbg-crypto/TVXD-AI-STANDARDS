# Quy trình chạy M04-B trên bản vẽ thật

Trạng thái: **bản nháp chờ REVIEW_V1**. Tài liệu này chỉ mô tả cách chạy. Nó không cho phép chạy.

Căn cứ: kế hoạch `docs/M04_B_PLAN.md`, mục 3 (G1–G7), mục 4 (luồng chạy), mục 5 (evidence) và mục 8 (B1–B5). Khi tài liệu này khác kế hoạch, kế hoạch thắng.

## 1. Điều kiện trước khi chạy

Chỉ bắt đầu khi đủ các điều sau, mỗi điều có căn cứ dẫn được:

| # | Điều kiện | Căn cứ |
|---|---|---|
| 1 | G1–G7 của kế hoạch đều "Đạt" trên `main` | `docs/M04_B_PLAN.md` mục 3 |
| 2 | Gói đọc thật G3 bên CHUAN-HOA-CAD có review và được chủ repo phê duyệt tại SHA cụ thể | run G3 bên CHUAN-HOA-CAD |
| 3 | Bản vẽ G4 đã chọn và có căn cứ thuộc phạm vi mẫu V2. sha256 bản vẽ ghi trong gói G3 | quyết định G4 |
| 4 | Chủ repo phê duyệt trực tiếp lần chạy này | lời phê duyệt riêng cho lần chạy |

Thiếu một điều thì dừng.

## 2. Phiên bản được dùng

| Thành phần | Phiên bản ghim | Cách kiểm |
|---|---|---|
| Bộ xuất CAD_READ (G2) | CHUAN-HOA-CAD `0223f8ee5f8d56cdd89d7c93347fd206c4b9bfa1`, `runs/M04BEX-20261019-01/tools/cadread_export.py` | sha256 `8de2ea099ff1fea1480ea06d0c369281fe17894ad2fc9fd58dd9d04cb48b551e` |
| Tệp quy tắc | CHUAN-HOA-CAD `0b3c5c5`, `approved/check_rules.approved.yaml` | sha256 `c6e94d72f41e7d4af39209b651e35af725f766ac46212ba196f4258680e57c37` |
| `cadaudit` (B4, G6) | TVXD-AI-STANDARDS, `cadaudit/` không đổi so với `9f11076` | `git diff --stat 9f11076 HEAD -- cadaudit/` rỗng |
| Script kiểm truy vết (G7) | `scripts/m04b/kiem_truy_vet.py` như tại `af82d368066ade4a91e6750d08726fc04a7c7079` | sha256 `e8e6ec93549e134e799c8fcbbf24e8ff8014ce871b1e81b3e602afc6eef1ef8a`; với checkout Windows dùng trường `sha256_lf` trong output |
| Công cụ tóm tắt | `scripts/m04b/tom_tat.py` tại SHA được merge sau review | ghi `script.sha256_lf` trong output |

Dùng **một** bản checkout TVXD-AI-STANDARDS tại một SHA của `main` thỏa cả bốn dòng cuối. Ghi SHA này vào bước 4.

## 3. Nơi chạy và nơi để tệp

- Mọi bước chạy trên máy ducdq (B3). Môi trường cloud không nhận bản vẽ, JSON `dwgread`, tệp CAD_READ hay báo cáo đầy đủ.
- Tạo một thư mục làm việc **ngoài** cả hai repo, ví dụ `<WORK>`, với hai thư mục con **ngang hàng**:
  - `<WORK>\input\`: tệp CAD_READ và tệp quy tắc;
  - `<WORK>\out\`: báo cáo `cadaudit`, output kiểm truy vết, bản tóm tắt.
  - Không đặt `out` bên trong `input`, và không đặt đầu vào trực tiếp trong `<WORK>` rồi ghi vào `<WORK>\out\`. Guard D6 của `cadaudit` từ chối ghi báo cáo vào thư mục chứa đầu vào **và mọi thư mục con của nó** (`OUT_IN_INPUT_DIR`).
  - Tạo sẵn hai thư mục, ví dụ PowerShell: `New-Item -ItemType Directory <WORK>\input, <WORK>\out`.
- Chỉ hai tệp đã lọc được chép vào repo (bước 8).

## 4. Chuẩn bị bản checkout TVXD-AI-STANDARDS

```text
git -C <TVXD> fetch origin
git -C <TVXD> checkout --detach <SHA_TVXD>
git -C <TVXD> status --short                       # phải rỗng
git -C <TVXD> diff --stat 9f11076 HEAD -- cadaudit/  # phải rỗng
git -C <TVXD> rev-parse HEAD                        # ghi lại: <SHA_TVXD>
```

Chạy các lệnh Python từ thư mục `<TVXD>`. Python 3.11 và PyYAML như CI.

## 5. Trích xuất (bên CHUAN-HOA-CAD, theo gói G3)

Làm đúng các bước của gói G3 đã duyệt. Kết quả là một tệp CAD_READ v1, chép vào `<WORK>\input\cad_read.json`, do bộ xuất tại `0223f8e` tạo, sau khi a1–a8 và b1–b4 đều đạt. Bộ xuất báo lỗi thì dừng.

Tệp quy tắc lấy đúng từ CHUAN-HOA-CAD `0b3c5c5`, đặt vào `<WORK>\input\check_rules.approved.yaml`.

## 6. Ghim hash

Tính sha256 của tệp CAD_READ và tệp quy tắc, ví dụ bằng PowerShell `Get-FileHash -Algorithm SHA256 <tệp>`, chuyển sang chữ thường. Đối chiếu:
- hash tệp quy tắc phải bằng `c6e94d72…7c37`;
- hash tệp CAD_READ phải bằng giá trị bộ xuất ghi trong `RUN_MANIFEST` bên CHUAN-HOA-CAD.

Ghi hai giá trị: `<H_CAD>`, `<H_RULES>`.

## 7. Kiểm, kiểm truy vết, tóm tắt

```text
python -m cadaudit check --input <WORK>\input\cad_read.json --rules <WORK>\input\check_rules.approved.yaml --out <WORK>\out\report.json
```
- Exit khác 0 thì dừng.
- Tính sha256 của báo cáo: `<H_REPORT>`.

```text
python scripts\m04b\kiem_truy_vet.py --cad-read <WORK>\input\cad_read.json --rules <WORK>\input\check_rules.approved.yaml --report <WORK>\out\report.json --sha256-cad-read <H_CAD> --sha256-rules <H_RULES> --sha256-report <H_REPORT> --out <WORK>\out\kiem_truy_vet.json --nguoi-chay <tên> --nguoi-duyet <tên>
```
- Exit 0 là DAT; exit 1 là KHONG_DAT, output vẫn được ghi; exit 2 hoặc 70 thì dừng.
- KHONG_DAT thì M04-B không được nghiệm thu (kế hoạch mục 5.1). Nếu kiểm truy vết đã chạy đủ 7 bước, vẫn chạy bước tóm tắt để có hồ sơ phân tích. Nếu nó dừng sớm ở bước 1 (sai hash) hoặc bước 2 (sai schema, sai coverage), `tom_tat.py` từ chối với exit 2: dừng và ghi lại `ly_do_khong_dat`.

```text
python scripts\m04b\tom_tat.py --cad-read <WORK>\input\cad_read.json --rules <WORK>\input\check_rules.approved.yaml --report <WORK>\out\report.json --kiem-truy-vet <WORK>\out\kiem_truy_vet.json --sha256-cad-read <H_CAD> --sha256-rules <H_RULES> --sha256-report <H_REPORT> --cadaudit-sha <SHA_TVXD> --out <WORK>\out\tom_tat.json
```
- Exit khác 0 thì dừng.

## 8. Đưa evidence vào repo (B1, B5)

1. Tạo nhánh mới từ `main` mới nhất.
2. Tạo thư mục `tests/m04/evidence_b/<RUN_ID>/`. `<RUN_ID>` theo dạng `M04B-<YYYYMMDD>-<NN>`.
3. Chép đúng hai tệp: `kiem_truy_vet.json` và `tom_tat.json`. Không chép tệp CAD_READ, báo cáo đầy đủ, tệp quy tắc, JSON `dwgread` hay bất kỳ tệp nào khác.
4. Thêm `README.md` trong thư mục đó, gồm:
   - các lệnh đã chạy ở bước 4–7, thay mọi đường dẫn bằng `<TVXD>`, `<WORK>`;
   - exit code từng lệnh;
   - RUN_ID các run bên CHUAN-HOA-CAD, kèm SHA gói G3 và SHA bộ xuất;
   - người chạy, thời điểm theo `YYYY-MM-DD HH:mm +07:00`.
5. Trước khi commit, kiểm hai tệp JSON không có tên layer, tên xref, handle, tên tệp hay đường dẫn máy. Chạy `python tests/m01/check_no_secrets.py`.
6. Mở PR nháp, đăng `CLAUDE_EXECUTION_REPORT` với `NEXT_REQUEST`, chờ REVIEW_V1, rồi chủ repo nghiệm thu theo kế hoạch mục 6.

## 9. Dừng ngay khi

- Thiếu một điều kiện ở mục 1, hoặc một phiên bản ở mục 2 không khớp.
- Một lệnh ở bước 5–7 trả exit lỗi (với `kiem_truy_vet.py`: exit 2 hoặc 70).
- Có dấu hiệu bản vẽ hoặc tệp nguồn bị thay đổi (hash trước và sau khác nhau ở gói G3).
- Thấy tên layer, xref hay đường dẫn máy trong tệp sắp commit.

Dừng thì ghi lại bước đang làm và lỗi (đã bỏ đường dẫn), không thử lại theo cách khác khi chưa có chỉ đạo.

## 10. Không thuộc quy trình này

- Không sửa bản vẽ, không ghi CAD, không mở AutoCAD từ repo này.
- Không gọi Gateway hay NotebookLM. Mục `STANDARD_REQUIRED` vẫn UNKNOWN `STANDARD_LOOKUP_NOT_ENABLED`.
- Không kết luận bản vẽ đạt tiêu chuẩn, hợp pháp hay phù hợp thiết kế.
