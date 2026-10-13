# ADR-0006 — Decision model làm arbitration scorer sau MVP (chưa chọn model cụ thể)

- Status: Proposed
- Date: 2026-10-13

## Context

Để xác định quyết định cuối của cuộc họp, có đề xuất dùng **decision model** (mô hình phân biệt:
nhận `state` + danh sách candidates, trả confidence từng candidate, có khả năng abstain/không chọn).
Luồng: LLM trích candidates + evidence, decision model chấm, chốt theo confidence cao nhất. Hấp dẫn vì:
ánh xạ 1-1 vào bài toán (state + options + abstain), option abstain trùng rule R3 (No Decision),
nhanh + rẻ hơn LLM ở scale.

Đã khảo sát sơ bộ 1 ứng viên (Jev, TypeSafe). Còn nhiều decision model khác benchmark cao hơn —
**chưa quyết định dùng model nào**. Lựa chọn để dành cho experiment, không chốt trong ADR này.

## Decision

- **MVP (P0–P2): giữ rules deterministic làm decider** (timestamp muộn nhất + role `decide` +
  câu chốt + chuỗi `supersedes`). Nhanh, giải thích được, test được trên 5 golden cases.
- **Decision model vào backlog, experiment ở P4:** bọc sau flag, chạy song song với rules trên tc1–tc5,
  so sánh trong `eval/report.md`. Thắng ở ca mờ mà không phá ca sạch → ADR mới để adopt + ghi tên
  model được chọn.
- **Tiêu chí chọn model (đo ở P4):** accuracy ca mờ + không phá ca sạch · latency · cost ở scale ·
  availability/self-host được hay không · hỗ trợ tiếng Việt. Không chọn theo benchmark của vendor
  trên dataset của họ.
- Tầng VERIFY (R1–R7) giữ nguyên trong mọi phương án — scorer không thay thế kiểm chứng bằng code.

## Consequences

- (+) MVP không dính dependency ngoài chưa kiểm chứng; không khóa vendor sớm.
- (+) Tránh `argmax` tự tin sai ở ca mờ (tc5: A→B→A, sarcasm) — đúng triết lý R4 (flag cho host, cấm tự chọn).
- (+) `review_log.json` tích lũy thành labeled data cho scorer fine-tune sau này.
- (−) Tốn thêm 1 experiment ở P4 (so nhiều model, không chỉ 1). Chấp nhận vì có 5 golden cases sẵn để đo.

## Alternatives considered

- Chốt 1 model cụ thể (Jev) ngay: loại vì chưa so benchmark giữa các decision model; khóa vendor sớm.
- Decision model làm decider ngay từ P1: loại vì confidence của scorer đo độ dứt khoát của phân phối,
  không phải P(đúng); evidence xấu → chọn sai nhưng tự tin (garbage in, confident out).
- Embedding similarity thay decision model: loại vì similarity đo liên quan chủ đề, không đo "quyết định cuối".
- Giữ rules mãi mãi: giữ làm baseline. Nếu không scorer nào vượt rules + gate host ở P4 thì không adopt.
