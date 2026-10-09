# Quy trình REVIEW_V1 và merge

Tài liệu này là sản phẩm D7 của M03 (`docs/M03_GITHUB_GOVERNANCE.md` §4). Nó chỉ viết lại trình tự đã có. Quy tắc gốc nằm ở mục "Phan vai" trong `CLAUDE.md` trên `main`. Khi hai nơi khác nhau, `CLAUDE.md` thắng.

## 1. Trình tự

```text
branch -> commit -> PR -> cập nhật theo main -> CI xanh -> REVIEW_V1 tại HEAD của PR -> chủ repo duyệt -> merge
```

1. **Branch.** Làm trên nhánh tính năng, không push thẳng vào `main`.
2. **PR.** Mở PR vào `main` theo `.github/pull_request_template.md`. Nếu PR sửa vùng nhạy cảm, đánh dấu ở mục "Vùng nhạy cảm bị sửa".
3. **Cập nhật theo `main`.** Nhánh PR phải chứa commit mới nhất của `main`. Repo dùng merge commit; chỉ rebase nhánh do chính mình tạo.
4. **CI xanh.** Ba check `linux`, `windows`, `metadata` của workflow `ci` phải xanh trên HEAD của PR. Khi báo cáo CI, tách 3 trạng thái:
   - đang chờ maintainer phê duyệt (PR từ fork, chưa chạy);
   - đã chạy và đỏ;
   - không có check.
   Chỉ trạng thái thứ hai là CI failure.
5. **REVIEW_V1.** Reviewer đăng review có marker `REVIEW_V1`, kèm `REVIEWER_MODEL`, `REVIEWED_COMMIT`, `DECISION` và `NEXT_ALLOWED_STEP`.
6. **Chủ repo duyệt và merge.** PASS của Reviewer không thay cho nghiệm thu. Chủ repo duyệt trực tiếp đúng SHA rồi tự bấm merge.

## 2. Khi nào review hết hiệu lực

- Review chỉ hợp lệ khi `REVIEWED_COMMIT` bằng HEAD hiện tại của PR.
- HEAD đổi vì bất kỳ lý do gì thì review cũ là STALE. Lý do có thể là commit mới, hoặc merge `main` vào nhánh. Khi đó phải chạy lại đủ 3 check và có REVIEW_V1 mới tại SHA mới.
- Executor và Reviewer không dùng cùng model trong một vòng chạy.

## 3. PR từ fork

Với PR từ fork của người đóng góp mới, GitHub có thể giữ workflow chờ maintainer phê duyệt. Trước khi phê duyệt, chủ repo đọc diff, đặc biệt các file trong `.github/`, script, test và mọi thay đổi có gọi mạng hoặc cài thêm gói. Không phê duyệt PR sửa `.github/workflows/` hoặc có thay đổi đáng ngờ; ghi lý do vào PR.

## 4. Ví dụ khối REVIEW_V1

```text
REVIEW_V1
REVIEWER_MODEL: GPT-6.1 Sol
REVIEWED_COMMIT: <SHA đầy đủ 40 ký tự của HEAD PR>
SCOPE: <phạm vi được review>

FINDINGS:
- [HIGH|MEDIUM|LOW|INFO] <mô tả, kèm file và lý do>

VALIDATION:
- <những gì reviewer đã đọc hoặc chạy>

LIMITATIONS:
- <những gì reviewer không kiểm>

DECISION: PASS | PATCH_REQUIRED | BLOCKED
NEXT_ALLOWED_STEP: <bước tiếp theo duy nhất được phép>
```

Báo cáo của Executor/LEAD trên PR dùng khối `CLAUDE_EXECUTION_REPORT`, có `HEAD_COMMIT` đầy đủ và kết thúc bằng `NEXT_REQUEST: REQUEST_REVIEW_V1 at exact HEAD <SHA>`.

## 5. Marker cũ

Các review `GPT_REVIEW_V1` đã đăng trong M01 và M02 được giữ nguyên làm hồ sơ lịch sử. Review mới dùng `REVIEW_V1`.
