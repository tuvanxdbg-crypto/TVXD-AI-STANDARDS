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

Các ảnh chụp 1 và 2 được chụp trước khi chủ repo thêm Merge vào "Allowed merge methods" và bật required status checks. Trạng thái cuối cùng của ruleset lấy theo `ruleset-24768629.api.json` và ảnh 3.

## Trạng thái

**M03-B: `CHƯA KIỂM CHỨNG`, chưa được ghi PASS.**

| Hạng mục | Trạng thái | Lý do |
|---|---|---|
| D1 ruleset | Đạt theo evidence | JSON từ API và ảnh 1 |
| D3 phê duyệt fork | Đạt theo evidence | Ảnh và xác nhận "đã Save" của chủ repo |
| D4 lớp 2: Secret Protection và Push protection đang bật | Đạt theo evidence | Ảnh |
| D4 lớp 2: lần quét lịch sử đã xong và alert liệt kê được đầy đủ | **`CHƯA KIỂM CHỨNG`** | Không có evidence chính thức nào của GitHub cho biết lần quét lịch sử đã xong. Xem giới hạn 2 |

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
- **Lần quét lịch sử và độ đầy đủ của danh sách alert: `CHƯA KIỂM CHỨNG`.** Ảnh 0 alert được chụp sau khi bật, nhưng không có gì cho biết lúc đó lần quét lịch sử đã xong. Vì vậy danh sách 0 alert chưa được coi là đầy đủ.

### D3: cổng phê duyệt workflow từ fork

- Đang chọn "Require approval for all external contributors", mức chặt nhất trong 3 lựa chọn: ảnh `actions-fork-approval.png`.
- Ảnh chụp vẫn còn nút Save. Chủ repo xác nhận trong chat Claude ngày 2026-10-09, nguyên văn: "đã Save".

## Giới hạn

1. API công khai không xác thực có thể không trả về `bypass_actors` cho người không có quyền admin. Vì vậy bằng chứng chính cho việc "không bypass" là ảnh 1 ("Bypass list is empty"). Trường `current_user_can_bypass: "never"` chỉ nói về người gọi API ẩn danh.
2. **Lần quét lịch sử.** Tài liệu GitHub mà Claude đọc không mô tả dấu hiệu nào trên giao diện báo lần quét lịch sử đã xong. Ảnh alert không có thông báo đang quét và cho 0 alert, nhưng evidence không chứng minh được lần quét đã xong. Vì vậy hạng mục này là `CHƯA KIỂM CHỨNG` và M03-B chưa PASS. Muốn đổi trạng thái, cần evidence chính thức của GitHub cho thấy lần quét lịch sử đã xong và alert liệt kê được đầy đủ, rồi có REVIEW_V1 mới.
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
