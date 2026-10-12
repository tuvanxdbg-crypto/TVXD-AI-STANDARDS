# M03-C: kế hoạch kiểm chứng ruleset (bản nháp chờ REVIEW_V1, chưa chạy)

**Trạng thái: KẾ HOẠCH, CHƯA THỰC HIỆN.** Tài liệu này chỉ mô tả cách kiểm chứng. Commit chứa nó không chạy thử, không tạo PR thử, không đổi cài đặt repo hay ruleset.

## 1. Thẩm quyền và điều kiện bắt đầu

- Spec: `docs/M03_GITHUB_GOVERNANCE.md` §6 bước 3 và §7 hàng M03-C.
- Ngày 2026-10-09, trong chat Claude, chủ repo chọn "Kế hoạch M03-C (Khuyến nghị)". Câu chọn đó cho phép **soạn** kế hoạch này để review, chưa cho phép chạy.
- Chỉ được bắt đầu chạy khi đủ cả ba điều kiện:
  1. M03-B đã được chủ repo nghiệm thu (PR #9);
  2. kế hoạch này có REVIEW_V1 PASS tại đúng SHA;
  3. chủ repo phê duyệt trực tiếp đúng SHA đó và cho phép chạy M03-C.

## 2. Mục tiêu

Chứng minh ruleset `TVXD-PROTECT-MAIN` (id `24768629`) thật sự chặn đủ 4 tình huống ở §7:

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| T1 | Push thẳng một commit mới vào `main` | Bị từ chối |
| T2 | Force push (non-fast-forward) vào `main` | Bị từ chối |
| T3 | Merge PR khi một required check đỏ | Không merge được |
| T4 | Merge PR khi nhánh chậm hơn `main` (chế độ strict) | Không merge được |

## 3. Kiểm tra trước khi chạy (P0)

Claude làm, chỉ đọc:
- Đọc lại ruleset qua API công khai (`GET /repos/tuvanxdbg-crypto/TVXD-AI-STANDARDS/rulesets/24768629`). So sánh với `tests/m03/evidence/github-settings-2026-10-09-m03b/ruleset-24768629.api.json`. Nếu `updated_at`, `bypass_actors` hoặc bất kỳ rule nào khác đi, dừng lại và báo chủ repo.
- Ghi SHA đầy đủ 40 ký tự của `main` lúc đó, gọi là `MAIN_BEFORE`, và SHA đầy đủ của commit cha thứ nhất của nó, gọi là `PARENT`. Gửi cả hai giá trị cho chủ repo trong chat. Mọi bước sau dùng đúng hai giá trị này, không dùng tên ref `main` hay `origin/main` làm mốc.
- Xác nhận CI trên `MAIN_BEFORE` xanh và không có PR nào khác sắp merge trong lúc kiểm chứng.

## 4. Các bước

Thứ tự chạy: P0, T1, T2, T4, T3, dọn dẹp.

### 4.1 Quy tắc chung: drift và kết quả INVALID

- **Drift** là khi `main` trên GitHub khác `MAIN_BEFORE` ở một lần kiểm tra mà kế hoạch yêu cầu nó phải bằng `MAIN_BEFORE`. Mỗi probe đều kiểm tra drift ngay trước và ngay sau khi chạy.
- Một probe chỉ được ghi **bị chặn** khi đủ cả ba điều kiện:
  1. `main` bằng `MAIN_BEFORE` cả trước lẫn sau probe;
  2. GitHub từ chối hoặc chặn thao tác đó;
  3. lý do từ chối đến từ phía GitHub, không phải lỗi ở máy hay lỗi đăng nhập.
- Kết quả là **INVALID** (không phải PASS, cũng không phải FAIL) khi:
  - có drift;
  - push bị từ chối vì lỗi xác thực hoặc quyền;
  - lease bị từ chối (`stale info`);
  - lỗi mạng;
  - không đọc được trạng thái.
  Khi INVALID: dừng, không chạy probe kế tiếp, báo Claude và chủ repo. Chỉ chạy lại từ P0, với `MAIN_BEFORE` mới, khi chủ repo xác nhận trong chat.
- Mọi lệnh force (thử T2 và khôi phục) dùng `--force-with-lease=refs/heads/main:<SHA dự kiến>`. GitHub chỉ cập nhật `main` khi giá trị hiện tại đúng bằng SHA dự kiến; nếu có thay đổi xen giữa, lệnh bị từ chối thay vì ghi đè. Không dùng `--force` trần.

### 4.2 T1 và T2: chủ repo chạy trên máy của mình

Claude không push vào `main`, kể cả để thử (CLAUDE.md: "Do not push directly to main"). Chủ repo chạy trong PowerShell, trong một thư mục tạm, với bản clone mới.

**Chuẩn bị** (dán nguyên khối; thay giá trị SHA bằng giá trị Claude gửi ở P0):

```powershell
$MAIN_BEFORE = "<SHA 40 ký tự của MAIN_BEFORE từ P0>"
$PARENT      = "<SHA 40 ký tự của PARENT từ P0>"
function Get-RemoteMain { ((git ls-remote origin refs/heads/main) -split "`t")[0] }
function Assert-MainBefore([string]$Step) {
  $now = Get-RemoteMain
  "$Step : main tren GitHub = $now"
  if ($now -ne $MAIN_BEFORE) { throw "$Step : main khac MAIN_BEFORE. Dung lai, bao Claude." }
}
git clone https://github.com/tuvanxdbg-crypto/TVXD-AI-STANDARDS.git m03c-probe
Set-Location m03c-probe
git switch --detach $MAIN_BEFORE
git rev-parse HEAD "$MAIN_BEFORE~1"   # dòng 1 phải bằng MAIN_BEFORE, dòng 2 phải bằng PARENT
```

**T1, push thẳng một commit mới** (dán nguyên khối; khối dừng ngay khi có drift):

```powershell
& {
  Assert-MainBefore "T1-truoc"
  git commit --allow-empty -m "M03-C T1 probe: phai bi tu choi"
  "T1 commit = $(git rev-parse HEAD)"
  git push origin HEAD:refs/heads/main
  "T1 exit = $LASTEXITCODE"
  Assert-MainBefore "T1-sau"
}
git switch --detach $MAIN_BEFORE      # bỏ commit thử ở máy
```

- Commit T1 có cha là `MAIN_BEFORE`. Khi `main` vẫn bằng `MAIN_BEFORE`, đây là một push fast-forward hợp lệ về mặt Git, nên nếu bị từ chối thì lý do chỉ có thể đến từ phía GitHub.
- T1 **bị chặn** khi: exit khác 0; output có dòng `! [remote rejected]` kèm lời giải thích của GitHub ở các dòng `remote:`; và cả hai dòng `T1-truoc`, `T1-sau` đều bằng `MAIN_BEFORE`.
- **INVALID** nếu output là lỗi xác thực hoặc quyền, hoặc là `! [rejected] ... (fetch first)` hay `(non-fast-forward)` (Git từ chối ở máy vì `main` đã đổi), hoặc có drift.
- **T1 bất ngờ thành công** khi `T1-sau` bằng đúng `T1 commit`. Khối sẽ dừng ở `T1-sau`. M03-C ghi FAIL, không chạy T2, báo Claude. Commit thử không đổi file nào (`--allow-empty`); việc gỡ nó khỏi `main` làm qua một PR revert riêng, không force push.

**T2, force push lùi `main` về `PARENT`** (chỉ chạy khi T1 bị chặn; dán nguyên khối):

```powershell
& {
  Assert-MainBefore "T2-truoc"
  git push --force-with-lease="refs/heads/main:$MAIN_BEFORE" origin "${PARENT}:refs/heads/main"
  "T2 exit = $LASTEXITCODE"
  Assert-MainBefore "T2-sau"
}
```

- Lease gắn với `MAIN_BEFORE`. Nếu `main` đã đổi trước khi lệnh tới GitHub, Git trả `stale info` và không cập nhật gì; khi đó kết quả là INVALID.
- T2 **bị chặn** khi: exit khác 0; output có `! [remote rejected]` kèm giải thích ở các dòng `remote:`; và `T2-truoc`, `T2-sau` đều bằng `MAIN_BEFORE`.
- **T2 bất ngờ thành công** khi `T2-sau` bằng `PARENT`. M03-C ghi FAIL. Khôi phục ngay bằng khối dưới; lệnh chỉ đưa `main` về `MAIN_BEFORE` khi `main` đang đúng bằng `PARENT`, nên không ghi đè thay đổi nào xen giữa:

```powershell
& {
  $now = Get-RemoteMain
  "Truoc khoi phuc: main tren GitHub = $now"
  if ($now -ne $PARENT) { throw "main khong bang PARENT. Khong khoi phuc bang lenh nay, bao Claude." }
  git push --force-with-lease="refs/heads/main:$PARENT" origin "${MAIN_BEFORE}:refs/heads/main"
  "Khoi phuc exit = $LASTEXITCODE"
  Assert-MainBefore "Sau-khoi-phuc"
}
```

  Nếu khối khôi phục dừng hoặc lệnh push bị từ chối: không thử lại, không đổi ruleset. Báo Claude; việc khôi phục chuyển sang một PR riêng đưa nội dung `main` về đúng cây của `MAIN_BEFORE`, qua review như mọi PR khác.
- Ghi nguyên văn toàn bộ output của các khối T1, T2 (và khối khôi phục nếu có chạy). Thông báo từ chối ghi đúng như in ra, không chép lại theo trí nhớ.
- **Giới hạn đã biết:** ruleset có cả rule "bắt buộc PR" lẫn rule "chặn force push". Một lần push bị từ chối có thể do một hoặc cả hai rule. Evidence ghi nguyên văn các rule GitHub nêu ra, không suy diễn thêm.

### 4.3 T4 và T3: PR thử, Claude chuẩn bị, chỉ đọc trạng thái

Claude tạo nhánh thử `claude/m03c-probe` **tách từ `PARENT`**, nên nhánh chậm hơn `main` đúng một commit. PR thử không bao giờ được merge, không bật auto-merge, cuối cùng sẽ đóng.

- **Diff vô hại xuyên suốt.** Commit đầu tiên trên nhánh thêm file tài liệu `tests/m03/probe/M03C_PROBE.md`, ghi rằng đây là file thử của M03-C và không được merge. File này nằm trong PR từ đầu đến cuối, nên PR luôn có nội dung để merge. Nó không khớp mẫu `test_*.py` và không phải `INDEX*.yaml`, nên không đổi kết quả CI.
- **Vì sao T4 chạy trước T3.** Nếu chạy T3 khi nhánh còn chậm hơn `main`, merge bị chặn vì hai lý do cùng lúc, và evidence không tách được lý do check đỏ. Vì vậy T4 chạy khi nhánh chậm hơn `main` nhưng CI xanh. Sau đó nhánh được cập nhật theo `main` rồi mới làm đỏ check cho T3, nên ở T3 lý do duy nhất là check đỏ.
- **Không lúc nào PR merge được.** Ở T4 nhánh chậm hơn `main`; ở T3 check đỏ. Commit cập nhật theo `main` và commit làm đỏ được push **trong cùng một lần push**, nên không có HEAD nào vừa cập nhật theo `main` vừa xanh.
- **Draft.** PR mở ở dạng draft. Sau khi CI của bước T4 chạy xong, Claude chuyển PR sang ready for review. PR draft bị chặn merge vì lý do riêng, nên phải bỏ draft thì hộp merge mới phản ánh đúng ruleset. Bỏ draft không chạy lại CI và không merge.

Ở mỗi bước, Claude đọc qua API, không gọi lệnh merge:
- `GET /repos/{owner}/{repo}/pulls/{n}`: trường `head.sha`, `draft`, `mergeable_state`;
- `GET /repos/{owner}/{repo}/compare/{MAIN_BEFORE}...{head.sha}`: trường `ahead_by`, `behind_by`, `merge_base_commit.sha`, danh sách `files[].filename`;
- SHA hiện tại của `main` trên GitHub (kiểm drift).

1. **T4, nhánh chậm hơn `main`, CI xanh.**
   - Kiểm drift: `main` bằng `MAIN_BEFORE`.
   - Push commit tài liệu, mở PR draft, chờ CI xong: cả `linux`, `windows`, `metadata` success trên `head.sha`. Chuyển PR sang ready for review.
   - Đọc trạng thái. Mong đợi:
     - `behind_by` ≥ 1 và `merge_base_commit.sha` bằng `PARENT`;
     - `files` chỉ gồm `tests/m03/probe/M03C_PROBE.md`;
     - `mergeable_state` ghi đúng như API trả về (thường là `behind`).
   - Chủ repo chụp hộp merge, cho thấy merge bị chặn vì nhánh chưa cập nhật theo `main` dù 3 check đều xanh.
   - Kiểm drift lần nữa. Có drift thì INVALID.
2. **T3, nhánh đã cập nhật theo `main`, một required check đỏ.**
   - Kiểm drift: `main` bằng `MAIN_BEFORE`.
   - Trên nhánh thử, tạo merge commit đưa `MAIN_BEFORE` vào (không rebase, không force push). Sau đó thêm commit chứa `tests/m03/test_m03c_probe.py`, gồm một test cố ý fail. Push hai commit trong cùng một lần push.
   - Chờ CI xong: `metadata` failure (job này chạy `tests/m03`), `linux` và `windows` success.
   - Đọc trạng thái. Mong đợi:
     - `behind_by` = 0;
     - `files` gồm đúng file tài liệu thử và file test thử;
     - `mergeable_state` ghi đúng như API trả về (thường là `blocked`).
   - Chủ repo chụp hộp merge, cho thấy merge bị chặn vì required check đỏ.
   - Kiểm drift lần nữa. Nếu `main` đã đổi (khi đó `behind_by` > 0), T3 là INVALID vì lý do chặn lại lẫn với nhánh chậm hơn `main`.
3. **Dọn dẹp.** Claude đóng PR thử mà không merge, rồi xóa nhánh `claude/m03c-probe`. Không có gì từ nhánh thử đi vào `main`.

Ở T4 và T3, không ai bấm merge hay gọi API merge. Như vậy, nếu ruleset có lỗi thì cũng không có code thử nào lọt vào `main`. Bằng chứng gồm trạng thái API và ảnh hộp merge.

## 5. Evidence

Ghi trong `tests/m03/evidence/github-ruleset-<ngày>-m03c/`, qua một PR riêng có REVIEW_V1:
- ruleset JSON đọc lại ở P0, kèm `MAIN_BEFORE` và `PARENT` (SHA đầy đủ);
- output nguyên văn của các khối T1 và T2 (gồm các dòng kiểm drift trước/sau, `T1 commit`, exit code), và khối khôi phục nếu có chạy;
- link PR thử, link các run CI (xanh ở T4, đỏ ở T3), ở mỗi bước: `head.sha`, `draft`, `mergeable_state`, `ahead_by`, `behind_by`, `merge_base_commit.sha`, danh sách file, SHA của `main` trước/sau; ảnh hộp merge;
- mọi kết quả INVALID và lý do, nếu có;
- xác nhận dọn dẹp: PR thử đã đóng và không merge, nhánh đã xóa, `main` vẫn bằng `MAIN_BEFORE` (trừ khi có PR thật khác merge xen giữa, khi đó ghi rõ);
- thời điểm ghi theo UTC+7, giờ GitHub giữ nguyên.

Không ghi token, mật khẩu hay bất kỳ dữ liệu đăng nhập nào.

## 6. Điều kiện đạt (§7 hàng M03-C)

- T1, T2, T3, T4 **đều bị chặn** theo đúng điều kiện ở mục 4, không tình huống nào INVALID, và mỗi tình huống có evidence như mục 5.
- `main` sau kiểm chứng vẫn ở `MAIN_BEFORE`, hoặc chỉ thay đổi do PR thật đã được duyệt.
- Có REVIEW_V1 PASS tại HEAD của PR evidence, và chủ repo nghiệm thu.

Chỉ cần một tình huống không bị chặn là M03-C FAIL. Khi đó dừng, khôi phục theo mục 4.2 và báo chủ repo, không tự sửa ruleset. Một tình huống INVALID không phải FAIL, nhưng M03-C chưa đạt cho tới khi chạy lại hợp lệ.

## 7. Phân vai

Theo khối "Phan vai" trong CLAUDE.md:
- LEAD (Opus 5.5) soạn kế hoạch này, kiểm tra P0, đọc trạng thái và soạn evidence.
- EXECUTOR (Sonnet 5.5) có thể tạo nhánh và PR thử theo đúng mục 4.
- Không giao cho EXECUTOR-2, vì việc này đụng `main`, ruleset và tiêu chí nghiệm thu.
- Chủ repo làm T1, T2 và chụp ảnh hộp merge.

## 8. Chưa được phép theo kế hoạch này

Chạy bất kỳ bước nào trước khi đủ điều kiện ở mục 1. Đổi hay tạm tắt ruleset để thử. Bấm merge, gọi API merge hay bật auto-merge cho PR thử. Push thẳng hoặc force push vào `main` từ phía Claude. Dùng `--force` không kèm lease. M04 trở đi; AutoCAD.
