# Spec - Nghiệm thu MVP (acceptance criteria)

Nguồn: PLAN_MVP §9. Kiểm lúc **P4** — sau khi eval chạy xong 5 ca và README hoàn thiện.

## Done = (7 tiêu chí)

| # | Tiêu chí | Cách kiểm |
|---|---|---|
| 1 | Demo end-to-end <5 phút: transcript → `run` → React review → export md+csv | `docs/runbook/demo-5min.md` |
| 2 | **tc2 Đạt:** D.final=B + supersedes + D0 discarded + evidence câu chốt cuối (45:30) | `eval/report.md` |
| 3 | Đủ 5/5 ca theo 4 trường (Kỳ vọng → Kết quả → Đạt/Chưa đạt → Bài học); **tc5 Chưa đạt vẫn tính hoàn thành nếu trung thực** | `eval/report.md` |
| 4 | Audit 10 task: owner/due hoặc đúng nguồn (explicit/inferred + evidence) hoặc TBD — **không bịa** | check mẫu 10 task |
| 5 | tc3 ra đỏ/vàng + TBD + due_hint — **không có xanh giả** | `eval/report.md` |
| 6 | Gate hoạt động: còn thẻ đỏ → POST export trả 403; xử lý xong → 200 | test tay / pytest |
| 7 | README ghi cách chạy + `known_limitations` | review README |

## Chấm điểm

- **7/7** → nghiệm thu.
- Thiếu ≤1 tiêu chí (trừ #2) → ghi rõ vào report, chấp nhận nếu có lý do trung thực.
- **#2 tc2 THẤT BẠI → KHÔNG nghiệm thu** — A→B là ca lõi nhất; phải tìm nguyên nhân, sửa prompt, chạy lại. (Đây là "Code kiểm chứng" trong triết lý "LLM đề xuất, code kiểm chứng, con người chốt".)