# docs — meet2note

> Tài liệu tech được track trong git, review qua PR. Chỉ `docs/private/` bị ignore (file nhạy cảm/coursework).

## Bản đồ đọc

| Thứ tự | File | Nội dung |
|---|---|---|
| 0 | `private/Mission1.docx` | Phân tích gốc (local-only, không push) — chỉ tham chiếu, không sửa |
| 1 | `glossary.md` | Ngôn ngữ chung — đọc trước để thống nhất từ vựng |
| 2 | `c4/01-context.md` | L1: hệ thống là gì, ai dùng, tương tác với gì |
| 3 | `c4/02-container.md` | L2: các khối React / FastAPI / pipeline CLI / filesystem |
| 4 | `c4/03-component.md` | L3: chi tiết pipeline ingest→extract→resolve→verify→export→store |
| 5 | `adr/` | Quyết định kiến trúc, mỗi quyết định 1 file, có status |
| 6 | `spec/taxonomy.md` | Hợp đồng 6 loại thông tin + 7 quy tắc cứng R1–R7 |
| 7 | `spec/eval-plan.md` | 5 kịch bản test + tiêu chí Đạt/Chưa đạt |
| 8 | `runbook/` | Setup local + kịch bản demo 5 phút |
| 9 | `spec/io-formats.md` | Định dạng transcript/turns/meta/golden + parse .txt/.srt (P0) |
| 10 | `prompts/` | system_extract, system_resolve, fewshot_atob — code load trực tiếp (P1) |
| 11 | `spec/api-contract.md` | GET/PUT /review, POST /export + gate R6 (P2) |
| 12 | `spec/export-format.md` | Template minutes.md + tasks_jira.csv + review_log + UI tối thiểu (P3) |
| 13 | `spec/acceptance.md` | Tiêu chí nghiệm thu MVP (P4) |

Spec thực thi MVP: `private/PLAN_MVP.md` (local-only, không push).
