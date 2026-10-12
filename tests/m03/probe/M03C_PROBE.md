# M03-C probe: file thử, không được merge

File này chỉ tồn tại trên nhánh thử `claude/m03c-probe`, theo `docs/M03_C_VERIFICATION_PLAN.md` §4.3.

- Mục đích: giữ cho PR thử luôn có nội dung để merge trong suốt T4 và T3.
- PR thử không bao giờ được merge, không bật auto-merge, và sẽ bị đóng khi xong kiểm chứng; nhánh sẽ bị xóa.
- Nếu thấy file này trên `main`, đó là sự cố: báo chủ repo.
