# M03-A: evidence CI trên GitHub Actions (2026-10-09)

## Bối cảnh

- **Spec:** `docs/M03_GITHUB_GOVERNANCE.md`, có REVIEW_V1 PASS tại `a2e8362fa49585b2dda05666ed14cfe19c006560` (review 5465559512).
- **Phê duyệt của chủ repo:** trong chat Claude ngày 2026-10-09, nguyên văn: "Tôi phê duyệt đặc tả M03 (docs/M03_GITHUB_GOVERNANCE.md) tại commit a2e8362fa49585b2dda05666ed14cfe19c006560 và cho phép triển khai M03-A theo §6".
- **Phạm vi M03-A:** D2, D3, D5, D6, D7. Chưa có ruleset (M03-B), nên lúc này check đỏ chưa chặn merge. Evidence dưới đây chỉ chứng minh từng job xanh khi code đúng và đỏ khi bị làm hỏng.
- **Workflow:** `.github/workflows/ci.yml`, tên `ci`. Tên check run GitHub tạo ra là `linux`, `windows`, `metadata`; giao diện PR hiện thành `ci / linux`, `ci / windows`, `ci / metadata`. M03-B phải chọn đúng các check này làm required check.
- Mọi lần chạy dưới đây đều do sự kiện `pull_request` của PR #8 kích hoạt. Không có secret, token chỉ đọc (`contents: read`), không gọi NotebookLM.

## Các lần chạy

Thời điểm lấy từ GitHub, giữ nguyên UTC; cột cuối là giờ UTC+7.

| # | Commit | Run | `linux` | `windows` | `metadata` | Bắt đầu (UTC) | UTC+7 |
|---|---|---|---|---|---|---|---|
| 1 | `5e553bc5486d6bb418ef0af2136e3c3de88ee98b` (M03-A) | [37882432278](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/actions/runs/37882432278) | success | **failure** (lỗi thật, xem dưới) | success | 2026-10-09T04:07:50Z | 2026-10-09 11:07 +07:00 |
| 2 | `c7d8f2a6b17e329197afbe12406063584723c451` (sửa lỗi khác ổ đĩa) | [37882681196](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/actions/runs/37882681196) | success | success | success | 2026-10-09T04:11:07Z | 2026-10-09 11:11 +07:00 |
| 3 | `eae70f644f79a03c4a4f04777541bfac4e0267dd` (cố ý làm đỏ) | [37882823264](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/actions/runs/37882823264) | **failure** (cố ý) | **failure** (cố ý) | **failure** (cố ý) | 2026-10-09T04:13:01Z (job `windows`) | 2026-10-09 11:13 +07:00 |
| 4 | `00bd2b81aac53a5c57473dcca1f44c76f1fcfad9` (revert lần 3) | [37882944571](https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS/actions/runs/37882944571) | success | success | success | 2026-10-09T04:14:38Z | 2026-10-09 11:14 +07:00 |

Job ID: lần 1: linux 113664888369, windows 113664888174, metadata 113664888288. Lần 2: linux 113665682107, windows 113665681961, metadata 113665682242. Lần 3: linux 113666139111, windows 113666138865, metadata 113666139095. Lần 4: linux 113666527174, windows 113666526917, metadata 113666527098.

Commit chứa file này tạo thêm một lần chạy nữa. Kết quả của lần đó được ghi trong báo cáo trên PR #8, vì file không thể tự ghi kết quả CI của chính commit chứa nó.

## Lần 1: lỗi thật trên `windows`

- 3 test `TemporaryFakeBackend` trong `tests/m02/test_gateway_surface_harness.py` báo ERROR với `ValueError: Paths don't have the same drive`.
- Nguyên nhân nằm ở `tests/m02/m02_surface.py` `build_fake_backend()`. Hàm này dùng `os.path.commonpath` để kiểm tra rằng config tạm nằm ngoài repo. Trên runner, thư mục tạm ở `C:` còn repo ở `D:\a\...`, và `commonpath` báo lỗi khi hai đường dẫn khác ổ.
- Trên máy chủ repo, cả hai cùng ở `C:`, nên lỗi này chưa từng xuất hiện trong các lần chạy M02.
- **Sửa ở commit 2:** thêm hàm `inside()`, coi hai đường dẫn khác ổ là "nằm ngoài", kèm test hồi quy `test_other_drive_counts_as_outside` (giả lập `ValueError`).
- Chỉ sửa harness test. Không đổi code Gateway, config, pin hay quyền. Bộ test M02 từ 185 lên 186 test.

## Lần 2 và lần 4: xanh

- `linux`: M02 186 test OK (bỏ qua 8 test chỉ dành cho Windows); M01-10 checker 12 test OK; console encoding 2 test OK; M01-09 secret scan PASS (chỉ cây file hiện tại).
- `windows`: M02 186 test OK, chỉ bỏ qua 2 test: test symlink dành cho POSIX trong `test_gateway_core.py` và test đọc `/proc` dành cho Linux. Như vậy 4 test junction/reparse và 4 test F14 suspended-start (job object, `CREATE_SUSPENDED`) đã chạy thật trên Windows.
- `metadata`: `validate_repo_metadata.py` PASS cả 6 kiểm tra; 17 test D5 OK.

## Lần 3: cố ý làm đỏ

Commit `eae70f6` thêm hai thứ, rồi bị revert ở commit `00bd2b8`:
- `tests/m02/test_gateway_ci_red_control.py`: một test luôn fail.
- `tests/m03/ci-red/INDEX.ci-red.yaml`: một INDEX YAML hỏng.

Kết quả, đã đọc log từng job:
- `linux`: `FAILED (failures=1, skipped=8)`. Test duy nhất fail là `test_deliberate_failure`.
- `windows`: `FAILED (failures=1, skipped=2)`. Test duy nhất fail là `test_deliberate_failure`.
- `metadata`: chỉ `INDEX_FILES_VALID` FAIL (`tests/m03/ci-red/INDEX.ci-red.yaml: INDEX_INVALID ... ParserError`); 5 kiểm tra còn lại PASS. Job dừng ở bước đó.

Cả 3 job đỏ trong cùng một lần chạy, mỗi job đúng một lần, và mỗi job đỏ đúng vì lỗi cố ý. Cây file sau revert giống hệt commit 2 (`git diff c7d8f2a 00bd2b8` rỗng).

Lần làm đỏ này không bật `mcp_stdio` và không đổi pin trong file đã commit. Hai tình huống đó đã có test âm trên bản sao Git tạm trong `tests/m03/test_validate_repo_metadata.py`.

## Giới hạn

- Chưa có ruleset, nên evidence này chưa chứng minh merge bị chặn. Đó là việc của M03-B và M03-C.
- Runner Windows của GitHub chạy với quyền admin, khác máy chủ repo. CI chỉ chạy unit/contract test. Các kiểm tra token (không elevated, integrity Medium) của preflight chỉ có nghĩa trên máy chủ repo và không nằm trong CI.
- CI không thay thế các lần chạy có Claude Code thật (`m02_surface.py`) hay chạy live. Các lần đó vẫn cần kế hoạch được review và phê duyệt riêng.
