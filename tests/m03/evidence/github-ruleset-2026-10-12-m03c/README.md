# M03-C: evidence kiểm chứng ruleset (2026-10-12)

## Bối cảnh

- **Kế hoạch:** `docs/M03_C_VERIFICATION_PLAN.md`. REVIEW_V1 5486070940 PASS tại `37e246386d1a797e0a641e7e6eec78e78d47cc38`. Kế hoạch merge vào `main` qua PR #12 (merge commit `1071a85`).
- **Phê duyệt của chủ repo:** trong chat Claude ngày 2026-10-12, nguyên văn:
  - "Tôi phê duyệt merge PR #12 tại commit 37e246386d1a797e0a641e7e6eec78e78d47cc38."
  - "Tôi phê duyệt chạy M03-C theo docs/M03_C_VERIFICATION_PLAN.md tại commit 37e246386d1a797e0a641e7e6eec78e78d47cc38."
- **Điều kiện bắt đầu (kế hoạch §1):**
  - M03-B đã được chủ repo nghiệm thu ngày 2026-10-12 (PR #9, merge `4db1f77`);
  - kế hoạch có REVIEW_V1 PASS tại đúng SHA;
  - chủ repo đã phê duyệt chạy.
- **Ruleset:** `TVXD-PROTECT-MAIN` (id `24768629`).
- **Mốc:**
  - `MAIN_BEFORE` = `1071a85233728508fc47bc8005571fed1ad13c32`;
  - `PARENT` = `4db1f77be95c6fde60463614be5cc8c10fe97313`.
- Thời điểm do GitHub cung cấp giữ nguyên UTC; diễn giải ghi kèm giờ UTC+7.

## Kết quả

| Mã | Tình huống | Kết quả | Căn cứ |
|---|---|---|---|
| T1 | Push thẳng commit mới vào `main` | **Bị chặn** | `! [remote rejected] … (push declined due to repository rule violations)`, `GH013`: "Changes must be made through a pull request.", "3 of 3 required status checks are expected."; `T1 push exit = 1`; `main` trước/sau = `MAIN_BEFORE` |
| T2 | Force push lùi `main` về `PARENT` | **Bị chặn** | `! [remote rejected]`, `GH013`: "Cannot force-push to this branch", "Changes must be made through a pull request."; `T2 push exit = 1`; `main` trước/sau = `MAIN_BEFORE` |
| T4 | Merge PR khi nhánh chậm hơn `main`, CI xanh | **Bị chặn** | PR #14 tại `c4bd2e0`: 3 check bắt buộc xanh, `mergeable_state: behind`, `behind_by: 5`; ảnh: "This branch is out-of-date with the base branch", nút "Merge pull request" bị khóa |
| T3 | Merge PR khi một required check đỏ, nhánh đã cập nhật theo `main` | **Bị chặn** | PR #14 tại `a2f7ea3`: `metadata` failure, `linux`/`windows` success; `mergeable_state: blocked`, `behind_by: 0`; ảnh: "Some checks were not successful", `ci / metadata` Required đỏ, nút merge bị khóa |

Không tình huống nào cho kết quả INVALID ở lần chạy được tính. Lần INVALID trước đó và lần chạy thêm được ghi ở mục "Các lần chạy không tính".

`main` sau kiểm chứng vẫn là `MAIN_BEFORE` (`1071a85…`). Claude đọc lại lúc 2026-10-12T03:47:19Z (10:47 +07:00), sau khi đóng PR #14.

## Các file

| File | Nội dung |
|---|---|
| `ruleset-24768629.p0.api.json` | Ruleset đọc lại ở P0 qua API công khai, nguyên văn. Header `Date: Mon, 12 Oct 2026 02:42:19 GMT` (09:42 +07:00). Không có khóa nào khác `tests/m03/evidence/github-settings-2026-10-09-m03b/ruleset-24768629.api.json`: `updated_at` vẫn `2026-10-09T11:47:19.910+07:00`, `enforcement: active`, `bypass_actors: []`. |
| `t1-attempt1-invalid-console-excerpt.txt` | Lần chạy T1 thứ nhất (INVALID, xem dưới), trích nguyên văn phần output. |
| `t1-t2-attempt2-console.txt` | Lần chạy được tính: khai báo danh tính git cục bộ, T1, đưa bản clone về `MAIN_BEFORE`, T2. Nguyên văn console. |
| `extra-run-ducdq-console-excerpt.txt` | Lần chạy thêm trên máy khác, dừng trước mọi probe (xem dưới), trích nguyên văn. |
| `probe-pr14-api-states.json` | Trường đọc từ API cho PR #14 ở T4 và T3: `draft`, `merged`, `mergeable_state`, `auto_merge`, `head_sha`, `base_sha`; compare `MAIN_BEFORE...head`: `status`, `ahead_by`, `behind_by`, `merge_base_commit`, `files`. |
| `t4-merge-box-pr14.png` | Ảnh hộp merge PR #14 ở T4, chủ repo chụp. |
| `t3-merge-box-pr14.png` | Ảnh hộp merge PR #14 ở T3, chủ repo chụp. |

## Diễn biến

### P0 (Claude, chỉ đọc)

- Đọc ruleset lúc 2026-10-12 09:42 +07:00 và so sánh với evidence M03-B: giống hệt.
- `main` = `MAIN_BEFORE` (merge PR #12), cha thứ nhất = `PARENT`.
- CI trên `MAIN_BEFORE` (run 38196816535):
  - `linux` success (job 114641203528);
  - `windows` success (job 114641203764);
  - `metadata` success (job 114641203693).
- PR đang mở: chỉ PR #13. Chủ repo giữ PR này, không merge trong lúc kiểm chứng.

### T1 và T2 (chủ repo chạy)

- **Máy:** chạy trên máy "IT", user Windows `BOSS`, trong bản clone mới `C:\Users\BOSS\AppData\Local\Temp\m03c-20261012-102858\m03c-probe`. Chủ repo cho biết đã định chạy trên máy ducdq và chạy nhầm sang máy IT. Chủ repo quyết định giữ kết quả và ghi rõ, không chạy lại.
- **Tài khoản GitHub:** `tuvanxdbg-crypto`, theo xác nhận của chủ repo. Máy IT đã lưu sẵn thông tin đăng nhập, không có cửa sổ đăng nhập.
- **Vì sao kết quả vẫn có giá trị:** ruleset được GitHub áp ở phía server. Từ chối `GH013` là của GitHub, không phụ thuộc máy client.
- **Danh tính git:** trước lần chạy được tính, chủ repo đặt `user.name`/`user.email` chỉ trong bản clone thử, không dùng `--global`. Email là địa chỉ noreply của GitHub.
- **T1:** commit thử `4f49a3971ec9117eb533aaff31442d7038f29f90`, cha `MAIN_BEFORE`, được kiểm trước khi push. Commit này chỉ tồn tại trên máy IT vì GitHub đã từ chối nó.
- **T2:** dùng `--force-with-lease=refs/heads/main:MAIN_BEFORE` đẩy `PARENT`. Không cần khối phục hồi.

### T4 rồi T3 (Claude, PR thử #14)

- Nhánh `claude/m03c-probe` tách từ `PARENT`.
- **Commit `c4bd2e0`:** thêm `tests/m03/probe/M03C_PROBE.md`, file tài liệu vô hại nằm trong PR suốt quá trình. PR mở ở dạng draft.
- **T4:**
  - CI run 38200460419 trên `c4bd2e0`: `linux` success (job 114652490454), `windows` success (job 114652490696), `metadata` success (job 114652490626).
  - Claude chuyển PR sang ready for review rồi đọc API lúc `Mon, 12 Oct 2026 03:39:09 GMT` (10:39 +07:00):
    - PR: `draft: false`, `merged: false`, `mergeable_state: behind`, `auto_merge: null`;
    - compare: `diverged`, `ahead_by: 1`, `behind_by: 5`, `merge_base` = `PARENT`, files = chỉ file tài liệu.
  - Chủ repo chụp ảnh T4. Sau đó đọc lại: `main` vẫn `MAIN_BEFORE`, `mergeable_state` vẫn `behind`.
- **T3:**
  - Kiểm drift: `main` = `MAIN_BEFORE`.
  - Hai commit được push trong cùng một lần:
    - merge commit `c1e8d203a2e3916530dd7a66c274231cfab1bf32`, đưa `MAIN_BEFORE` vào;
    - commit `a2f7ea38bbaed52ad9040ab59ac607d0ba2f5b08`, thêm `tests/m03/test_m03c_probe.py` với một test cố ý fail.
  - CI run 38200912890 trên `a2f7ea3`:
    - `metadata` failure (job 114653907324). Log: chỉ `test_deliberate_failure (test_m03c_probe.M03CProbe.test_deliberate_failure)` FAIL, `Ran 18 tests`, `FAILED (failures=1)`;
    - `linux` success (job 114653907275);
    - `windows` success (job 114653907116).
  - Đọc API lúc `Mon, 12 Oct 2026 03:45:46 GMT` (10:45 +07:00):
    - PR: `mergeable_state: blocked`, `auto_merge: null`;
    - compare: `ahead`, `ahead_by: 3`, `behind_by: 0`, `merge_base` = `MAIN_BEFORE`, files = file tài liệu và file test thử.
  - Chủ repo chụp ảnh T3. Sau đó đọc lại: `main` vẫn `MAIN_BEFORE`, `mergeable_state` vẫn `blocked`.
- **Trong suốt T4 và T3:** không ai bấm merge, không gọi API merge, không bật auto-merge. Không có HEAD nào của PR #14 vừa cập nhật theo `main` vừa xanh.

### Dọn dẹp

- PR #14 đã đóng, không merge: `state: closed`, `merged: false`, `closed_at: 2026-10-12T03:47:09Z` (10:47 +07:00).
- Nhánh `claude/m03c-probe`: Claude không xóa được, vì proxy của phiên Claude trả HTTP 403 cho lệnh xóa nhánh. Chủ repo xóa trên giao diện GitHub (nút "Delete branch" của PR #14) và báo trong chat "Đã xóa 14". Claude kiểm lại lúc 2026-10-12T03:52:11Z (10:52 +07:00): `git ls-remote` không còn `refs/heads/claude/m03c-probe`, `GET /repos/{owner}/{repo}/branches/claude/m03c-probe` trả 404, `main` vẫn `MAIN_BEFORE`.
- Không có gì từ nhánh thử đi vào `main`.

## Các lần chạy không tính

| Lần | Máy | Kết quả | Lý do |
|---|---|---|---|
| T1 lần 1 | IT, user `BOSS` | **INVALID** | `git commit` lỗi `Author identity unknown` (exit 128). `Invoke-Git` dừng khối trước lệnh push, đúng cơ chế fail-closed. Không push gì. Chủ repo xác nhận chạy lại trong chat: "Tôi xác nhận chạy lại T1/T2 sau lần INVALID do thiếu danh tính git." Claude chạy lại P0 lúc `Mon, 12 Oct 2026 03:30:22 GMT` (10:30 +07:00): `main` vẫn `MAIN_BEFORE`, ruleset không đổi. |
| Chạy thêm | ducdq, user `ducdq.tvxdbg` | Dừng trước mọi probe | Chạy sau khi T1/T2 đã xong, không được yêu cầu. `Assert-Repo` dừng ở khối clone và khối T1, trước mọi commit hay push. Lý do: `$env:TEMP` là đường dẫn 8.3 (`C:\Users\DUCDQ~1.TVX\…`), còn `Get-Location` trả tên đầy đủ (`C:\Users\ducdq.tvxdbg\…`). `main` sau đó vẫn `MAIN_BEFORE`. |

## Giới hạn

- **T1/T2 chạy trên máy IT, không phải ducdq.** Kết quả chặn đến từ GitHub. Tài khoản push là `tuvanxdbg-crypto` theo lời chủ repo; Claude không tự kiểm được tài khoản trên máy IT.
- **Lý do chặn T1/T2:** ruleset có cả rule "bắt buộc PR" lẫn rule "chặn force push". Evidence ghi nguyên văn các rule GitHub nêu, không suy diễn rule nào là nguyên nhân duy nhất. T2 nêu cả hai rule.
- **`mergeable_state`** là trường API không có tài liệu đầy đủ. Evidence kết hợp trường này với compare (`behind_by`) và ảnh hộp merge.
- **`Assert-Repo` báo sai khi `$env:TEMP` là đường dẫn 8.3.** Lỗi này dừng khối an toàn, không gây push sai, nhưng làm khối không chạy được trên máy như ducdq. Nếu sau này cần chạy lại các khối này, kế hoạch cần sửa bước so sánh đường dẫn, qua review riêng.
- **Thông tin còn lưu trên máy IT:**
  - bản clone thử, gồm cấu hình danh tính cục bộ và commit `4f49a39`. Chủ repo được khuyên xóa thư mục;
  - thông tin đăng nhập GitHub đã lưu sẵn từ trước, ngoài phạm vi M03-C.
- **Tên user Windows** (`BOSS`, `ducdq.tvxdbg`) và tên máy `IT` xuất hiện trong output. Không có mật khẩu, token hay cookie.

## Trạng thái

**M03-C: ĐẠT THEO EVIDENCE, chờ REVIEW_V1 và chủ repo nghiệm thu.** Cả 4 tình huống T1, T2, T3, T4 đều bị chặn, và `main` không đổi. Chỉ chủ repo mới chốt M03-C, và M03 tổng thể, là PASS.
