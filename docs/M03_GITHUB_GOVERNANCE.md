# M03 GitHub governance: đặc tả

**Trạng thái: ĐÃ DUYỆT.** REVIEW_V1 PASS và chủ repo phê duyệt trực tiếp tại `a2e8362` ngày 2026-10-09. M03-A đã triển khai và merge vào `main` tại `d1b65aa` (PR #8). M03-B và M03-C theo §6 và §7. Mọi sửa đổi spec về sau phải có REVIEW_V1 tại đúng SHA và chủ repo phê duyệt.

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
branch -> commit -> PR -> cập nhật theo main -> CI xanh -> REVIEW_V1 tại HEAD của PR -> chủ repo duyệt -> merge
```

HEAD của PR đổi vì bất kỳ lý do gì thì phải chạy lại cả 3 job CI và có REVIEW_V1 mới tại SHA mới. Lý do có thể là commit mới, hoặc merge/rebase theo `main`. Review ở SHA cũ là STALE, đúng quy tắc trong CLAUDE.md.

Thêm vào đó:
- CI tự chạy các kiểm tra offline đang chạy tay ở M01/M02, gồm cả các kiểm tra chỉ chạy được trên Windows.
- Các file quy tắc, chỉ mục và config luôn có chủ sở hữu rõ ràng.
- Có kiểm tra máy cho các điều kiện an toàn đã chốt. Ví dụ: mọi config Gateway đã commit giữ NotebookLM ở chế độ `disabled`, và `.mcp.json` ghim `notebooklm-mcp-cli==0.15.1` với đúng 4 tool đọc.

## 3. Hiện trạng tại `main` `cee197f`

| Hạng mục | Hiện trạng |
|---|---|
| Workflow CI (`.github/workflows/`) | Chưa có |
| `CODEOWNERS` | Chưa có |
| Ruleset / branch protection cho `main` | Chưa xác định được từ phía Claude: cài đặt repo không đọc được bằng công cụ hiện có. Repo `private` tại `cee197f`; chủ repo chuyển sang `public` ngày 2026-10-09 (§8) |
| PR template | Có (`.github/pull_request_template.md`), đã có khối `REVIEW_V1` |
| Bộ test M02 | 185 test, chạy tay bằng `scripts/m02/m02-tests.ps1` hoặc `uv run ... python -m unittest discover -s tests/m02 -p "test_gateway_*.py"`. Trên Linux có 8 test bỏ qua vì chỉ chạy trên Windows: 4 test junction/reparse và 4 test F14 suspended-start |
| Test M01 offline | `tests/m01/test_m01_10_llm_check.py` (12 test), `tests/m01/test_m01_console.py` (2 test) |
| Quét secret | `tests/m01/check_no_secrets.py`, quét theo tên file và mẫu chuỗi trên các file đã track (323 file tại `6eb2aed`). Script lấy danh sách bằng `git ls-files` rồi đọc file ở working tree, nên chỉ quét cây hiện tại. Nó không quét commit cũ hay file đã xóa trong lịch sử. Docstring của script ghi: "Minimal local check" và "Full secret scanning stays in M03" |
| Kiểm tra metadata | Có hàm nhưng chưa có lệnh gom lại: `gateway.schema.check()`, `gateway.index.load_index()`, `pilot_stage_b_v2_preflight.committed_configs_disabled()`, `server_pin_problems()` |
| Kiểm tra chạy thật với Claude Code (`m02_surface.py surface`/`llm`) | Cần đăng nhập Claude Code, chỉ chạy được trên máy chủ repo hoặc sandbox. Không đưa vào CI |

## 4. Sản phẩm M03

### D1. Ruleset cho nhánh `main`

Chủ repo tự áp dụng trong Settings của repo. Claude chỉ soạn danh sách thông số và cách kiểm tra.

Thông số đề xuất:
- Bắt buộc mọi thay đổi qua PR. Không push thẳng vào `main`.
- Bắt buộc các status check của D3 phải xanh: `ci / linux`, `ci / windows`, `ci / metadata`. Tên cuối cùng lấy theo tên job sau khi D3 đã merge.
- **Status check ở chế độ strict:** bật "Require branches to be up to date before merging". Ở chế độ loose, nhánh PR không cần chứa commit mới nhất của `main`. Khi đó check xanh có thể đã chạy trên một base cũ, và không còn đại diện cho kết quả sau merge, nhất là khi một PR khác vừa merge trước. Ở chế độ strict, GitHub chặn merge cho đến khi nhánh PR đã cập nhật theo `main`.
- **Sau mỗi lần cập nhật base:**
  - nhánh PR merge `main` vào (repo này dùng merge commit; rebase chỉ trên nhánh do người đó tạo);
  - chạy lại đủ 3 job trên HEAD mới;
  - vì HEAD đã đổi, cần REVIEW_V1 mới tại SHA mới trước khi chủ repo merge.
- Chặn force push và chặn xóa nhánh `main`.
- Cho phép merge commit, vì repo đang dùng kiểu này cho PR #1, #5, #6, #7.
- Bắt buộc giải quyết hết hội thoại review trước khi merge.
- **Không bắt buộc approval** (quyết định §8, mục 1). Lý do: các PR mở bằng chính tài khoản chủ repo (`tuvanxdbg-crypto`), mà GitHub không cho tác giả PR tự approve. Việc chủ repo tự bấm merge, sau REVIEW_V1 PASS tại HEAD, được coi là bước duyệt.
- **Không có bypass, kể cả admin** (quyết định §8, mục 4). Tài khoản chủ repo cũng không push thẳng hay force push vào `main` được.
- Repo đã chuyển sang public (quyết định §8, mục 2), nên ruleset dùng được mà không cần gói trả phí.

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

CODEOWNERS chỉ có tác dụng chặn khi ruleset bật "Require review from Code Owners". Theo quyết định không bắt buộc approval ở D1, ruleset sẽ không bật mục này. CODEOWNERS vẫn có ích ở chỗ GitHub tự gắn người review và hiện rõ vùng nhạy cảm, nhưng không khóa được merge.

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

Job `windows` chạy ở mọi PR (quyết định §8, mục 3). Repo giờ là public, nên phút runner chuẩn của GitHub không còn là ràng buộc chính. Ước tính từ các lần chạy đã ghi ở M02 (185 test mất khoảng 50 giây trên Linux, 85 giây trên Windows): mỗi lần chạy khoảng 3-6 phút thực, chưa tính thời gian cài `uv` và Python.

Repo public nên PR có thể đến từ fork của người khác. Với trigger `pull_request`, GitHub chạy workflow của fork bằng token chỉ đọc và không cấp secret. Spec giữ đúng mô hình này. Không dùng `pull_request_target`, vì trigger đó chạy code của fork với quyền của repo gốc.

**Cổng phê duyệt workflow của fork.** Với PR từ fork của người đóng góp mới, GitHub có thể giữ workflow ở trạng thái chờ maintainer phê duyệt. Khi đó các job chưa chạy và các required check ở trạng thái pending. Câu "job `windows` chạy ở mọi PR" nghĩa là mọi PR đều phải có đủ 3 check xanh trước khi merge. Nó không có nghĩa là bỏ lớp phê duyệt này.
- Chủ repo giữ cài đặt phê duyệt workflow của fork (Settings → Actions → General) ở mức mặc định hoặc chặt hơn. Không nới lỏng chỉ để mọi PR tự chạy.
- Trước khi bấm phê duyệt cho một lần chạy, chủ repo đọc diff của PR. Đặc biệt xem các file trong `.github/`, script, test và mọi thay đổi có gọi mạng hoặc cài thêm gói. Nếu PR sửa `.github/workflows/` hoặc có thay đổi đáng ngờ thì không phê duyệt, mà ghi lý do vào PR.
- Khi ghi nghiệm thu hay báo cáo CI, phân biệt 3 trạng thái:
  - đang chờ maintainer phê duyệt (chưa chạy);
  - đã chạy và đỏ (CI failure);
  - không có check (thiếu check, ví dụ do sai tên job).
  Chỉ trạng thái thứ hai được tính là CI failure.

### D4. Quét secret

Hai lớp:
1. **Trong CI:** chạy `check_no_secrets.py` ở job `linux`, như đã làm tay từ M01. Lớp này chỉ bảo vệ cây hiện tại của mỗi commit, không quét lịch sử.
2. **Phía GitHub:**
   - Bật secret scanning và push protection trong Settings → Code security. Repo đã public nên hai tính năng này dùng được.
   - Theo tài liệu GitHub, secret scanning quét toàn bộ lịch sử Git của repo. Đây là lớp duy nhất trong M03 phủ được lịch sử đã công khai.
   - Mọi alert phải được chủ repo xử lý: thu hồi hoặc đổi (rotate) credential ở nhà cung cấp trước, rồi mới đóng alert. Đóng alert mà không rotate thì không tính là đã xử lý, vì lịch sử đã public.
   - Nếu trang Settings không hiện các tùy chọn này, ghi rõ trong tài liệu nghiệm thu là lớp 2 chưa có. Không thay bằng công cụ bên thứ ba khi chưa được duyệt riêng.

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
   - Bật D4 lớp 2.
   - Xem trang Security → Secret scanning của repo sau khi bật. Xác nhận lần quét lịch sử đã xong, và xử lý mọi alert theo D4. Nếu GitHub không cung cấp chỉ báo chính thức cho lần quét lịch sử, áp dụng tiêu chí thay thế ở §7a.
   - Gửi lại cho Claude để ghi evidence:
     - bản export JSON của ruleset (Settings → Rules → Export) hoặc ảnh chụp màn hình, trong đó thấy chế độ strict;
     - ảnh chụp trang Code security và trang danh sách alert secret scanning (gồm cả alert đã đóng);
     - ảnh chụp cài đặt phê duyệt workflow của fork.
     Ảnh chụp không được để lộ giá trị secret. Nếu có alert, chỉ ghi loại secret, đường dẫn file, commit và cách đã xử lý.
3. **M03-C, kiểm chứng:**
   - Một PR thử nhỏ, chỉ sửa tài liệu, để thấy check bắt buộc hiện ra và chặn merge khi đỏ.
   - Chính PR thử đó, khi `main` đã có commit mới mà nhánh chưa cập nhật: phải bị chặn merge vì chế độ strict.
   - Thử push thẳng vào `main` và force push: phải bị từ chối. Chủ repo làm và gửi output.
   - Ghi evidence và chốt nghiệm thu M03.

## 7. Nghiệm thu M03

Theo CLAUDE.md, mỗi mốc nghiệm thu phải ghi đủ: mục tiêu, evidence yêu cầu, điều kiện đạt, người duyệt.

| Mốc | Mục tiêu | Evidence yêu cầu | Điều kiện đạt | Người duyệt |
|---|---|---|---|---|
| M03-A | CI, CODEOWNERS, script metadata, PR template, tài liệu quy trình | Link 3 lần chạy CI xanh trên HEAD của PR; link các lần chạy đỏ có chủ đích (mỗi job một lần); output test âm của D5 | 3 job xanh trên HEAD; mỗi job từng đỏ đúng một lần khi cố ý làm hỏng; D5 có đủ 6 test âm | REVIEW_V1 tại HEAD, chủ repo |
| M03-B | Ruleset trên `main`, secret scanning, cổng phê duyệt fork | Export JSON hoặc ảnh chụp ruleset; ảnh chụp trang Code security; ảnh chụp danh sách alert secret scanning (mở và đã đóng); ảnh chụp cài đặt phê duyệt workflow của fork | Đủ các thông số D1 đã chốt, kể cả strict. Lớp 2 của D4 bật, lần quét lịch sử đã xong, và mọi alert đã được rotate/thu hồi rồi mới đóng. Nếu không xác nhận được lần quét lịch sử hoặc không đọc được alert, ghi trạng thái là `CHƯA KIỂM CHỨNG` và M03-B không được ghi PASS. Ngoại lệ duy nhất: điều kiện "lần quét lịch sử đã xong" được thay bằng tiêu chí ở §7a khi đủ điều kiện áp dụng của §7a. Cài đặt fork ở mức mặc định hoặc chặt hơn | Chủ repo |
| M03-C | Ruleset thực sự chặn | Output của push thẳng và force push bị từ chối; PR thử bị chặn khi check đỏ; PR thử bị chặn khi nhánh chậm hơn `main` | Cả 4 tình huống đều bị chặn | REVIEW_V1 tại HEAD evidence, chủ repo |

### 7a. Tiêu chí thay thế cho điều kiện "lần quét lịch sử đã xong" (sửa đổi A1)

**Thẩm quyền.** Chủ repo quyết định trong chat Claude ngày 2026-10-09, nguyên văn: "Tôi quyết định chấp nhận tiêu chí thay thế cho điều kiện quét lịch sử secret ở §7 và cho phép soạn bản sửa đổi spec M03." Sửa đổi này chỉ có hiệu lực sau khi có REVIEW_V1 PASS tại đúng SHA chứa nó và chủ repo phê duyệt trực tiếp đúng SHA đó.

**Lý do.**
- Endpoint chính thức duy nhất cho biết trạng thái quét là `GET /repos/{owner}/{repo}/secret-scanning/scan-history`, trả về `backfill_scans`. Theo tài liệu REST của GitHub, endpoint này "requires GitHub Advanced Security".
- Repo này là repo public, dùng Secret Protection miễn phí, không có GitHub Advanced Security. Khi gọi thật, endpoint trả HTTP 404 "Advanced Security is disabled on this repository" (evidence M03-B, `gh-api-secret-scanning-console.txt`).
- Giao diện cũng không có chỉ báo nào cho biết lần quét lịch sử đã xong. Vì vậy, với cấu hình này, điều kiện gốc ở §7 không bao giờ thỏa được.

**Điều kiện áp dụng.** Chỉ dùng §7a khi đồng thời:
1. repo là public và không bật GitHub Advanced Security;
2. đã gọi `scan-history` bằng tài khoản chủ repo và nhận lỗi cho thấy endpoint không dùng được trên repo (ghi nguyên văn lỗi vào evidence).

Nếu sau này repo bật GitHub Advanced Security, hoặc `scan-history` dùng được, thì quay về điều kiện gốc: phải có một `backfill_scans` loại `git` với `status: completed`.

**Tiêu chí thay thế.** Phải đạt **tất cả**:

| # | Tiêu chí | Evidence |
|---|---|---|
| A1-1 | Secret Protection và Push protection đang bật | Ảnh chụp Settings → Advanced Security |
| A1-2 | Lần đọc alert thứ nhất, sau khi bật Secret Protection, **đọc hết mọi trang** theo "Cách đọc alert" bên dưới: 0 alert `open`; mọi alert `resolved` (nếu có) có evidence theo từng alert như mục "Evidence theo từng alert" | Ảnh trang Secret scanning (Open và Closed) **và** output nguyên văn của lệnh REST API đọc hết mọi trang, gọi bằng tài khoản chủ repo |
| A1-3 | Lần đọc thứ hai, **ít nhất 24 giờ sau khi bật Secret Protection**, bằng cùng cách đọc hết mọi trang như A1-2: vẫn 0 alert `open`; mọi alert `resolved` (gồm cả alert mới xuất hiện từ lần đọc thứ nhất) có evidence theo từng alert | Output nguyên văn, kèm thời điểm chạy (UTC+7) và thời điểm bật Secret Protection |
| A1-4 | Lời gọi `scan-history` và lỗi trả về được ghi nguyên văn | Output nguyên văn |

**Cách đọc alert (A1-2 và A1-3).** Endpoint `GET /repos/{owner}/{repo}/secret-scanning/alerts` có phân trang (tham số `page`, `per_page`, `before`, `after`). Một trang response không đủ để kết luận "mọi alert". Mỗi lần đọc phải:
- gọi riêng `state=open` và `state=resolved`, luôn kèm `hide_secret=true`;
- đọc hết mọi trang, ví dụ bằng GitHub CLI `gh api --paginate`, với `per_page=100`;
- in một dòng cho mỗi alert, chỉ gồm các trường không nhạy cảm: `number`, `state`, `secret_type`, `resolution`, `resolved_at`. Ví dụ:
  ```text
  gh api --paginate "repos/tuvanxdbg-crypto/TVXD-AI-STANDARDS/secret-scanning/alerts?state=resolved&hide_secret=true&per_page=100" --jq ".[] | [.number, .state, .secret_type, .resolution, .resolved_at] | @tsv"
  ```
  Số alert là số dòng in ra. Output rỗng nghĩa là 0 alert ở trạng thái đó trên mọi trang. Không dùng `--jq "length"` không kèm `--paginate`, vì cách đó chỉ đếm một trang.

**Evidence theo từng alert khi có alert `resolved`.** Nếu một lần đọc có ít nhất một alert `resolved`, thì với **từng** alert phải có evidence đã khử nhạy cảm:
- số alert (`number`), loại secret (`secret_type`), `resolution` và `resolved_at`;
- vị trí: `path` và `commit_sha`, lấy từ `GET /repos/{owner}/{repo}/secret-scanning/alerts/{alert_number}/locations` (cũng đọc hết mọi trang);
- xác nhận của chủ repo rằng credential đã được rotate hoặc thu hồi ở nhà cung cấp **trước** thời điểm `resolved_at`: tên nhà cung cấp, cách làm (rotate hay thu hồi), thời điểm, và mã tham chiếu phía nhà cung cấp nếu có (ví dụ ID của khóa đã thu hồi). Nếu alert bị đóng là `false_positive` hoặc `used_in_tests`, ghi lý do kiểm chứng thay cho rotate;
- **tuyệt đối không ghi giá trị secret**, cũng không ghi đoạn văn bản chứa secret.

Thiếu evidence cho bất kỳ alert `resolved` nào thì tiêu chí đó không đạt. Số đếm một mình không đủ.

Mốc 24 giờ là một biện pháp bù do LEAD đề xuất. Tài liệu GitHub không công bố thời gian một lần quét lịch sử. Mốc này chỉ để có thêm một lần đọc cách xa thời điểm bật, chứ không chứng minh lần quét đã xong.

**Cách ghi trạng thái.**
- Khi đạt đủ A1-1 đến A1-4, hạng mục D4 lịch sử được ghi là **`ĐẠT THEO TIÊU CHÍ THAY THẾ (A1)`**. Không ghi là "lần quét lịch sử đã xong".
- Evidence phải giữ một câu giới hạn: tiêu chí A1 không chứng minh GitHub đã quét xong toàn bộ lịch sử. Nó chỉ cho thấy không có alert nào trong hai lần đọc cách nhau ít nhất 24 giờ.
- Nếu thiếu một tiêu chí, hạng mục vẫn là `CHƯA KIỂM CHỨNG` và M03-B không được ghi PASS.
- Các phần khác của M03-B (D1, D3, rotate trước khi đóng alert) giữ nguyên như §7.

**Rủi ro còn lại, được chấp nhận theo quyết định của chủ repo:** nếu lần quét lịch sử chưa xong ở cả hai lần đọc, một secret cũ trong lịch sử có thể chưa được phát hiện. Khi đó GitHub sẽ tạo alert sau, và chủ repo phải xử lý theo D4 (rotate trước, rồi đóng), kể cả sau khi M03 đã đóng.

## 8. Quyết định của chủ repo

Chủ repo trả lời trong chat Claude ngày 2026-10-09, nguyên văn: "1. Không bắt buộc approval. 2. tôi đã chuyển sang public. 3 có chạy. 4 có".

| # | Câu hỏi | Quyết định | Ảnh hưởng tới spec |
|---|---|---|---|
| 1 | Có bắt buộc approval trên PR không | Không | D1 không bật "Require approvals" và không bật "Require review from Code Owners". CI vẫn bắt buộc |
| 2 | Gói GitHub có hỗ trợ ruleset và secret scanning cho repo private không | Repo đã chuyển sang public | D1 và D4 lớp 2 dùng được. D3 không còn bị giới hạn phút. Có thêm rủi ro, ghi ở §8a |
| 3 | Có chạy runner Windows ở mọi PR không | Có | Job `windows` chạy ở mọi PR vào `main` |
| 4 | Ruleset có áp dụng cả với tài khoản admin không | Có | Không có danh sách bypass |

### 8a. Hệ quả của việc chuyển sang public

Lịch sử Git giờ ai cũng đọc được, gồm cả các commit cũ. Rà nhanh trên nhánh này tại `aa973cb`:
- **Secret: chỉ kiểm được cây hiện tại.** `tests/m01/check_no_secrets.py` PASS, nghĩa là không phát hiện secret trong cây file đã track tại `aa973cb`, theo các mẫu của M01-09. Không có địa chỉ email trong các file đó; các chuỗi "gmail" chỉ là tên plugin trong evidence. Kết quả này **không** chứng minh lịch sử Git không có secret: script không quét commit cũ hay file đã xóa. Lịch sử đã công khai vẫn ở trạng thái `CHƯA KIỂM CHỨNG` cho đến khi GitHub secret scanning quét xong toàn bộ lịch sử và chủ repo xử lý mọi alert (D4, M03-B), hoặc đến khi đạt tiêu chí thay thế ở §7a.
- **Email trong metadata commit.** Trường author/committer của 13 commit chứa email Gmail cá nhân của chủ repo, và 1 commit chứa một email máy cục bộ dạng `@tvxd.local`. Các commit còn lại dùng `noreply@anthropic.com` hoặc `noreply@github.com`. Đây là metadata Git, không nằm trong file nên lớp quét file không thấy. Với commit mới, chủ repo có thể bật "Keep my email addresses private" và "Block command line pushes that expose my email" trong cài đặt email của tài khoản GitHub, rồi đặt `git config user.email` thành địa chỉ noreply mà GitHub cấp. Đây là cài đặt tài khoản, nằm ngoài M03.
- **Định danh hạ tầng công khai.** Đường dẫn có tên tài khoản Windows `ducdq.tvxdbg` xuất hiện trong 7 file evidence. Notebook ID `8ca84143-…` và các source ID xuất hiện trong 50 file đã track (35 file evidence M02, 15 file code, fixture và tài liệu). Những ID này không phải secret: muốn đọc notebook vẫn cần đăng nhập và quyền chia sẻ. Tuy vậy, chúng cho người ngoài biết cấu trúc hệ thống.
- **Nội dung tài liệu không có trong repo.** Không có PDF tiêu chuẩn, không có văn bản nguồn hay transcript thô. Evidence chỉ ghi ID, mã trạng thái, số đếm và thời gian, đúng quy tắc từ M01.

Spec không đề xuất viết lại lịch sử Git để xóa các định danh trên. Nếu chủ repo muốn ẩn chúng, đó là một quyết định riêng, cần review riêng.

## 9. Chưa được phép theo spec này

Tạo workflow, CODEOWNERS hay script trước khi spec được duyệt; đổi cài đặt repo; merge; chạy live; đăng nhập; đổi nguồn, notebook, scope, config, pin, ACL, credential hoặc quyền; M04 trở đi; AutoCAD.
