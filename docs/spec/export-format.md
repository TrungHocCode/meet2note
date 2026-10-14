# Spec - Export formats + review log (P3)

Nguồn: PLAN_MVP §5. **EXPORT chỉ chạy sau confirm** (R6 — API từ chối 403 nếu còn thẻ đỏ).

## 1. minutes.md (Jinja2 template)

```markdown
# Biên bản họp - {title} — {date}
**Trạng thái:** Đã confirm · Pipeline {pipeline_version}

## ✅ Quyết định
- **{id} - {content}** (bởi {decided_by} · {confidence} {badge}) - Lý do: {reason}. Thay thế {supersedes}.
  - 🎯 [{timestamp}] {speaker}: "{quote}"
  - ⛔ Objection: [{ts}] {speaker}: "{quote}"

## 📌 Công việc
- [ ] {id} {what} - {owner} · {due} · link {link_to_decision} {badge}

## ⚠️ Vướng mắc & Chưa chốt
- {id} {content} (cần {needs_action_from}) {badge}

## 📋 Yêu cầu & Kiến thức
- {id} {content} ({origin}) {badge}

---
*Hạn chế: {known_limitations}*
```

- Badge: 🟢 `≥0.75` · 🟡 `0.50-0.75` · 🔴 `<0.50` (đỏ không xuất hiện nếu gate đã chặn).
- Discarded không in thành mục riêng — chỉ ghi dòng "Thay thế D0" trong item final.

## 2. tasks_jira.csv

Cột (import Jira thủ công — MVP không gọi API):
`Summary,Issue Type,Assignee,Due Date,Labels,Description`

```csv
Summary,Issue Type,Assignee,Due Date,Labels,Description
"[D1] Gửi báo giá B",Task,Nam,2026-10-12,"tc2;decision-D1","Evidence [00:46:05] Nam: '...'"
"[T2] Kiểm tra SLA",Task,,,,Owner TBD - cần gán
```

Quy tắc:
- Owner/Due = TBD → ô trống + ghi chú vào Description (`Owner TBD - cần gán`).
- Cột Summary prefix: `[D1]`, `[T2]`... để trace về decision.
- Labels: `{meeting_id};decision-{id}` hoặc `{meeting_id};task-{id}`.

## 3. review_log.json (ghi mỗi lần host sửa — audit)

```json
{
  "meeting_id": "tc2",
  "entries": [
    {"item_id": "T2", "action": "edit",
     "old": {"owner": "TBD"}, "new": {"owner": "Nam"},
     "reviewer": "host", "ts": "2026-10-13T10:00:00Z"}
  ]
}
```

- Actions: `agree | edit | remove` — **append**, không sửa entry cũ (ADR-0004: audit ai sửa gì).

## 4. UI tối thiểu (React 1 trang)

> **Đã chuyển sang tài liệu chuyên biệt** — mục này chỉ giữ 1 dòng để tránh 2 nguồn sự thật:
> - Công nghệ + token: `docs/adr/0008-tailwind-shadcn-va-design-tokens.md`, `docs/design/tokens.md`
> - Bố cục / component / trạng thái: `docs/design/layout.md`, `docs/design/components.md`
> - Hành vi (schema↔UI, R1–R8, bàn phím) + acceptance: `docs/spec/ui-spec.md`
>
> Tóm gọn bất biến: sidebar (meeting · review · upload) + **4 cột** Quyết định / Công việc /
> Vướng mắc & Chưa chốt / Yêu cầu & Phản hồi + drawer transcript ±4 lượt + gate R6 khoá Export.
> Gọi API: `GET/PUT /api/v1/review`, `POST /api/v1/export` (`spec/api-contract.md`).