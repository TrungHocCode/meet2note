# Runbook — kịch bản demo 5 phút (dùng khi nghiệm thu MVP)

Tổng <5 phút. Chuẩn bị sẵn: `.env` có key, `tc2` đã `run` 1 lần thành công.

| Phút | Bước | Điểm cần show |
|---|---|---|
| 0:00–0:30 | Mở transcript `tc2_atob.txt`: chỉ ra dòng đề xuất A (10') và dòng chốt B (45') | Ca khó A→B |
| 0:30–1:30 | Chạy `cli run --meeting tc2`, mở `state.json`: D1.final=B, supersedes=[D0], evidence 45:30 | Giữ đúng kết luận cuối |
| 1:30–3:00 | Mở React review: 4 cột, badge xanh/vàng, 1 thẻ đỏ TBD; sửa owner 1 click | Human-confirm 2 phút |
| 3:00–3:30 | Bấm Export khi còn thẻ đỏ ⇒ bị khóa (gate R6); xử lý xong ⇒ mở | Gate hoạt động |
| 3:30–4:30 | Mở `minutes.md` + `tasks_jira.csv`; mở `report.md` 5 ca (tc5 Chưa đạt trung thực) | Export + trung thực |
| 4:30–5:00 | Đọc `known_limitations` trong state | Không che giấu hạn chế |

Fail-safe: nếu LLM API chậm, dùng `state.json` của lần chạy trước trong `runs/` để demo tiếp.
