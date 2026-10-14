# Eval plan — 5 kịch bản kiểm thử bắt buộc

## 1. Tiêu chí Đạt/Chưa đạt (chấm trước khi chạy)

- **Decision.final Đạt khi:** content đúng kết luận cuối như golden + `supersedes` đúng + evidence là câu chốt cuối khớp transcript + không liệt kê proposal ngang hàng.
- **Task Đạt khi:** what đúng + owner đúng (hoặc TBD đúng khi transcript thiếu) + due đúng ISO (hoặc TBD + hint khi mơ hồ) + link đúng.
- Runner so tự động trường then chốt với `data/golden/`; phần mơ hồ/sarcasm host chấm tay.
- **tc5 ghi Chưa đạt là kết quả hợp lệ** — kèm điều học được.

## 2. Năm transcripts (`data/transcripts/` + `meta/` + `golden/`)

| # | File | Bối cảnh / quy mô | Điểm khó | Kỳ vọng |
|---|---|---|---|---|
| tc1 | `tc1_happy.txt` ~90 lượt | Sprint planning: 1 QĐ rõ (chọn B), 3 task đủ owner+deadline, 1 blocker + nhiễu (CI hỏng, đùa chốt nghỉ trưa, giao-nhận task đảo rồi hoàn) | Tường minh nhưng nhiễu: chốt giả phải loại, timestamp evidence phải sửa về turn khớp | D.final=B; 3/3 task đủ; evidence đúng turn khớp |
| tc2 | `tc2_atob.txt` ~100 lượt | Chọn vendor: Nam đề xuất A + bào chữa vòng 2, decoy vendor Z, sarcasm nhẹ, QĐ phụ (lịch demo PoC), Lan chốt B | Đảo chiều + decoy + đa quyết định | D1.final=B supersedes=[D0], D0 discarded, evidence câu chốt cuối, T1 link D1 |
| tc3 | `tc3_vague.txt` ~85 lượt | Brainstorm vòng vo + **chốt giả** ("chốt luôn Stripe đi" rồi rút lại vì thiếu data) | Chống bịa + chống chốt giả | `no_decision=true`, ≥1 Open Issue + next_step, TBD + hint |
| tc4 | `tc4_entity.txt` ~80 lượt | Họp kỹ thuật: đại từ dày, code-switch, viết tắt UAT/PO/QA, deadline sửa-rồi-hoàn, `thứ 6 tuần sau nữa` (không parse → TBD), sarcasm | Quy đổi đại từ + ngày + nhiễu sửa đổi | owner inferred đúng, due ISO đúng, không tên ngoài participants |
| tc5 | `tc5_fail.txt` ~100 lượt — DỰ KIẾN THẤT BẠI | War A→B→A khốc liệt: hùng biện 2 phe, chốt ngắt câu (`chốt—` rồi lái), sarcasm ×2, deal riêng, 2 final đối đầu | Tất cả cùng lúc | Trung thực **Chưa đạt** + bài học |

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
