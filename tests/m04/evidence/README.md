# Evidence M04-A (fixture, dữ liệu giả)

Thư mục này chứa báo cáo mẫu cho từng nhóm fixture của M04-A (spec `docs/M04_CAD_AUDIT_READONLY.md`, §7). Mọi dữ liệu đầu vào là giả (`tests/m04/fixtures/`), không có file DWG hay bản trích xuất thật. Các báo cáo không nói gì về tính đạt tiêu chuẩn, tính hợp pháp hay sự phù hợp thiết kế của một bản vẽ thật.

## File

| File | Nội dung |
|---|---|
| `report_pass__internal.json` | Fixture PASS, quy tắc nội bộ: mọi quy tắc PASS, `overall: ALL_RULES_PASS` |
| `report_fail__internal.json` | Fixture FAIL: sai tên layer, sai font và chiều cao text, thiếu attribute `DRAWING_NO`, dimension bị ghi đè giá trị hiển thị, xref `NOT_FOUND` |
| `report_unknown__internal.json` | Fixture UNKNOWN: coverage `INCOMPLETE` hoặc `NOT_EXTRACTED`, trường `null`; xref `NOT_FOUND` vẫn là FAIL kèm `coverage_complete: false` |
| `report_{pass,fail,unknown}__standard.json` | Quy tắc `STANDARD_REQUIRED` (khai báo và nâng lên theo D4) và selector rỗng: mọi mục `STANDARD_REQUIRED` là UNKNOWN `STANDARD_LOOKUP_NOT_ENABLED`, selector rỗng là UNKNOWN `NO_OBJECTS_IN_SCOPE` |
| `input_errors.json` | Lỗi input và lỗi quy tắc: mã thoát, mã lỗi, và xác nhận không có báo cáo nào được tạo |

`sandbox-linux-unittest.txt` là output `unittest -v` của executor trong sandbox Linux (142 test, 1 bỏ qua vì chỉ chạy trên Windows). Đây không phải kết quả CI và không chứng minh hành vi trên Windows.

Output của `python -m unittest discover -s tests/m04 -p "test_*.py" -v` trên Linux và Windows lấy từ CI (3 job xanh trên HEAD của PR). Test âm D4 nằm trong `test_audit_verdicts.py` (lớp `Classification`), test âm D6 lớp 3 trong `test_static_write_controls.py`, test bảo vệ ghi D6 lớp 2 trong `test_writer_guards.py`.

## Tạo lại báo cáo mẫu

Từ thư mục gốc của repo, Python 3.11 và `pyyaml==6.0.2`:

```text
uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z python tests/m04/make_evidence.py
```

Script gọi CLI thật và bộ ghi thật `cadaudit/_report_writer.py`. Bộ ghi không bao giờ ghi đè, nên script xóa trước các file `report_*__*.json` do nó sinh ra lần trước (chỉ các tên đó, chỉ trong thư mục này). Trường `generated_at` là thời điểm sinh lại. Các trường khác tất định.

Lưu ý: `input_sha256` và `sha256` của file quy tắc trong báo cáo là hash theo byte của fixture. Nếu Git đổi kết thúc dòng của fixture khi checkout (Windows, `core.autocrlf`), hash trong báo cáo mẫu sẽ khác. Không test nào so với các hash này; mọi test tính hash tại lúc chạy.

## Fixture

Fixture JSON được sinh bởi `tests/m04/make_fixtures.py` và `test_fixtures_in_sync.py` kiểm file đã commit khớp với script. Mỗi fixture JSON có `fixture_note` bắt đầu bằng `FIXTURE ONLY`; mỗi fixture YAML bắt đầu bằng dòng `# FIXTURE ONLY`. File "DWG giả" của các test bảo vệ ghi được tạo lúc chạy trong thư mục tạm, không nằm trong repo.
