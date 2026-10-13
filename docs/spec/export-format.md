# Spec - Export formats + review log + UI tối thiểu (P3)

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

- **Sidebar:** chọn meeting, filter theo confidence, nút Export (khoá/mở theo gate R6), đếm thẻ đỏ.
- **Main 4 cột:** Quyết định | Công việc | Vướng mắc & Chưa chốt | Yêu cầu & Phản hồi.
- **Thẻ:** content + badge màu confidence + evidence expandable (quote + timestamp + speaker)
  + 3 nút **Đồng ý / Sửa / Loại**.
- **Sửa inline:** content, owner, due, link_to_decision.
- **Discarded:** hiển thị thu gọn dưới final (`Lịch sử: thay thế D0`), không hiện ngang hàng.
- Gọi API: `GET/PUT /api/v1/review`, `POST /api/v1/export` (chi tiết: `spec/api-contract.md`).