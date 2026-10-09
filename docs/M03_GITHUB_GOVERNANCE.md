# M03 GitHub governance: đặc tả (BẢN NHÁP chờ REVIEW_V1, chưa triển khai)

**Trạng thái: SPEC DRAFT.** Tài liệu này chỉ đặc tả M03. Commit chứa nó không thêm workflow, không thêm CODEOWNERS, không đổi cài đặt repo, không đổi code, config, pin hay quyền. Chỉ triển khai sau khi có REVIEW_V1 PASS cho đúng SHA của bản đặc tả và chủ repo phê duyệt trực tiếp trong chat.

## 1. Thẩm quyền

- Roadmap [Issue #2](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/issues/2), mục "M03 — GitHub governance".
- M02 đã đóng ở phạm vi giới hạn và được merge vào `main` tại `cee197f` ngày 2026-10-09.
- Ngày 2026-10-09, trong chat Claude, chủ repo chọn "M03 governance (Khuyến nghị)". Mô tả của lựa chọn đó là: chỉ soạn spec để Reviewer xem và chủ repo duyệt trước khi triển khai. Chủ repo cũng chọn làm trên nhánh mới `claude/m03-github-governance`.
- Phân vai theo CLAUDE.md trên `main`:
  - LEAD (Claude Opus 5.5) soạn spec này.
  - REVIEWER (GPT-6.1 Sol) review với marker `REVIEW_V1`.
  - Chủ repo nghiệm thu và merge.

## 2. Mục tiêu

Mọi thay đổi vào `main` đi đúng một đường:

```text
branch -> commit -> PR -> CI xanh -> REVIEW_V1 tại HEAD của PR -> chủ repo duyệt -> merge
```

Thêm vào đó:
- CI tự chạy các kiểm tra offline đang chạy tay ở M01/M02, gồm cả các kiểm tra chỉ chạy được trên Windows.
- Các file quy tắc, chỉ mục và config luôn có chủ sở hữu rõ ràng.
- Có kiểm tra máy cho các điều kiện an toàn đã chốt. Ví dụ: mọi config Gateway đã commit giữ NotebookLM ở chế độ `disabled`, và `.mcp.json` ghim `notebooklm-mcp-cli==0.15.1` với đúng 4 tool đọc.

## 3. Hiện trạng tại `main` `cee197f`

| Hạng mục | Hiện trạng |
|---|---|
| Workflow CI (`.github/workflows/`) | Chưa có |
| `CODEOWNERS` | Chưa có |
| Ruleset / branch protection cho `main` | Chưa xác định được từ phía Claude: cài đặt repo không đọc được bằng công cụ hiện có. Repo đang `private` |
| PR template | Có (`.github/pull_request_template.md`), đã có khối `REVIEW_V1` |
| Bộ test M02 | 185 test, chạy tay bằng `scripts/m02/m02-tests.ps1` hoặc `uv run ... python -m unittest discover -s tests/m02 -p "test_gateway_*.py"`. Trên Linux có 8 test bỏ qua vì chỉ chạy trên Windows: 4 test junction/reparse và 4 test F14 suspended-start |
| Test M01 offline | `tests/m01/test_m01_10_llm_check.py` (12 test), `tests/m01/test_m01_console.py` (2 test) |
| Quét secret | `tests/m01/check_no_secrets.py`, quét theo tên file và mẫu chuỗi trên các file đã track (323 file tại `6eb2aed`). Docstring của script ghi: "Full secret scanning stays in M03" |
| Kiểm tra metadata | Có hàm nhưng chưa có lệnh gom lại: `gateway.schema.check()`, `gateway.index.load_index()`, `pilot_stage_b_v2_preflight.committed_configs_disabled()`, `server_pin_problems()` |
| Kiểm tra chạy thật với Claude Code (`m02_surface.py surface`/`llm`) | Cần đăng nhập Claude Code, chỉ chạy được trên máy chủ repo hoặc sandbox. Không đưa vào CI |

## 4. Sản phẩm M03

### D1. Ruleset cho nhánh `main`

Chủ repo tự áp dụng trong Settings của repo. Claude chỉ soạn danh sách thông số và cách kiểm tra.

Thông số đề xuất:
- Bắt buộc mọi thay đổi qua PR. Không push thẳng vào `main`.
- Bắt buộc các status check của D3 phải xanh: `ci / linux`, `ci / windows`, `ci / metadata`. Tên cuối cùng lấy theo tên job sau khi D3 đã merge.
- Chặn force push và chặn xóa nhánh `main`.
- Cho phép merge commit, vì repo đang dùng kiểu này cho PR #1, #5, #6, #7.
- Bắt buộc giải quyết hết hội thoại review trước khi merge.

**Điểm phải quyết (xem §8, mục 1):**
- Các PR hiện mở bằng chính tài khoản chủ repo (`tuvanxdbg-crypto`). GitHub không cho tác giả PR tự approve PR của mình. Nếu bật "Require approvals ≥ 1" thì mọi PR sẽ bị khóa, trừ khi có tài khoản thứ hai.
- Ruleset và branch protection cho repo private có thể đòi gói trả phí của GitHub `[cần kiểm tra trên trang Settings → Rules của repo]`.

### D2. `CODEOWNERS`

File `.github/CODEOWNERS` gán `@tuvanxdbg-crypto` cho toàn repo. Các đường dẫn có quy tắc an toàn được ghi riêng để dễ đọc:
- `CLAUDE.md`
- `.mcp.json`
- `.claude/`
- `config/`
- `.github/`
- `gateway/`
- `docs/m02-pilot/`
- `tests/m02/fixtures/`
- `tests/m01/fixtures/`

CODEOWNERS chỉ có tác dụng chặn khi ruleset bật "Require review from Code Owners". Điều này lại vướng đúng điểm tự approve ở D1. Khi đó CODEOWNERS vẫn có ích ở chỗ GitHub tự gắn người review và hiện rõ vùng nhạy cảm, nhưng không khóa được merge.

### D3. CI: `.github/workflows/ci.yml`

Kích hoạt khi có `pull_request` vào `main` và khi `push` vào `main`. Không dùng `pull_request_target`, không dùng `workflow_dispatch` có input.

| Job | Runner | Nội dung |
|---|---|---|
| `linux` | `ubuntu-latest` | Cài `uv` bằng action ghim theo SHA, chạy:<br>- bộ test M02 (`--exclude-newer 2026-10-03T00:00:00Z`, `pyyaml==6.0.2`, Python 3.11);<br>- 2 file test M01 offline;<br>- `check_no_secrets.py`. |
| `windows` | `windows-latest` | Bộ test M02 đầy đủ, để 8 test chỉ dành cho Windows được chạy thật. Đây là nơi duy nhất ngoài máy chủ repo chạy được job object và `CREATE_SUSPENDED` |
| `metadata` | `ubuntu-latest` | Script D5 |

Ràng buộc cho mọi job:
- `permissions: contents: read`, không cấp thêm quyền nào.
- Không dùng secret của repo.
- Không gọi NotebookLM, không đăng nhập, không chạy `m02_surface.py`.
- Mọi action ghim theo commit SHA đầy đủ, không ghim theo tag.
- `timeout-minutes: 15` cho mỗi job.
- `concurrency` theo nhánh, hủy lần chạy cũ khi có push mới.

Repo private dùng phút Actions có giới hạn theo gói, và runner Windows tính phút cao hơn Linux `[cần kiểm tra hạn mức trên trang Billing]`. Ước tính từ các lần chạy đã ghi ở M02 (185 test mất khoảng 50 giây trên Linux, 85 giây trên Windows): mỗi lần chạy khoảng 3-6 phút thực, chưa tính thời gian cài `uv` và Python.

### D4. Quét secret

Hai lớp:
1. **Trong CI:** chạy `check_no_secrets.py` ở job `linux`, như đã làm tay từ M01.
2. **Phía GitHub:**
   - Bật secret scanning và push protection nếu gói tài khoản cho phép với repo private `[cần kiểm tra trên trang Settings → Code security]`.
   - Nếu gói không cho phép, ghi rõ trong tài liệu nghiệm thu là lớp 2 chưa có. Không thay bằng công cụ bên thứ ba khi chưa được duyệt riêng.

Không thêm công cụ quét mới trong M03. Lý do: đó là một phụ thuộc mới và cần review riêng.

### D5. Kiểm tra metadata: `tests/m03/validate_repo_metadata.py`

Chỉ dùng thư viện chuẩn, PyYAML và code `gateway/` sẵn có. Không mạng, không đọc thư viện tài liệu local. Kiểm tra:

| Mã | Điều kiện đạt |
|---|---|
| `GATEWAY_CONFIGS_VALID_AND_DISABLED` | Mọi file JSON đã track có `schema: tvxd.gateway.config/v1`: hợp lệ theo `config.v1.json`, và có `notebooklm.mode` là `disabled`. Hiện có 4 file: `tests/m02/fixtures/gateway.fixture.json` và 3 file `docs/m02-pilot/gateway.pilot.*.json` |
| `INDEX_FILES_VALID` | Mọi `INDEX*.yaml` đã track nạp được bằng `load_index()` mà không lỗi. Riêng `INDEX.pilot.template.yaml` phải thất bại đúng như thiết kế, vì template cố ý fail closed |
| `M01_SERVER_PIN` | `.mcp.json` khởi động `gemini-notebook-mcp` bằng `uvx --from notebooklm-mcp-cli==0.15.1` và bật đúng 4 tool đọc. Dùng lại `server_pin_problems()` |
| `M01_POLICY_CONSISTENT` | Danh sách tool cho phép trong `config/m01-tool-policy.yaml` và trong `.claude/settings.json` trùng đúng 4 tool của `NOTEBOOKLM_ENABLED_TOOLS` |
| `GATEWAY_NOT_IN_PROJECT_MCP` | `.mcp.json` không có server `tvxd-standards-gateway`. Đây là quy tắc trong CLAUDE.md |
| `SCHEMAS_PARSE` | Mọi file `gateway/schemas/*.json` là JSON hợp lệ và có `$id` hoặc `title` |

Mỗi mã có một test âm (negative control) trong `tests/m03/test_validate_repo_metadata.py`. Test làm việc trên bản sao tạm, cố ý làm hỏng đúng điều kiện đó rồi khẳng định script báo FAIL.

### D6. Duyệt thay đổi quy tắc và chỉ mục

Cập nhật PR template với một mục "Vùng nhạy cảm bị sửa". Người mở PR đánh dấu nếu PR sửa:
- `CLAUDE.md`, `.mcp.json`, `.claude/`, `config/`;
- INDEX hoặc mapping;
- `.github/`.

PR như vậy phải có REVIEW_V1 tại đúng HEAD và chủ repo duyệt trực tiếp. M03 không thêm cơ chế tự động nào để đọc comment review, vì việc đó cần token có quyền đọc PR và không cần thiết ở quy mô hiện tại.

### D7. Quy trình REVIEW_V1

Giữ đúng mục "Phan vai" trong CLAUDE.md trên `main`:
- Review mới dùng `REVIEW_V1`, kèm `REVIEWER_MODEL` và `REVIEWED_COMMIT`.
- Review chỉ hợp lệ khi `REVIEWED_COMMIT` bằng HEAD hiện tại của PR.
- PASS của Reviewer không thay cho nghiệm thu và merge của chủ repo.

M03 chỉ thêm một tài liệu ngắn `docs/REVIEW_PROCESS.md`, viết lại trình tự từ mục 2 của spec này kèm ví dụ khối `REVIEW_V1` đầy đủ. Không đổi quy tắc trong CLAUDE.md.

### D8. Cổng regression

Đạt được khi D1 bắt buộc 3 status check của D3. Lúc đó:
- một test M02 hay M01 bị đỏ sẽ chặn merge;
- một config bị bật `mcp_stdio`, hoặc pin bị đổi, sẽ làm job `metadata` đỏ và chặn merge.

## 5. Ràng buộc trong toàn bộ M03

- Theo Issue #2: không workflow GitHub nào được điều khiển máy trạm AutoCAD hoặc giữ cookie trình duyệt NotebookLM.
- Không self-hosted runner. Không secret của repo. Không auto-merge.
- Claude không tự đổi cài đặt repo (ruleset, secret scanning, quyền, collaborator). Chủ repo làm các việc đó.
- Không đổi quy tắc M01/M02, pin, config đã commit, phạm vi nguồn hay notebook.
- Mọi config Gateway đã commit giữ `notebooklm.mode: disabled`.
- Không M04/M05/M06, không AutoCAD.

## 6. Thứ tự triển khai đề xuất (sau khi spec được duyệt)

1. **M03-A, trên nhánh này:**
   - Nội dung: D2, D3, D5 (script và test), D6 (PR template), D7 (`docs/REVIEW_PROCESS.md`).
   - Kiểm tra: chạy CI ngay trên PR nháp để thấy 3 job xanh. Thêm một commit thử cố ý làm đỏ từng job, để chứng minh check chặn được, rồi revert.
   - Duyệt: REVIEW_V1 tại HEAD, chủ repo duyệt merge.
2. **M03-B, chủ repo làm trên GitHub sau khi M03-A merge:**
   - Áp dụng ruleset D1 với tên status check đúng như CI đã chạy.
   - Bật D4 lớp 2 nếu gói cho phép.
   - Gửi lại cho Claude bản export JSON của ruleset (Settings → Rules → Export) hoặc ảnh chụp màn hình để ghi evidence.
3. **M03-C, kiểm chứng:**
   - Một PR thử nhỏ, chỉ sửa tài liệu, để thấy check bắt buộc hiện ra và chặn merge khi đỏ.
   - Thử push thẳng vào `main` và force push: phải bị từ chối. Chủ repo làm và gửi output.
   - Ghi evidence và chốt nghiệm thu M03.

## 7. Nghiệm thu M03

Theo CLAUDE.md, mỗi mốc nghiệm thu phải ghi đủ: mục tiêu, evidence yêu cầu, điều kiện đạt, người duyệt.

| Mốc | Mục tiêu | Evidence yêu cầu | Điều kiện đạt | Người duyệt |
|---|---|---|---|---|
| M03-A | CI, CODEOWNERS, script metadata, PR template, tài liệu quy trình | Link 3 lần chạy CI xanh trên HEAD của PR; link các lần chạy đỏ có chủ đích (mỗi job một lần); output test âm của D5 | 3 job xanh trên HEAD; mỗi job từng đỏ đúng một lần khi cố ý làm hỏng; D5 có đủ 6 test âm | REVIEW_V1 tại HEAD, chủ repo |
| M03-B | Ruleset trên `main`, secret scanning nếu có | Export JSON hoặc ảnh chụp ruleset; ảnh chụp trang Code security | Đủ các thông số D1 đã chốt; lớp 2 của D4 bật, hoặc được ghi rõ là không khả dụng | Chủ repo |
| M03-C | Ruleset thực sự chặn | Output của push thẳng và force push bị từ chối; PR thử bị chặn khi check đỏ | Cả 3 tình huống đều bị chặn | REVIEW_V1 tại HEAD evidence, chủ repo |

## 8. Thông tin cần chủ repo quyết định (MISSING_OWNER_INPUTS)

1. **Approval bắt buộc trên PR.** Chọn một:
   - (a) Không bắt buộc approval. Merge do chính chủ repo bấm được coi là duyệt. Check CI vẫn bắt buộc.
   - (b) Thêm một tài khoản thứ hai làm reviewer trên GitHub.

   Claude đề xuất (a) cho quy mô hiện tại.
2. **Gói tài khoản GitHub.** Ruleset và secret scanning cho repo private có khả dụng không? Kiểm tra trên trang Settings của repo.
3. **Runner Windows.** Có chấp nhận dùng phút Actions cho job `windows` ở mọi PR không? Hay chỉ chạy khi PR sửa `gateway/` hoặc `tests/m02/`?
4. **Áp dụng cho admin.** Ruleset có áp dụng cả với tài khoản chủ repo không (không có bypass)? Claude đề xuất có áp dụng, để không ai push thẳng vào `main`.

## 9. Chưa được phép theo spec này

Tạo workflow, CODEOWNERS hay script trước khi spec được duyệt; đổi cài đặt repo; merge; chạy live; đăng nhập; đổi nguồn, notebook, scope, config, pin, ACL, credential hoặc quyền; M04 trở đi; AutoCAD.
