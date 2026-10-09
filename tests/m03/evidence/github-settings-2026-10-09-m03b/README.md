# M03-B: evidence cài đặt GitHub (2026-10-09)

## Bối cảnh

- **Spec:** `docs/M03_GITHUB_GOVERNANCE.md` (REVIEW_V1 PASS tại `a2e8362`), các mục D1, D4 lớp 2, D3 (cổng phê duyệt fork), §6 bước 2 và §7 hàng M03-B.
- **M03-A** đã merge vào `main` tại `d1b65aabb00cf58d6b611242eff86d7c336aa7ca` ngày 2026-10-09. CI chạy trên `main` sau merge (run 37885550904) xanh.
- **Người thao tác:** chủ repo tự đổi cài đặt trên GitHub. Claude không đổi cài đặt nào. Claude chỉ:
  - đọc ruleset qua API công khai, không xác thực (`GET /repos/{owner}/{repo}/rulesets/{id}`). Repo public nên ai có quyền đọc cũng xem được ruleset đang chạy;
  - lưu các ảnh chụp chủ repo gửi trong chat Claude.

## Các file

| File | Nội dung | Thời điểm |
|---|---|---|
| `ruleset-24768629.api.json` | Ruleset `TVXD-PROTECT-MAIN` lấy từ API công khai, nguyên văn | Claude đọc lúc 2026-10-09T05:23Z (12:23 +07:00); `updated_at` của ruleset: `2026-10-09T11:47:19.910+07:00` |
| `ruleset-1-bypass-target.png` | Trang ruleset: tên, Active, **Bypass list is empty**, target `main` (Default) | Chủ repo gửi khoảng 11:44 +07:00, trước lần sửa merge method |
| `ruleset-2-pull-request.png` | Branch rules: Restrict deletions, Require a pull request (0 approval), không bật Require linear history | Như trên |
| `ruleset-3-merge-methods-status-checks.png` | Allowed merge methods "Squash, Merge"; Require status checks to pass, strict, 3 check `linux`, `windows`, `metadata` (GitHub Actions); Block force pushes | Chủ repo gửi khoảng 11:47 +07:00, sau khi sửa |
| `advanced-security-secret-protection.png` | Settings → Advanced Security: **Secret Protection** và **Push protection** đang bật (nút "Disable" hiện ở cả hai dòng) | Chủ repo gửi khoảng 12:22 +07:00 |
| `secret-scanning-alerts.png` | Security and quality → Secret scanning: **0 Open, 0 Closed**, "No secrets found." | Chủ repo gửi khoảng 12:20 +07:00 |
| `actions-fork-approval.png` | Settings → Actions → General: **Require approval for all external contributors** được chọn | Chủ repo gửi khoảng 12:22 +07:00 |
| `gh-api-secret-scanning-console.txt` | Chủ repo chạy GitHub CLI (đã đăng nhập) gọi REST API secret scanning: `scan-history` trả 404 "Advanced Security is disabled on this repository"; danh sách alert `state=open` và `state=resolved` đều có 0 phần tử | Chủ repo gửi chiều 2026-10-09, sau REVIEW_V1 5466929709 |

Các ảnh chụp 1 và 2 được chụp trước khi chủ repo thêm Merge vào "Allowed merge methods" và bật required status checks. Trạng thái cuối cùng của ruleset lấy theo `ruleset-24768629.api.json` và ảnh 3.

## Trạng thái

**M03-B: `CHƯA KIỂM CHỨNG`, chưa được ghi PASS.**

| Hạng mục | Trạng thái | Lý do |
|---|---|---|
| D1 ruleset | Đạt theo evidence | JSON từ API và ảnh 1 |
| D3 phê duyệt fork | Đạt theo evidence | Ảnh và xác nhận "đã Save" của chủ repo |
| D4 lớp 2: Secret Protection và Push protection đang bật | Đạt theo evidence | Ảnh |
| D4 lớp 2: danh sách alert qua API có xác thực | Đạt theo evidence | REST API `secret-scanning/alerts`, gọi bằng tài khoản chủ repo: 0 alert `open`, 0 alert `resolved`. Lần gọi đầu (`gh-api-secret-scanning-console.txt`) chỉ đếm một trang; lần đọc hết mọi trang theo A1-2 ở `a1-2-alerts-paginated-console.txt` |
| D4 lớp 2: lần quét lịch sử đã xong | **`CHƯA KIỂM CHỨNG`** | Endpoint chính thức `secret-scanning/scan-history` trả 404 "Advanced Security is disabled on this repository", nên không đọc được trạng thái quét. Không có evidence chính thức nào khác. Vì chưa biết lần quét đã xong hay chưa, danh sách 0 alert cũng chưa được coi là đầy đủ. Xem giới hạn 2 |


### Tiến độ theo tiêu chí thay thế A1 (§7a)

§7a có hiệu lực từ khi chủ repo phê duyệt `9139f5010f6cfe01822b86119161d3562b5d0201` ngày 2026-10-09 (REVIEW_V1 5467514547; ghi nhận trên PR #9). Điều kiện áp dụng thỏa: repo public, không có GitHub Advanced Security, và lỗi của `scan-history` đã được ghi (A1-4).

| Tiêu chí | Trạng thái | Evidence |
|---|---|---|
| A1-1 Secret Protection và Push protection đang bật | Đạt | `advanced-security-secret-protection.png` |
| A1-2 Lần đọc thứ nhất, đọc hết mọi trang | Đạt | `a1-2-alerts-paginated-console.txt`: chạy lúc 2026-10-09 16:54 +07:00; `state=open` và `state=resolved` đều không in dòng nào, tức 0 alert trên mọi trang. Không có alert `resolved`, nên không cần evidence theo từng alert. Ảnh `secret-scanning-alerts.png` cũng cho 0 Open, 0 Closed |
| A1-3 Lần đọc thứ hai, ít nhất 24 giờ sau khi bật | **Chưa thực hiện** | Sớm nhất sau 2026-10-10 12:20 +07:00. Mốc tính từ cận trên: ảnh alert 0/0 được chụp khoảng 12:20 +07:00 ngày 2026-10-09, nên Secret Protection đã bật trước thời điểm đó |
| A1-4 Lỗi `scan-history` ghi nguyên văn | Đạt | `gh-api-secret-scanning-console.txt`: HTTP 404 "Advanced Security is disabled on this repository." |

Vì A1-3 chưa có, hạng mục "lần quét lịch sử" vẫn là `CHƯA KIỂM CHỨNG` và M03-B chưa PASS.

Spec §7 hàng M03-B quy định: nếu không xác nhận được lần quét lịch sử, trạng thái là `CHƯA KIỂM CHỨNG` và M03-B không được ghi PASS. Theo REVIEW_V1 5466884315 tại `eadf54e`, tài liệu này áp dụng đúng quy định đó.

## Đối chiếu với spec

### D1: ruleset cho `main`

| Thông số D1 | Trường trong API | Giá trị | Kết quả |
|---|---|---|---|
| Áp dụng cho `main` | `conditions.ref_name.include` | `["~DEFAULT_BRANCH"]` (nhánh mặc định là `main`) | Đạt |
| Đang có hiệu lực | `enforcement` | `active` | Đạt |
| Bắt buộc qua PR | rule `pull_request` | có | Đạt |
| Không bắt buộc approval (§8 mục 1) | `required_approving_review_count` | `0` | Đạt |
| Không bắt buộc Code Owner review | `require_code_owner_review` | `false` | Đạt |
| Bắt buộc giải quyết hội thoại review | `required_review_thread_resolution` | `true` | Đạt |
| Cho phép merge commit | `allowed_merge_methods` | `["squash", "merge"]` | Đạt |
| 3 check bắt buộc | `required_status_checks[].context` | `linux`, `windows`, `metadata`; `integration_id` 15368 (GitHub Actions) | Đạt |
| Chế độ strict | `strict_required_status_checks_policy` | `true` | Đạt |
| Chặn force push | rule `non_fast_forward` | có | Đạt |
| Chặn xóa nhánh | rule `deletion` | có | Đạt |
| Không bypass, kể cả admin (§8 mục 4) | `bypass_actors`; ảnh 1 | `[]`; ảnh ghi "Bypass list is empty" | Đạt, xem giới hạn 1 |

Ngoài spec:
- `require_extra_approval_for_unattributed_changes: true` (mục "additional approval for unattributed Copilot pull requests"). Theo mô tả trên giao diện, mục này chỉ có tác dụng khi số approval bắt buộc lớn hơn 0, nên với cấu hình 0 approval nó không đổi gì.
- Cài đặt chung của repo cho phép cả merge, squash và rebase (`allow_merge_commit`, `allow_squash_merge`, `allow_rebase_merge` đều `true`). Với `main`, ruleset thu hẹp lại còn squash và merge.

### D4 lớp 2: secret scanning và push protection

- Secret Protection (secret scanning) và Push protection đang bật: ảnh `advanced-security-secret-protection.png`.
- Danh sách alert: 0 open, 0 closed, "No secrets found.": ảnh `secret-scanning-alerts.png`. Không có alert nào nên không có credential nào phải thu hồi.
- Theo tài liệu GitHub ("secret scanning scans your entire Git history on all branches"), secret scanning quét toàn bộ lịch sử Git trên mọi nhánh. Câu này mô tả tính năng. Nó không phải evidence rằng lần quét trên repo này đã xong.
- **REST API, gọi bằng tài khoản chủ repo** (`gh-api-secret-scanning-console.txt`):
  - `GET /repos/{owner}/{repo}/secret-scanning/alerts?state=open&hide_secret=true` → 0 phần tử;
  - `GET /repos/{owner}/{repo}/secret-scanning/alerts?state=resolved&hide_secret=true` → 0 phần tử;
  - `GET /repos/{owner}/{repo}/secret-scanning/scan-history` → HTTP 404, "Advanced Security is disabled on this repository". Theo tài liệu REST của GitHub (`github/docs` commit `9f65179`, file `src/rest/data/fpt-2022-11-28/secret-scanning.json`), endpoint này "requires GitHub Advanced Security". Repo này dùng Secret Protection miễn phí cho repo public, không có GitHub Advanced Security, nên không gọi được endpoint.
- **Lần quét lịch sử: `CHƯA KIỂM CHỨNG`.** Cả giao diện lẫn API đều không cho biết lần quét lịch sử đã xong. Danh sách alert trên API khớp với ảnh (0 và 0), nhưng chưa được coi là đầy đủ, vì có thể lần quét chưa xong.

### D3: cổng phê duyệt workflow từ fork

- Đang chọn "Require approval for all external contributors", mức chặt nhất trong 3 lựa chọn: ảnh `actions-fork-approval.png`.
- Ảnh chụp vẫn còn nút Save. Chủ repo xác nhận trong chat Claude ngày 2026-10-09, nguyên văn: "đã Save".

## Giới hạn

1. API công khai không xác thực có thể không trả về `bypass_actors` cho người không có quyền admin. Vì vậy bằng chứng chính cho việc "không bypass" là ảnh 1 ("Bypass list is empty"). Trường `current_user_can_bypass: "never"` chỉ nói về người gọi API ẩn danh.
2. **Lần quét lịch sử.** Tài liệu GitHub mà Claude đọc không mô tả dấu hiệu nào trên giao diện báo lần quét lịch sử đã xong. Endpoint API duy nhất trả về trạng thái quét (`scan-history`) cần GitHub Advanced Security, nên trả 404 trên repo này. Vì vậy, với cấu hình hiện tại, không có cách chính thức nào để kiểm chứng lần quét đã xong. Hạng mục này là `CHƯA KIỂM CHỨNG` và M03-B chưa PASS. Muốn đổi trạng thái, cần một trong hai:
   - evidence chính thức của GitHub về lần quét, rồi có REVIEW_V1 mới;
   - chủ repo quyết định riêng cách xử lý điều kiện này của §7 (ví dụ chấp nhận ngoại lệ, có ghi lý do), rồi có review riêng.
   Claude không tự chọn hướng nào.
3. Trạng thái bật Secret Protection, Push protection và cài đặt fork chỉ có trong ảnh chụp. Claude không đọc được các cài đặt này qua API, vì chúng cần quyền admin.
4. Evidence này chưa chứng minh ruleset thật sự chặn. Việc đó là M03-C: thử push thẳng, force push, merge khi check đỏ, merge khi nhánh chậm hơn `main`.

## Nguồn tài liệu GitHub đã đối chiếu

Claude đọc từ repo công khai `github/docs`, commit `9f651797567230e844373870fce8b14427ad47ad` (2026-10-08), vì docs.github.com bị chặn trong môi trường của Claude. Các trang:
- `content/code-security/how-tos/secure-your-secrets/detect-secret-leaks/enable-secret-scanning.md`;
- `content/code-security/how-tos/secure-your-secrets/prevent-future-leaks/enable-push-protection.md`;
- `content/code-security/concepts/secret-security/secret-scanning.md`;
- `content/code-security/how-tos/manage-security-alerts/manage-secret-scanning-alerts/viewing-alerts.md` và `resolving-alerts.md`;
- `data/reusables/actions/workflows-from-public-fork-setting.md`;
- `data/reusables/repositories/rulesets-anyone-can-view.md`.
