# M04 CAD audit chỉ đọc: đặc tả

**Trạng thái: BẢN NHÁP CHỜ REVIEW_V1.** Tài liệu này chỉ mô tả việc sẽ làm. Commit chứa nó không thêm code, schema, test hay workflow, và không kết nối AutoCAD. Chỉ được triển khai sau khi có REVIEW_V1 PASS tại đúng SHA chứa spec và chủ repo phê duyệt trực tiếp đúng SHA đó.

## 1. Thẩm quyền

- **Roadmap:** [Issue #2](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/issues/2), mục "M04 — CAD audit read-only".
  - Mục này yêu cầu "Integrate with `CHUAN-HOA-CAD`".
  - Sản phẩm yêu cầu:
    - CAD_READ contract;
    - trích xuất entity/block/layer/attribute/text/measure;
    - drawing evidence ID;
    - bộ phân loại có cần tiêu chuẩn hay không;
    - đầu ra PASS / FAIL / UNKNOWN;
    - không có quyền ghi CAD.
  - Điều kiện thoát: "Claude can identify an issue, decide whether standards lookup is required, retrieve evidence, and report without modifying DWG."
- **Mốc trước:** M03 PASS. Chủ repo chốt ngày 2026-10-12, merge `d0fb512` (PR #16). `CLAUDE.md` ghi: "M04 trở đi chưa được phép. Mốc tiếp theo cần spec mới, REVIEW_V1 và chủ repo phê duyệt trực tiếp."
- **Quyết định của chủ repo trong chat Claude ngày 2026-10-12**, chọn trong các phương án Claude đưa ra:
  1. "Soạn spec M04 (Khuyến nghị)": chỉ soạn spec để review, không chạy, không kết nối AutoCAD.
  2. "Tách: hợp đồng ở đây (Khuyến nghị)". Phần hợp đồng nằm ở TVXD-AI-STANDARDS: CAD_READ contract, bộ phân loại và đầu ra PASS/FAIL/UNKNOWN. Phần này chỉ đọc file JSON trích xuất sẵn. Việc đọc AutoCAD thật vẫn do CHUAN-HOA-CAD làm theo quy trình riêng của repo đó.
  3. "Quy tắc nội bộ + cờ tra cứu (Khuyến nghị)". Vòng đầu kiểm quy tắc nội bộ không cần tiêu chuẩn. Mục cần tiêu chuẩn chỉ gắn cờ `STANDARD_REQUIRED` và trả UNKNOWN, không gọi NotebookLM.
  4. "Fixture giả trước (Khuyến nghị)". Vòng đầu dùng dữ liệu trích xuất giả lập, chạy được trên CI. Bản vẽ thật để sang bước sau, có phê duyệt riêng.
  5. Bốn câu hỏi ở §8 của bản nháp đầu (`ee688c4`). Nguyên văn: "Tôi đồng ý 4 đề xuất cho §8 spec M04." Nội dung các đề xuất ghi ở §8.
- **Phân vai** theo `CLAUDE.md`:
  - LEAD (Claude Opus 5.5) soạn spec;
  - EXECUTOR (Claude Sonnet 5.5) triển khai sau khi spec được duyệt;
  - REVIEWER (GPT-6.1 Sol) review với marker `REVIEW_V1`;
  - chủ repo nghiệm thu và merge.

## 2. Mục tiêu

Với một bản trích xuất bản vẽ dạng JSON đúng contract, hệ thống trả lời được ba câu hỏi, không cần AutoCAD và không thể sửa bản vẽ:

1. **Có vấn đề gì?** Áp từng quy tắc lên từng đối tượng liên quan và ghi kết quả PASS, FAIL hoặc UNKNOWN, kèm evidence ID trỏ đúng đối tượng và trường dữ liệu.
2. **Có cần tiêu chuẩn không?** Mỗi quy tắc được phân loại bằng luật cố định, không dùng LLM: `INTERNAL_ONLY` hoặc `STANDARD_REQUIRED`.
3. **Kết luận được đến đâu?** Không đủ dữ liệu, trích xuất không đầy đủ, hoặc cần tiêu chuẩn mà chưa có tra cứu: kết quả là UNKNOWN có lý do. Không bao giờ đoán PASS hay FAIL.

Đầu ra là một báo cáo có cấu trúc. Báo cáo không kết luận "bản vẽ đạt tiêu chuẩn", không kết luận tính hợp pháp hay sự phù hợp thiết kế, đúng giới hạn đã có từ M01/M02.

## 3. Hiện trạng

### 3.1 CHUAN-HOA-CAD (đọc tại `main` `af1e1f1`, repo private)

| Hạng mục | Hiện trạng |
|---|---|
| Cầu nối AutoCAD | `engine/bridge/lisp_bridge.py` và `vpt_bridge.lsp` (LISP/COM). Có `ReadOnlyGuardTransport` chỉ cho các lệnh đọc (`VB-VERSION`, `VB-IDENT`, `VB-READ`, `VB-COUNTS`, `VB-XREFS`). Đọc được viewport, số đếm, trạng thái xref |
| Công cụ đọc live | `engine/live/l01_readonly.py`, `l06_l14_readonly.py`... Mỗi công cụ chỉ chạy khi có gói phê duyệt ở trạng thái APPROVED |
| Audit Pilot 01B | Dự án thử "Nhà văn hóa Tam Sơn", 8 file. Audit chạy bằng AutoLISP trên máy cục bộ. Báo cáo chỉ rõ độ phủ (ví dụ `CONTENT_READ_INCOMPLETE` với block phụ thuộc xref). Bản dump thô không đưa vào repo |
| Quy tắc | `rules/*.yaml`: LAYER, BLOCK, UNIT, XREF, VIEWPORT, CLEANING. Gần như toàn bộ ở trạng thái `PROPOSED`, chưa duyệt. Bộ duy nhất đã duyệt là `EXECUTION_POLICY` (EP-01..EP-08), là quy tắc thực thi chứ không phải quy tắc kiểm bản vẽ |
| Mapping | `mappings/` trống: "Chưa có mapping nào được duyệt" |

**Hệ quả cho M04:**
- Chưa có quy tắc kiểm bản vẽ nào đã duyệt để M04 dùng làm chuẩn thật.
- Chưa có công cụ nào xuất bản trích xuất đầy đủ layer/text/block/attribute/dimension theo một contract chung.
- Vì vậy vòng đầu M04 chỉ chứng minh cơ chế bằng quy tắc giả và dữ liệu giả, giống cách M02 dùng fixture.

### 3.2 TVXD-AI-STANDARDS (tại `main` `d0fb512`)

- **Gateway M02:** 3 tool `standards_lookup`, `standards_verify`, `standards_status`. NotebookLM adapter ở `notebooklm.mode: "disabled"`.
- **Validator schema:** `gateway/schema.py` là validator JSON Schema tự viết, chỉ dùng thư viện chuẩn. Nó từ chối từ khóa không hỗ trợ.
- **CI M03:** 3 job `linux`, `windows`, `metadata`, là required check ở chế độ strict.
- **Chưa có** thư mục, code hay test nào cho CAD.

## 4. Ranh giới hai repo

| Việc | TVXD-AI-STANDARDS (M04) | CHUAN-HOA-CAD |
|---|---|---|
| Định nghĩa CAD_READ contract (schema) | Có | Dùng contract này khi muốn xuất dữ liệu cho M04 (sau này) |
| Mở DWG, gọi AutoCAD, LISP, COM | **Không bao giờ** | Có, theo quy trình và gói phê duyệt của repo đó |
| Kiểm quy tắc, phân loại, báo cáo PASS/FAIL/UNKNOWN | Có, chỉ trên file JSON | Không bắt buộc |
| Lưu bản vẽ, bản dump thô | Không | Không (đã có quy định riêng) |
| Ghi CAD | Không | Chỉ ở các pilot ghi có phê duyệt riêng, ngoài phạm vi M04 |

M04 không sửa gì trong CHUAN-HOA-CAD. Nếu sau này CHUAN-HOA-CAD cần thêm bộ xuất dữ liệu theo contract, việc đó là một vòng chạy riêng theo quy trình của repo đó (§6, M04-B).

## 5. Sản phẩm M04-A (offline, fixture)

Code đặt trong package mới `cadaudit/` ở gốc repo, test trong `tests/m04/` (§8, quyết định 1).
- Dùng Python 3.11 và `uv` như Gateway.
- Không thêm dependency mới ngoài `pyyaml==6.0.2` đã dùng.
- Không sửa `gateway/`, không import từ `gateway/`.
- **Validator schema** (§8, quyết định 3): `cadaudit/` có bản chép riêng của `gateway/schema.py`, ghi rõ nguồn là commit `d35b574` trong đầu file.
  - Thư mục schema trỏ tới `cadaudit/schemas/`.
  - Giữ nguyên tập từ khóa hỗ trợ và cơ chế từ chối từ khóa lạ khi nạp schema.
  - Test trong `tests/m04/` chạy các ca hợp lệ và không hợp lệ, gồm ca từ khóa lạ bị từ chối, để bản chép không âm thầm lỏng hơn bản gốc.

### D1. CAD_READ contract: `cadaudit/schemas/cad_read.v1.json`

Schema JSON (draft 2020-12, chỉ dùng tập từ khóa mà validator hỗ trợ) cho một bản trích xuất của **một** file bản vẽ.

- **Danh tính (`drawing`):**
  - `file_id`: mã ngắn do bên xuất đặt, không chứa đường dẫn máy;
  - `file_name`;
  - `sha256` của file DWG nguồn;
  - `size_bytes`;
  - `source_tool` và `source_tool_version`;
  - `extracted_at` (ISO 8601);
  - `read_mode`: hằng số `"READ_ONLY"`, mọi giá trị khác bị từ chối;
  - `dwg_modified`: hằng số `false`.
- **Độ phủ (`coverage`), theo từng nhóm** (`layers`, `blocks`, `block_refs`, `attributes`, `texts`, `dimensions`, `xrefs`, `units`):
  - `status`: `COMPLETE`, `INCOMPLETE` hoặc `NOT_EXTRACTED`;
  - `expected` và `enumerated`: số đếm;
  - `reason`: `null` hoặc một mã trong danh sách đóng `XREF_DEPENDENT`, `READ_ERROR`, `TIMEOUT`, `PARTIAL_ENUMERATION`, `NOT_REQUESTED`, kèm `note` tùy chọn.
  Bài học từ Pilot 01B: không được coi "không thấy lỗi" là "đạt" khi chưa đọc hết.
- **Bất biến độ phủ.** Kiểm ngữ nghĩa ngay sau khi kiểm schema. Vi phạm bất kỳ dòng nào là lỗi input `COVERAGE_INCONSISTENT`: dừng hẳn, không sinh báo cáo. Gọi `N` là số phần tử thực có trong mảng của nhóm đó.

  | `status` | `expected` | `enumerated` | `reason` | Mảng đối tượng |
  |---|---|---|---|---|
  | `COMPLETE` | số nguyên ≥ 0 | bằng `expected` | `null` | `N` = `enumerated` |
  | `INCOMPLETE` | số nguyên ≥ 0, hoặc `null` khi không biết tổng | nhỏ hơn `expected` khi `expected` có giá trị; ≥ 0 khi `expected` là `null` | khác `null` | `N` = `enumerated` |
  | `NOT_EXTRACTED` | `null` | 0 | khác `null` | rỗng (`N` = 0) |

  Mảng của một nhóm có phần tử mà `coverage` của nhóm đó không có, hoặc ngược lại, cũng là `COVERAGE_INCONSISTENT`.
- **Tham chiếu chéo.** Handle cha của `attributes` phải có trong `block_refs`.
  - Khi `block_refs` là `COMPLETE`: handle cha không tìm thấy là lỗi input `DANGLING_REFERENCE`.
  - Khi `block_refs` không `COMPLETE`: handle cha không tìm thấy được chấp nhận, nhưng mọi quy tắc cần đối tượng cha cho kết quả UNKNOWN (`COVERAGE_INCOMPLETE`).
- **Đối tượng.** Mỗi đối tượng có `handle` (chuỗi hex của AutoCAD, duy nhất trong file) và `space` (`MODEL`, hoặc tên layout):
  - `layers`: tên, màu, linetype, lineweight, plot, frozen/off/locked;
  - `blocks` (định nghĩa): tên, `is_xref_dependent`, số entity;
  - `block_refs`: handle, tên block, layer, điểm chèn, tỉ lệ, góc;
  - `attributes`: handle cha, tag, value;
  - `texts` (TEXT/MTEXT): value, style, font, height, layer;
  - `dimensions`: kiểu, giá trị đo, giá trị hiển thị, `dimscale`, layer;
  - `xrefs`: tên, trạng thái đường dẫn (`RESOLVED`/`NOT_FOUND`/`UNRESOLVED`), không ghi đường dẫn tuyệt đối của máy;
  - `units`: `INSUNITS`, `MEASUREMENT`.
- **Quy tắc dữ liệu:** `additionalProperties: false` ở mọi cấp. Trường nào không đọc được thì để `null` và ghi vào `coverage`, không bỏ trống im lặng.

### D2. Evidence ID

- Dạng `CADEV:<file_id>:<handle>:<field>`, ví dụ `CADEV:F01:2A3F:layer`. Với thuộc tính cấp file: `CADEV:<file_id>:FILE:<field>`.
- Sinh tất định từ dữ liệu đầu vào. Cùng input thì cùng ID.
- Mỗi kết quả FAIL hoặc UNKNOWN có ít nhất một evidence ID. Mỗi evidence ID trong báo cáo phải trỏ tới đúng một giá trị có trong input, có test kiểm.
- Báo cáo chép giá trị đã trích xuất làm bằng chứng. Không chép nội dung tiêu chuẩn.

### D3. Bộ quy tắc: `cadaudit/schemas/cad_rules.v1.json` và file YAML quy tắc

Mỗi quy tắc có các trường:
- `id`;
- `title`;
- `status`: `FIXTURE`, `PROPOSED` hoặc `APPROVED`;
- `source`: nơi quy tắc được duyệt, ví dụ đường dẫn trong CHUAN-HOA-CAD;
- `applies_to`: một nhóm trong D1;
- `selector`: lọc đối tượng, ví dụ theo layer hay tên block;
- `check`: một trong các kiểu đóng dưới đây;
- `standard_required`: true/false;
- `standard_hint`: tùy chọn, mã tài liệu gợi ý, không phải trích dẫn.

Quy tắc viết bằng YAML (§8, quyết định 2). Chỉ đọc bằng `yaml.safe_load`, rồi kiểm bằng schema JSON trước khi dùng.

Các kiểu `check` được phép, danh sách đóng, không có biểu thức tự do hay `eval`:
- `name_pattern`: tên khớp regex, có giới hạn độ dài;
- `allowed_values`: giá trị trường nằm trong tập cho phép;
- `numeric_range`: giá trị số trong khoảng, có dung sai;
- `required_field`: trường hoặc attribute tag phải có và khác rỗng;
- `equals_field`: hai trường của cùng đối tượng phải bằng nhau, ví dụ giá trị đo và giá trị hiển thị của dimension;
- `xref_resolved`: trạng thái đường dẫn xref là `RESOLVED`.

**Trong M04-A:**
- Mọi quy tắc đều là `FIXTURE`, dữ liệu giả, giống metadata giả của M02.
- Không đưa quy tắc `PROPOSED` của CHUAN-HOA-CAD vào làm chuẩn.
- Báo cáo luôn ghi `status` của quy tắc cạnh từng kết quả. Kết quả từ quy tắc không phải `APPROVED` mang nhãn `rule_status` tương ứng và không được tổng hợp thành "đạt".

### D4. Bộ phân loại cần tiêu chuẩn

- Luật cố định, đọc từ trường `standard_required` của quy tắc. Bộ phân loại chỉ có thể nâng một quy tắc lên `STANDARD_REQUIRED`, không bao giờ hạ xuống:
  - quy tắc nhóm `dimensions` với `check: numeric_range` mà không có `source` nội bộ bị nâng lên `STANDARD_REQUIRED`.
- Cấu hình mâu thuẫn bị từ chối khi nạp: quy tắc có `standard_hint` mà lại khai `standard_required: false`.
- Với quy tắc `STANDARD_REQUIRED`, M04-A không gọi Gateway, không gọi NotebookLM. Kết quả là UNKNOWN với lý do `STANDARD_LOOKUP_NOT_ENABLED`, kèm evidence ID của đối tượng và `standard_hint` nếu có.
- Không có đường nào để quy tắc `STANDARD_REQUIRED` cho ra PASS hay FAIL trong M04-A. Có test âm cho điều này.

### D5. Bộ kiểm và báo cáo

- **CLI:** `python -m cadaudit check --input <cad_read.json> --rules <rules.yaml> --out <report.json>`.
- **Báo cáo** theo `cadaudit/schemas/cad_audit_report.v1.json`:
  - danh tính input: `file_id`, `sha256` của file JSON input, `sha256` của DWG nguồn lấy từ input;
  - danh tính bộ quy tắc (`sha256` của file quy tắc);
  - phiên bản `cadaudit`;
  - danh sách kết quả, mỗi dòng gồm `rule_id`, `rule_status`, `classification`, `handle`, `verdict`, `reason`, `evidence_ids`, giá trị thực tế, giá trị kỳ vọng;
  - tổng hợp theo quy tắc và theo verdict.
- **Lý do UNKNOWN** là danh sách đóng:
  - `COVERAGE_INCOMPLETE`: nhóm dữ liệu chưa đọc đủ;
  - `FIELD_MISSING`: trường cần kiểm là `null`;
  - `STANDARD_LOOKUP_NOT_ENABLED`;
  - `NO_OBJECTS_IN_SCOPE`: selector không chọn được đối tượng nào, nên không kết luận là đạt.
- **Nhóm dữ liệu mà một quy tắc đọc** (`reads_groups`): gồm nhóm `applies_to` cộng mọi nhóm mà `selector` hoặc `check` tham chiếu, ví dụ selector lọc `block_refs` theo layer thì đọc cả `layers`. Danh sách này tính tất định khi nạp quy tắc và in vào báo cáo.
- **Verdict theo từng đối tượng**, xét theo thứ tự, dừng ở dòng đầu tiên khớp:
  1. Quy tắc `STANDARD_REQUIRED`: UNKNOWN (`STANDARD_LOOKUP_NOT_ENABLED`), bất kể dữ liệu.
  2. Trường cần kiểm là `null`, hoặc đối tượng tham chiếu không có vì nhóm liên quan không `COMPLETE`: UNKNOWN (`FIELD_MISSING` hoặc `COVERAGE_INCOMPLETE`).
  3. Áp `check`: FAIL nếu vi phạm, PASS nếu không.
  Một FAIL luôn có evidence ID trỏ tới đúng giá trị vi phạm. Không có FAIL suy luận, kiểu "thiếu đối tượng nên coi là sai".
- **Verdict theo từng quy tắc**, xét theo thứ tự, dừng ở dòng đầu tiên khớp:
  1. Quy tắc `STANDARD_REQUIRED`: UNKNOWN (`STANDARD_LOOKUP_NOT_ENABLED`).
  2. Có ít nhất một đối tượng FAIL: FAIL. FAIL được giữ cả khi độ phủ chưa đủ, vì đã có bằng chứng trực tiếp. Khi đó báo cáo ghi thêm `coverage_complete: false` cạnh FAIL.
  3. Có nhóm trong `reads_groups` không `COMPLETE`: UNKNOWN (`COVERAGE_INCOMPLETE`). Không bao giờ PASS.
  4. Không có đối tượng nào trong phạm vi: UNKNOWN (`NO_OBJECTS_IN_SCOPE`).
  5. Có ít nhất một đối tượng UNKNOWN: UNKNOWN, với lý do của đối tượng đó (nhiều lý do thì liệt kê đủ).
  6. Còn lại, mọi đối tượng đều PASS: PASS.
- **Tổng hợp cả báo cáo:** đếm số quy tắc theo verdict. Không có trường nào mang nghĩa "bản vẽ đạt". Trường `overall` chỉ nhận `HAS_FAIL`, `HAS_UNKNOWN` (khi không có FAIL) hoặc `ALL_RULES_PASS`. Giá trị cuối cùng chỉ có khi mọi quy tắc đều PASS, và luôn đi kèm `rule_status` của từng quy tắc.
- **Lỗi input** dừng hẳn với mã lỗi rõ ràng, không sinh báo cáo, kể cả báo cáo một phần:
  - input sai schema;
  - `read_mode` khác `READ_ONLY`;
  - handle trùng;
  - `COVERAGE_INCONSISTENT`, `DANGLING_REFERENCE`;
  - quy tắc sai schema, hoặc cấu hình mâu thuẫn theo D4.
- **Tất định:** cùng input và cùng quy tắc thì cho cùng báo cáo, so theo byte, trừ một trường thời gian được tách riêng.

### D6. Không có quyền ghi CAD

**Bất biến cần giữ:** `cadaudit` không bao giờ mở một file **đã tồn tại** để ghi. Nó cũng không cắt ngắn, thay thế, đổi tên hay xóa file đã tồn tại nào, ngoài file tạm do chính nó vừa tạo. Mọi lần ghi đều là tạo mới độc quyền. Vì vậy, kể cả khi đường dẫn bị đánh tráo, công cụ cũng chỉ có thể tạo thêm một file mới, không thể sửa một bản vẽ đang có.

Ba lớp:

**1. Đọc input.** File JSON và YAML chỉ được mở ở chế độ đọc (`rb`). Không mở file nào khác.

**2. Ghi báo cáo: bộ ghi duy nhất `cadaudit/_report_writer.py`, fail-closed.**
- **Kiểm `--out` trước khi ghi.** Từ chối và thoát mã khác 0, không tạo file nào, nếu:
  - đuôi không phải `.json` (danh sách cho phép, không phải danh sách cấm);
  - `--out` đã tồn tại dưới bất kỳ dạng nào: file, thư mục, symlink (kể cả symlink hỏng), hard link, junction hay reparse point. Không có tùy chọn ghi đè;
  - thư mục cha không tồn tại hoặc không phải thư mục thật;
  - đường dẫn tuyệt đối của thư mục cha khác với kết quả `os.path.realpath` của nó (so không phân biệt hoa thường trên Windows), tức là trên đường đi có symlink, junction hay reparse point. Đường dẫn dạng 8.3 (ví dụ `DUCDQ~1.TVX`) cũng lệch so với `realpath` và bị từ chối an toàn. Người dùng truyền đường dẫn dạng đầy đủ; thông báo lỗi phải nói rõ điều này (bài học từ M03-C);
  - thư mục cha trùng, hoặc nằm trong, thư mục chứa file input hay file quy tắc;
  - `--out` trùng input hoặc file quy tắc (so bằng đường dẫn đã chuẩn hóa và `os.path.samefile` khi có).
- **Ghi:**
  1. Dựng toàn bộ nội dung báo cáo trong bộ nhớ.
  2. Tạo file tạm có tên ngẫu nhiên dạng `.cadaudit-tmp-<random>.json` trong thư mục cha đã kiểm. Mở bằng `os.open` với `O_CREAT | O_EXCL | O_WRONLY`, thêm `O_NOFOLLOW` khi hệ điều hành có và `O_BINARY` trên Windows.
     - Trên POSIX, thư mục cha được mở bằng `O_DIRECTORY | O_NOFOLLOW`. Mọi thao tác tạo, link và xóa dùng `dir_fd` của thư mục này, để thư mục cha không bị đánh tráo giữa lúc kiểm và lúc ghi.
  3. Ghi đủ nội dung, `flush` và `fsync`, rồi đóng.
  4. **Công bố không thay thế:** POSIX dùng `os.link(tmp, out)`, lệnh này thất bại nếu `out` đã có, rồi xóa tên tạm. Windows dùng `os.rename(tmp, out)`, lệnh này thất bại nếu `out` đã có. Không dùng `os.replace`.
  5. Có lỗi ở bất kỳ bước nào: xóa file tạm (chỉ file tạm do chính lần chạy này tạo), thoát mã khác 0, không để lại file `out`. Không có báo cáo một phần.
- **Sau khi ghi:** kiểm `out` là file thường, `st_nlink == 1`, và `sha256` khớp nội dung đã dựng. Không khớp thì báo lỗi, không xóa gì, vì không chắc file đó là của mình.
- **Phần còn hở, ghi rõ:**
  - Windows không có `dir_fd`. Nếu thư mục cha bị đánh tráo đúng lúc giữa lúc kiểm và lúc ghi, báo cáo có thể bị tạo ở chỗ khác. Bất biến ở đầu mục vẫn giữ: không file nào đang có bị sửa.
  - Nếu tiến trình bị giết giữa chừng, file `.cadaudit-tmp-*` có thể còn lại. Công cụ không tự xóa file nào khi khởi động; file tạm không bao giờ được coi là báo cáo.

**3. Kiểm tĩnh theo danh sách cho phép, dùng AST** (test trong `tests/m04/`, chạy trên mọi file `.py` của `cadaudit/`):
- **Import:**
  - chỉ được import module có trong danh sách cho phép: thư viện chuẩn cần thiết như `json`, `re`, `hashlib`, `argparse`, `os`, `os.path`, `stat`, `errno`, `sys`, `secrets`, `datetime`, `dataclasses`, `typing`, `functools`; cùng `yaml`. Module ngoài danh sách là lỗi;
  - cấm hẳn `subprocess`, `socket`, `ctypes`, `win32com`, `comtypes`, `pythoncom`, `importlib`, `shutil`, `pathlib`, `io`, `tempfile`;
  - cấm `import ... as ...` với `os` và `yaml`; `from os import ...` chỉ cho tên trong danh sách cho phép.
- **Lời gọi và thuộc tính:**
  - ngoài `_report_writer.py`, mọi lời gọi hay truy cập thuộc tính có tên `write`, `write_text`, `write_bytes`, `writelines`, `truncate`, `unlink`, `remove`, `rename`, `replace`, `link`, `symlink`, `rmdir`, `mkdir`, `makedirs`, `chmod`, `chown`, `utime` đều là lỗi, bất kể đối tượng gọi là gì; cùng với `os.open`, `os.system`, `os.fdopen`;
  - ngoài `_report_writer.py`, `open(...)` chỉ được gọi với mode là chuỗi hằng `"rb"` hoặc `"r"`. Mode không phải hằng cũng là lỗi;
  - trong `_report_writer.py`, chỉ được dùng đúng tập lời gọi mà mục 2 cần, liệt kê sẵn trong test.
- **Truy cập động và YAML:**
  - cấm `__import__`, `eval`, `exec`, `compile`, `globals`, `vars`, `setattr`, `delattr`, truy cập `__dict__` hay `__builtins__`;
  - `getattr` chỉ được dùng với tên thuộc tính là chuỗi hằng không thuộc danh sách cấm ở trên;
  - chỉ `yaml.safe_load`; cấm `yaml.load`, `yaml.unsafe_load`, `yaml.full_load` và mọi tham số `Loader=`.
- **Chuỗi:** cấm chuỗi `AutoCAD.Application`.
- **Test âm:** mỗi luật có ít nhất một đoạn mã mẫu vi phạm, và bộ quét phải bắt được. Các mẫu gồm `Path(...).write_text`, `p.open("w")`, `os.open`, `os.replace`, `os.rename`, `os.unlink`, `f.write` ngoài bộ ghi, `import os as o` rồi `o.remove`, `from os import remove`, `__import__("os")`, `importlib.import_module`, `getattr(os, "remove")`, `getattr(os, name)`, `eval`, `exec`, `subprocess`, `ctypes`, `win32com`, `socket`, `yaml.load`.

Kiểm tĩnh là lớp bổ sung, không thay cho kiểm lúc chạy ở lớp 2.

**4. Ranh giới repo:** TVXD-AI-STANDARDS không chứa code LISP, COM hay script mở DWG. `tests/m03/validate_repo_metadata.py` không đổi trong M04-A.

### D7. Fixture và test: `tests/m04/`

- Fixture giả lập, ghi rõ là giả ở đầu mỗi file. Không lấy từ bản vẽ thật hay bản dump của CHUAN-HOA-CAD.
- **Ca PASS:** dữ liệu đúng mọi quy tắc nội bộ.
- **Ca FAIL:** sai tên layer, sai font/chiều cao text, thiếu attribute bắt buộc, dimension bị ghi đè giá trị hiển thị, xref `NOT_FOUND`.
- **Ca UNKNOWN:** coverage `INCOMPLETE`, trường `null`, quy tắc `STANDARD_REQUIRED`, selector rỗng.
- **Bất biến độ phủ (D1):** test theo bảng cho mọi tổ hợp `status` × quan hệ giữa `expected`, `enumerated`, `reason` và số phần tử thực. Tổ hợp hợp lệ được chấp nhận, mọi tổ hợp còn lại cho `COVERAGE_INCONSISTENT`. Có ca `COMPLETE` mà `enumerated` khác `expected`, và ca `COMPLETE` mà mảng thiếu phần tử.
- **Thứ tự kết luận (D5):** mỗi dòng trong hai danh sách thứ tự có ít nhất một ca. Gồm ca FAIL cùng độ phủ không đủ (giữ FAIL, ghi `coverage_complete: false`), ca không FAIL mà độ phủ không đủ (UNKNOWN, không PASS), và ca selector đọc nhóm khác chưa `COMPLETE`.
- **Ca lỗi input:** sai schema, `read_mode: "READ_WRITE"`, handle trùng, `COVERAGE_INCONSISTENT`, `DANGLING_REFERENCE`, quy tắc có kiểu `check` lạ, quy tắc có `standard_hint` mà `standard_required: false`.
- **Bảo vệ ghi (D6 lớp 2), chạy trên Linux và Windows.** Mỗi ca kiểm cả ba điều: mã thoát khác 0; file đích hay file bị trỏ tới giữ nguyên `sha256` và kích thước; không còn file tạm. Các ca:
  - `--out` đã tồn tại là file thường (có đuôi `.json`);
  - `--out` là symlink tới một file giả mang đuôi `.dwg`;
  - `--out` là symlink hỏng;
  - `--out` là hard link tới file giả `.dwg`;
  - thư mục cha là symlink (POSIX) hoặc junction (Windows);
  - đuôi không phải `.json`;
  - `--out` trùng input;
  - `--out` nằm trong thư mục input;
  - lỗi giả lập giữa lúc ghi file tạm.
  Trên Windows, nếu tạo symlink cần quyền mà runner không có, test đó bị bỏ qua với lý do ghi rõ. Test junction và hard link vẫn phải chạy.
- **Kiểm tĩnh (D6 lớp 3):** đủ test âm như đã liệt kê.
- **Kiểm truy vết:** mọi evidence ID trong mọi báo cáo fixture trỏ tới đúng giá trị trong input.
- **Kiểm tất định:** chạy hai lần, so báo cáo theo byte.

### D8. CI

- Thêm một bước chạy `tests/m04` vào hai job `linux` và `windows` của `.github/workflows/ci.yml`.
- Giữ nguyên tên 3 job, quyền `contents: read`, các action ghim SHA và mọi ràng buộc của M03 D3.
- Sửa `.github/` là vùng nhạy cảm: PR phải đánh dấu trong template và cần REVIEW_V1.

### D9. Tài liệu và trạng thái

- **`README.md`:** thêm mục M04 ngắn.
- **`CLAUDE.md`:** thêm mục "M04 rules" sau khi chủ repo nghiệm thu M04-A. Mục này ghi các ràng buộc của §9, để chúng vẫn có hiệu lực sau khi M04 đóng, giống cách làm với M01/M02.
- **Evidence nghiệm thu:** đặt ở `tests/m04/evidence/`.

## 6. Thứ tự và các bước sau

| Bước | Nội dung | Được phép theo spec này? |
|---|---|---|
| M04-A | D1–D9 với fixture, chạy offline và trên CI | Có, sau khi spec có REVIEW_V1 PASS và chủ repo phê duyệt |
| M04-B | Chạy bộ kiểm trên một bản trích xuất **thật** do CHUAN-HOA-CAD xuất theo contract D1, từ một file bản vẽ được chọn, với quy tắc đã `APPROVED` bên CHUAN-HOA-CAD | **Không.** Cần kế hoạch riêng. CHUAN-HOA-CAD có bộ xuất theo quy trình của repo đó; có ít nhất một quy tắc được duyệt bên đó; quyết định dữ liệu thật nào được đưa vào repo (mặc định chỉ báo cáo đã lọc, không đưa bản trích xuất đầy đủ); REVIEW_V1 và chủ repo phê duyệt |
| M04-C | Với kết quả `STANDARD_REQUIRED`, gọi Gateway để lấy evidence tiêu chuẩn | **Không.** Phụ thuộc vào việc mở lại NotebookLM live theo quy tắc M02: kế hoạch có review, nguồn giới hạn, chủ repo phê duyệt. Trước đó M04 chỉ ghi `STANDARD_LOOKUP_NOT_ENABLED` |

**Cách đóng M04** (§8, quyết định 4):
- M04 được **đóng có giới hạn** sau khi M04-A và M04-B đều được chủ repo nghiệm thu, giống cách M02 đã đóng.
- Bản ghi đóng phải nói rõ phần chưa làm: mục `STANDARD_REQUIRED` vẫn trả UNKNOWN với lý do `STANDARD_LOOKUP_NOT_ENABLED`. Vì vậy điều kiện thoát của Issue #2 ("retrieve evidence") mới đạt một phần.
- M04-C tách thành mốc riêng, có spec hoặc kế hoạch riêng, làm khi NotebookLM live được mở lại theo quy tắc M02.
- M04-A tự nó không làm M04 đóng. M04-B phụ thuộc vào việc CHUAN-HOA-CAD có ít nhất một quy tắc kiểm bản vẽ được duyệt; trong lúc chờ, M04 vẫn ở trạng thái đang thực hiện.

## 7. Nghiệm thu

Theo `CLAUDE.md`, mỗi mốc nghiệm thu ghi đủ: mục tiêu, evidence yêu cầu, điều kiện đạt, người duyệt.

| Mốc | Mục tiêu | Evidence yêu cầu | Điều kiện đạt | Người duyệt |
|---|---|---|---|---|
| M04-A | Contract, bộ quy tắc, bộ phân loại, bộ kiểm, báo cáo, bảo vệ ghi; chạy bằng fixture | Link CI xanh của 3 job trên HEAD của PR; output `tests/m04` trên Linux và Windows; báo cáo mẫu cho từng nhóm fixture (PASS, FAIL, UNKNOWN, lỗi input); output test âm của D4 và D6; kiểm truy vết và kiểm tất định | Mọi ca fixture cho đúng verdict và lý do. Không ca `STANDARD_REQUIRED` nào ra PASS/FAIL. Không ca nào có nhóm trong `reads_groups` chưa `COMPLETE` mà ra PASS. Mọi tổ hợp độ phủ sai đều bị từ chối. Mọi ca bảo vệ ghi D6 lớp 2 đạt trên cả Linux và Windows: không file có sẵn nào bị đổi, không còn file tạm. Mọi test âm D6 lớp 3 bắt đúng mẫu. Mọi evidence ID truy được về input. Báo cáo tất định. Không có code LISP/COM/DWG trong repo | REVIEW_V1 tại HEAD, chủ repo |
| M04-B | Chạy trên dữ liệu thật | Theo kế hoạch riêng (§6) | Theo kế hoạch riêng | REVIEW_V1, chủ repo |
| M04-C | Tra tiêu chuẩn cho mục `STANDARD_REQUIRED` | Theo kế hoạch riêng (§6) | Theo kế hoạch riêng | REVIEW_V1, chủ repo |
| M04 (đóng có giới hạn) | Đóng M04 sau M04-A và M04-B | Nghiệm thu M04-A và M04-B; bản ghi đóng nêu rõ phần chưa làm (M04-C) | M04-A và M04-B đều PASS; bản ghi đóng có REVIEW_V1 | Chủ repo |

## 8. Quyết định của chủ repo

Ngày 2026-10-12, trong chat Claude, chủ repo đồng ý cả bốn đề xuất Claude đưa ra cho các câu hỏi ở §8 của bản nháp đầu. Nguyên văn: "Tôi đồng ý 4 đề xuất cho §8 spec M04."

| # | Câu hỏi | Quyết định | Lý do (theo đề xuất đã được đồng ý) |
|---|---|---|---|
| 1 | Vị trí và tên | Package `cadaudit/` ở gốc repo, test ở `tests/m04/` | Tách khỏi code M01/M02, dễ khoanh vùng cho CI và `CODEOWNERS` |
| 2 | Định dạng quy tắc | YAML, kiểm bằng schema JSON, chỉ đọc bằng `yaml.safe_load` | Khớp INDEX của M02 và `rules/*.yaml` của CHUAN-HOA-CAD; không thêm dependency; `safe_load` không dựng object tùy ý |
| 3 | Validator | Chép một bản riêng vào `cadaudit/`, ghi nguồn `gateway/schema.py` tại `d35b574`, có test riêng. Không import từ `gateway/` | `gateway/schema.py` đọc schema từ thư mục cố định `gateway/schemas/`, và bước chặn từ khóa lạ nằm trong hàm nội bộ. Import sẽ ràng M04 vào chi tiết nội bộ của Gateway (M02 đã đóng, vùng nhạy cảm) |
| 4 | Cách đóng M04 | Đóng có giới hạn sau M04-A + M04-B; M04-C thành mốc riêng | M04-C phụ thuộc việc mở lại NotebookLM live, chưa có thời điểm. Chi tiết ở §6 |

Bản nháp đầu `ee688c4` đề xuất import validator. Quyết định 3 thay đề xuất đó.

## 9. Chưa được phép theo spec này

- Triển khai bất kỳ phần nào trước khi spec có REVIEW_V1 PASS và chủ repo phê duyệt trực tiếp.
- Kết nối hay điều khiển AutoCAD; thêm code LISP, COM, AutoLISP hay script mở DWG vào TVXD-AI-STANDARDS.
- Đưa file DWG, DXF, bản sao làm việc, bản dump thô hay dữ liệu bản vẽ thật vào repo.
- Ghi CAD dưới mọi hình thức (M05/M06).
- Gọi Gateway ở chế độ live, gọi NotebookLM, hay đổi `notebooklm.mode`.
- Sửa CHUAN-HOA-CAD, hay coi quy tắc `PROPOSED` bên đó là đã duyệt.
- Kết luận tính hợp pháp, sự phù hợp thiết kế hay "đạt tiêu chuẩn".
- Đổi pin, config, quyền M01; đổi ruleset hay cài đặt repo.
- Các bước M04-B, M04-C, M05, M06.
