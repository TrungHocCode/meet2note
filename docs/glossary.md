# Glossary — ngôn ngữ chung của meet2note

| Thuật ngữ | Nghĩa chốt |
|---|---|
| Decision final | Kết luận cuối duy nhất của một vấn đề (`status: final`) |
| Discarded / proposal | Đề xuất đã bị thay thế, vẫn lưu để audit, không hiện ngang hàng với final |
| Supersedes | Liên kết final → proposal bị thay thế (giữ vết A→B) |
| Task | Công việc: What / Who (owner) / When (due) + `link_to_decision` |
| TBD | Giá trị không có trong transcript — trung thực để trống, cấm bịa |
| Explicit / inferred / tbd | Nguồn của owner/due: nói rõ / suy ra (đại từ, ngày tương đối) / không rõ |
| Due hint | Chữ gốc mơ hồ giữ lại khi due=TBD (vd: `"sớm nhé"`) |
| Evidence | Quote nguyên văn + timestamp + speaker + turn, khớp transcript ≥85% |
| Role in discussion | Vai trò của lượt thoại: `propose / object / decide / confirm / info` |
| Confidence đỏ/vàng/xanh | `<0.50 / 0.50–0.75 / ≥0.75`. Đỏ khóa export cho tới khi host xử lý |
| Gate đỏ | Quy tắc R6: còn thẻ đỏ chưa Đồng ý/Sửa/Loại thì nút Export bị khóa |
| No Decision | Họp không chốt gì — output hợp lệ, phải có ≥1 Open Issue kèm next_step |
| Open Issue | Nội dung chưa chốt + `next_step` bắt buộc + owner (hoặc TBD) |
| Unresolved reversal | Đảo A→B→A hoặc 2 final mâu thuẫn — hệ thống không tự chọn, đẩy cho host |
| Known limitations | Danh sách hạn chế đã biết, ghi trung thực vào output, không che giấu |
| Glossary (dự án) | Từ điển viết tắt/riêng của từng dự án (KH, VG, SLA...) đưa vào prompt context |
