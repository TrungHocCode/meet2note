# Spec — Taxonomy 6 loại + Evidence + 8 quy tắc cứng

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
| Requirement/Feedback | `content, raised_by, origin customer\|internal\|partner\|unknown` | Yêu cầu hoặc phản hồi, kể cả từ bên ngoài; origin không xác định được → `unknown` (giữ item) |
| Open Issue | `content, next_step (bắt buộc — thiếu thì placeholder "Host xác định bước tiếp theo" + limitation), next_step_owner\|TBD` | Chưa chốt; họp không chốt gì ⇒ `no_decision=true` + ≥1 Open Issue |
| Evidence/Knowledge | `content, context, tags[]` | Tri thức/quy ước rút ra, không phải việc phải làm |

Mọi item có `confidence 0–1` + `confidence_reason`. Ngưỡng: đỏ <0.50 (khóa export) · vàng 0.50–0.75 · xanh ≥0.75.

## 4. Tám quy tắc cứng (enforce bằng code ở VERIFY/RESOLVE)

| # | Quy tắc | Enforce |
|---|---|---|
| R1 | Không bịa owner/deadline ⇒ `TBD` | `tbd` ⇒ confidence ≤0.4 (đỏ) |
| R2 | Cấm đoán ngày: `sớm/gấp/asap` ⇒ `due TBD + due_hint`; chỉ nhận ngày rõ hoặc tính deterministic từ `meeting.date` | Regex + quy đổi thứ/tuần bằng Python; không parse ISO ⇒ TBD. **Mở rộng (vòng transcripts v2):** due đã ISO nhưng hint còn pattern tương đối → recompute, khác thì OVERRIDE + limitation (model hay tính nhầm thứ→ngày); due ISO trước `meeting.date` → bất khả thi → TBD + limitation |
| R3 | `No Decision` hợp lệ | Không decision ⇒ `no_decision=true` + yêu cầu ≥1 Open Issue |
| R4 | Giữ vết supersedes; A→B→A không resolve ⇒ `unresolved_reversal` + Open Issue nhờ host | Graph check Python, không tự chọn |
| R5 | Mọi item (trừ Knowledge) ≥1 evidence khớp fuzzy ≥85% (difflib trên text normalize) | Không khớp ⇒ `evidence_mismatch`, thẻ đỏ |
| R6 | Không tự sync: export chỉ sau confirm | Gate ở React + backend check |
| R7 | Không xóa tranh luận | Phản đối vào `objections` của Decision |
| R8 | Toàn vẹn link: `link_to_decision` phải trỏ tới item TỒN TẠI | Không tồn tại (model link ID tưởng tượng) → null + limitation |

## 5. Công thức confidence (VERIFY — deterministic)

```
conf_final = clamp01(
  conf_llm
  + 0.10  nếu quote khớp transcript
  - 0.30  nếu evidence_mismatch
  - 0.15  mỗi trường TBD
  - 0.10  mỗi trường inferred
  - 0.20  nếu có mâu thuẫn (unresolved_reversal)
)
```

- Ngưỡng badge: đỏ `<0.50` (khoá export) · vàng `0.50-0.75` · xanh `≥0.75`.
- Quote verify: normalize (bỏ dấu câu + khoảng trắng dư) → `difflib.ratio ≥ 0.85`;
  thử lân cận ≤2 lượt; fail → `evidence_mismatch` (đỏ). Trừ Knowledge — không bắt buộc evidence.
- **Evidence ts sửa về turn khớp thật:** model hay gán sai timestamp vài giây dù quote đúng
  (live tc1: quote 04:14 gán ts 04:24) → verify đặt lại ts/turn/speaker theo turn khớp + limitation.
  Không sửa quote (nguyên văn là thiêng liêng — R5).
- **Contradiction chỉ phạt finals SỐNG SÓT:** penalty -0.20 áp sau validate (item rớt không tính),
  tính lại badge sau phạt. Tránh phạt oan như bản cũ (đếm trên raw input).
- **Substring fallback** (vì ratio 0.85 sai toán học với quote ngắn trong turn dài):
  quote ≥10 ký tự nằm nguyên trong turn + coverage ≥30% → tính khớp.
- **Role normalize:** `role_in_discussion` ngoài 5 giá trị → `"info"` + ghi limitation
  (accept-with-flag: role là metadata phụ, không đáng reject chunk; khác silent default
  vì có vết audit trong `known_limitations`).
- **Stats shape** (`Stats` model, không dict phẳng): `by_type{type: count}`,
  `items_total`, `by_badge{red|yellow|green: count}`.

## 6. R3-fallback khi LLM trắng final (system OpenIssue)

- Trắng final + không Open Issue → verify tự tổng hợp `O_SYS`
  (`system_generated=true`, confidence 0.0 = đỏ, `next_step` cho host).
  `O_SYS` được miễn evidence (không trích từ transcript nên không thể có quote).
- `no_decision=True` hợp lệ nhờ O_SYS → export bị KHÓA (thẻ đỏ) tới khi host xử lý.
  Đây là phía đúng: trắng trạng thái mà gắn `False` là nói dối nhẹ.

## 7. Resolve rules (pass-2 — deterministic, không để LLM tự chọn)

- **Merge trùng:** cùng chủ đề + speaker + bằng chứng → gộp 1, ghi `merged_ids`.
- **Hạ final thiếu câu chốt thật → proposal** (glossary "Chốt vs nói chơi"): evidence role=decide
  nhưng quote là tường thuật ("Em note lại: chốt...") cũng không tính — chỉ ghi chú/đồng thuận
  lại ≠ chốt. Giữ làm proposal để audit.
- **Gộp finals CÙNG nội dung khác id** (model đặt D0/D1 cho cùng 1 chốt ở 2 chunk):
  winner = evidence decide không-recap muộn nhất; union evidence + supersedes (bỏ self-ref).
  Khác nội dung thì giữ nguyên để reversal detection xử.
- **Tách id-collision task:** model tái dùng T1..Tn mỗi chunk cho task khác nhau → cùng id +
  khác nội dung (non-decision) = collision, không phải conflict → tách cluster, rename id mới
  (`T2_2`) + limitation. Text quá ngắn (<2 tokens significant) thì không đủ phân biệt → trọng
  tài như cũ (mất task thật tệ hơn trùng task).
- **Gộp task trùng khác id:** cùng owner (non-TBD) + cùng due ISO (non-TBD) + overlap what →
  giữ bản đầu + union hint/link/evidence từ bản thua.
- **Nối supersedes xuyên chunk:** mỗi vấn đề tối đa 1 `final`; cũ → `discarded` (R4).
- **A→B→A hoặc 2 final cùng chủ đề** → `unresolved_reversal=true` + Open Issue cho host — không tự chọn (R4).
- **Entity-link người:** chỉ chấp nhận `name`/`aliases` trong `participants` (em/anh/chị → name,
  source=inferred); không khớp → TBD. Tên ngoài participants là SAI.
- **Entity-link ngày** (regex + Python, từ `meeting.date`): `thứ 2..CN`, `tuần sau`, `ngày N/M`,
  `cuối tháng` → ISO deterministic; mơ hồ → `due=TBD` + `due_hint` giữ nguyên gốc (R2).

## 8. Meeting brief (vấn đề + kết quả — tư duy business)

- Họp người thật hiếm khi tuyên bố mục đích rõ ràng — brief do LLM tổng hợp từ toàn transcript:
  `problem` (1–2 câu: vấn đề họp giải quyết, không phải agenda chung chung) +
  `outcomes[]` (mỗi kết quả 1 dòng + `ref_ids` trỏ tới Decision/OpenIssue ID).
- **Luật business cốt lõi:** "nói ra" ≠ "chốt". Một phát biểu chỉ thành Decision khi có câu chốt rõ +
  người chốt + đồng thuận (ngầm/hiển) — nói suông/ví dụ/đùa không thành item.
  Cơ chế enforce: outcome MUỐN ghi nhận kết quả nào thì BẮT BUỘC trỏ tới ID đã chốt —
  không ID tương ứng thì outcome đó không tồn tại (verify bỏ + limitation).
- Verify: mỗi `ref_id` phải tồn tại trong items đã validate; outcome rỗng ref hoặc ref ma → bỏ
  outcome + limitation. Brief không có evidence riêng (nó là tổng hợp từ items đã có evidence).
