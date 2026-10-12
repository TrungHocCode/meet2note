# Spec — Taxonomy 6 loại + Evidence + 7 quy tắc cứng

Nguồn: `PLAN_MVP.md` §3. File này là hợp đồng chi tiết để hiện thực `schema.py`.
Định nghĩa từ vựng: `glossary.md`.

## 1. Envelope

`meeting{id, title, date, participants[name, role, aliases], source_file, pipeline_version, generated_at}`
+ `items[]` + `no_decision` + `stats` + `known_limitations`.

## 2. Evidence dùng chung (bắt buộc mỗi item)

`{quote (nguyên văn, cấm viết lại), timestamp HH:MM:SS, speaker (chuẩn hóa theo participants), turn, role_in_discussion: propose|object|decide|confirm|info}`.

## 3. Sáu loại

| Loại | Trường bắt buộc | Ghi chú |
|---|---|---|
| Decision | `content, status final\|discarded\|proposal, decided_by, reason, supersedes[]`, `objections[]` optional | Final duy nhất mỗi vấn đề; cũ → `discarded`, giữ vết `supersedes`; phản đối lưu `objections`, không xóa |
| Task | `what, owner\|TBD, owner_source, due ISO\|TBD, due_source, due_hint, link_to_decision` | Thiếu ⇒ TBD; `due_hint` giữ chữ gốc (`sớm nhé`); source `explicit\|inferred\|tbd` |
| Blocker/Risk | `content, needs_action_from\|TBD, severity high\|medium\|low` | Việc bị chặn, cần ai gỡ |
| Requirement/Feedback | `content, raised_by, origin customer\|internal\|partner` | Yêu cầu hoặc phản hồi, kể cả từ bên ngoài |
| Open Issue | `content, next_step (bắt buộc), next_step_owner\|TBD` | Chưa chốt; họp không chốt gì ⇒ `no_decision=true` + ≥1 Open Issue |
| Evidence/Knowledge | `content, context, tags[]` | Tri thức/quy ước rút ra, không phải việc phải làm |

Mọi item có `confidence 0–1` + `confidence_reason`. Ngưỡng: đỏ <0.50 (khóa export) · vàng 0.50–0.75 · xanh ≥0.75.

## 4. Bảy quy tắc cứng (enforce bằng code ở VERIFY)

| # | Quy tắc | Enforce |
|---|---|---|
| R1 | Không bịa owner/deadline ⇒ `TBD` | `tbd` ⇒ confidence ≤0.4 (đỏ) |
| R2 | Cấm đoán ngày: `sớm/gấp/asap` ⇒ `due TBD + due_hint`; chỉ nhận ngày rõ hoặc tính deterministic từ `meeting.date` | Regex + quy đổi thứ/tuần bằng Python; không parse ISO ⇒ TBD |
| R3 | `No Decision` hợp lệ | Không decision ⇒ `no_decision=true` + yêu cầu ≥1 Open Issue |
| R4 | Giữ vết supersedes; A→B→A không resolve ⇒ `unresolved_reversal` + Open Issue nhờ host | Graph check Python, không tự chọn |
| R5 | Mọi item (trừ Knowledge) ≥1 evidence khớp fuzzy ≥85% (difflib trên text normalize) | Không khớp ⇒ `evidence_mismatch`, thẻ đỏ |
| R6 | Không tự sync: export chỉ sau confirm | Gate ở React + backend check |
| R7 | Không xóa tranh luận | Phản đối vào `objections` của Decision |
