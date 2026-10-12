# Eval plan — 5 kịch bản kiểm thử bắt buộc

## 1. Tiêu chí Đạt/Chưa đạt (chấm trước khi chạy)

- **Decision.final Đạt khi:** content đúng kết luận cuối như golden + `supersedes` đúng + evidence là câu chốt cuối khớp transcript + không liệt kê proposal ngang hàng.
- **Task Đạt khi:** what đúng + owner đúng (hoặc TBD đúng khi transcript thiếu) + due đúng ISO (hoặc TBD + hint khi mơ hồ) + link đúng.
- Runner so tự động trường then chốt với `data/golden/`; phần mơ hồ/sarcasm host chấm tay.
- **tc5 ghi Chưa đạt là kết quả hợp lệ** — kèm điều học được.

## 2. Năm transcripts (`data/transcripts/` + `meta/` + `golden/`)

| # | File | Bối cảnh / quy mô | Điểm khó | Kỳ vọng |
|---|---|---|---|---|
| tc1 | `tc1_happy.txt` ~50 lượt | Sprint planning: 1 QĐ rõ (chọn B), 3 task đủ owner+deadline, 1 blocker | Không — tường minh | D.final=B xanh; 3/3 task đủ; evidence 100% |
| tc2 | `tc2_atob.txt` ~70 lượt | Chọn vendor: Nam đề xuất A (10'), Lan phản đối + chốt B (45'), task gắn B | Đảo chiều, giữ lý do | D1.final=B supersedes=[D0], D0 discarded, evidence 45:30, T1 link D1 |
| tc3 | `tc3_vague.txt` ~60 lượt | Brainstorm vòng vo: `sẽ xem xét`, `sớm nhé`, `anh em triển khai nhé`, không chốt | Chống bịa | `no_decision=true`, ≥1 Open Issue + next_step, TBD + hint, confidence đỏ/vàng |
| tc4 | `tc4_entity.txt` ~80 lượt | Họp kỹ thuật: `em/anh/chị`, `tuần sau/thứ 6/cuối tháng`, viết tắt KH/VG/SLA | Quy đổi đại từ + ngày | owner inferred đúng, due ISO đúng, không tên ngoài participants |
| tc5 | `tc5_fail.txt` ~90 lượt — DỰ KIẾN THẤT BẠI | Họp căng: đảo A→B→A, 2 QĐ mâu thuẫn, chồng lấn speaker, sarcasm `A 'tuyệt vời' lắm` | Tất cả cùng lúc | Trung thực **Chưa đạt** + bài học (cần module chồng lấn / pass-3 arbitration) |

Mỗi transcript: tiếng Việt, timestamp tăng dần, ≥3 speaker. `meta.json`: `{id, title, date, participants[], glossary{}}`.
`golden`: JSON kỳ vọng tối thiểu `{decisions_final[], tasks[], no_decision}` để runner so.

## 3. Template report (copy cho 5 ca vào `eval/report.md`)

```markdown
## tc2 — Đảo A→B sạch
- **Kỳ vọng:** D1.final=B supersedes=[D0], evidence 00:45:30, reason chi phí 30%; T1 Nam 2026-10-12 link D1
- **Kết quả thực tế:** (điền sau khi chạy)
- **Đạt/Chưa đạt:** Decision ☐ Đạt ☐ Chưa đạt · Task ☐ · Evidence ☐
- **Điều học được:** (điền sau khi chạy)
```
