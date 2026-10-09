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
- Đọc lại ruleset qua API công khai (`GET /repos/tuvanxdbg-crypto/TVXD-AI-STANDARDS/rulesets/24768629`). So sánh với `tests/m03/evidence/github-settings-2026-10-09-m03b/ruleset-24768629.api.json`. Nếu `updated_at` hoặc bất kỳ rule nào khác đi, dừng lại và báo chủ repo.
- Ghi SHA hiện tại của `main` (gọi là `MAIN_BEFORE`) và xác nhận CI trên `main` đang xanh.
- Xác nhận không có PR nào khác sắp merge trong lúc kiểm chứng.

## 4. Các bước

### T1 và T2: chủ repo chạy trên máy của mình

Claude không push vào `main`, kể cả để thử (CLAUDE.md: "Do not push directly to main"). Chủ repo chạy trong PowerShell, trong một bản clone sạch của repo:

```powershell
git fetch origin
git switch main
git reset --hard origin/main
git rev-parse HEAD                 # ghi lại: phải bằng MAIN_BEFORE

# T1: push thẳng một commit mới
git commit --allow-empty -m "M03-C T1 probe: phải bị từ chối"
git push origin HEAD:main          # mong đợi: bị từ chối
git reset --hard origin/main       # bỏ commit thử ở máy

# T2: force push lùi main về commit cha
git push --force origin HEAD~1:main   # mong đợi: bị từ chối
git fetch origin
git rev-parse origin/main          # phải vẫn bằng MAIN_BEFORE
```

- Ghi nguyên văn output của hai lệnh `git push`. Thông báo từ chối của GitHub thường nhắc tới vi phạm ruleset của repo; ghi đúng như in ra, không chép lại theo trí nhớ.
- **Giới hạn đã biết:** ruleset có cả rule "bắt buộc PR" lẫn rule "chặn force push". Một lần push bị từ chối có thể do một hoặc cả hai rule. Evidence ghi nguyên văn các rule GitHub nêu ra, không suy diễn thêm.
- **Nếu T2 bất ngờ thành công** (`origin/main` khác `MAIN_BEFORE`): dừng ngay, khôi phục bằng `git push --force origin MAIN_BEFORE:main`, kiểm tra lại `origin/main`, báo Claude. M03-C ghi FAIL, không chạy tiếp.
- **Nếu T1 bất ngờ thành công:** dừng, báo Claude. Commit thử không đổi file nào (`--allow-empty`). Việc gỡ nó khỏi `main` sẽ làm qua một PR revert riêng, không force push.

### T3 và T4: PR thử, Claude chuẩn bị, chỉ đọc trạng thái

Claude tạo nhánh thử `claude/m03c-probe`. Nhánh này **tách từ commit cha thứ nhất của `MAIN_BEFORE`**, nên ngay từ đầu đã chậm hơn `main` đúng một commit. Sau đó Claude mở một PR nháp vào `main`. PR này chỉ dùng để thử: không bao giờ merge, cuối cùng sẽ đóng.

1. **T3, check đỏ.** Commit đầu tiên trên nhánh thử thêm `tests/m03/test_m03c_probe.py`, gồm một test cố ý fail. Job `metadata` chạy `tests/m03` nên sẽ đỏ.
   - Chờ CI chạy xong. Ghi link run: `metadata` failure, `linux` và `windows` success.
   - Claude đọc trạng thái PR qua API (`mergeable_state`), không gọi lệnh merge.
   - Chủ repo chụp hộp merge của PR trên giao diện, cho thấy merge bị chặn vì required check đỏ.
2. **T4, nhánh chậm hơn `main`.** Commit thứ hai revert commit T3, nên CI xanh lại.
   - Nhánh vẫn chậm hơn `main`, vì nó tách từ commit cha.
   - Claude đọc lại `mergeable_state` và ghi lại tình trạng "behind" mà API báo về.
   - Chủ repo chụp hộp merge, cho thấy merge vẫn bị chặn vì nhánh chưa cập nhật theo `main`, dù 3 check đều xanh.
3. **Dọn dẹp.** Claude đóng PR thử mà không merge, rồi xóa nhánh `claude/m03c-probe`. Không có gì từ nhánh thử đi vào `main`.

Ở T3 và T4, không ai bấm merge hay gọi API merge. Như vậy, nếu ruleset có lỗi thì cũng không có code thử nào lọt vào `main`. Bằng chứng gồm trạng thái API và ảnh hộp merge.

## 5. Evidence

Ghi trong `tests/m03/evidence/github-ruleset-<ngày>-m03c/`, qua một PR riêng có REVIEW_V1:
- ruleset JSON đọc lại ở P0, kèm `MAIN_BEFORE`;
- output nguyên văn của T1 và T2, cùng `origin/main` sau mỗi bước;
- link PR thử, link các run CI (đỏ ở T3, xanh ở T4), `mergeable_state` ở mỗi bước, ảnh hộp merge;
- xác nhận dọn dẹp: PR thử đã đóng và không merge, nhánh đã xóa, `main` vẫn bằng `MAIN_BEFORE` (trừ khi có PR thật khác merge xen giữa, khi đó ghi rõ);
- thời điểm ghi theo UTC+7, giờ GitHub giữ nguyên.

Không ghi token, mật khẩu hay bất kỳ dữ liệu đăng nhập nào.

## 6. Điều kiện đạt (§7 hàng M03-C)

- T1, T2, T3, T4 **đều bị chặn**, và mỗi tình huống có evidence như mục 5.
- `main` sau kiểm chứng vẫn ở `MAIN_BEFORE`, hoặc chỉ thay đổi do PR thật đã được duyệt.
- Có REVIEW_V1 PASS tại HEAD của PR evidence, và chủ repo nghiệm thu.

Chỉ cần một tình huống không bị chặn là M03-C FAIL. Khi đó dừng, khôi phục và báo chủ repo, không tự sửa ruleset.

## 7. Phân vai

Theo khối "Phan vai" trong CLAUDE.md:
- LEAD (Opus 5.5) soạn kế hoạch này, kiểm tra P0, đọc trạng thái và soạn evidence.
- EXECUTOR (Sonnet 5.5) có thể tạo nhánh và PR thử theo đúng mục 4.
- Không giao cho EXECUTOR-2, vì việc này đụng `main`, ruleset và tiêu chí nghiệm thu.
- Chủ repo làm T1, T2 và chụp ảnh hộp merge.

## 8. Chưa được phép theo kế hoạch này

Chạy bất kỳ bước nào trước khi đủ điều kiện ở mục 1. Đổi hay tạm tắt ruleset để thử. Bấm merge hay gọi API merge PR thử. Push thẳng hoặc force push vào `main` từ phía Claude. M04 trở đi; AutoCAD.
