# Spec - API contract (`backend/api.py`, P2)

Service layer **mỏng** — đọc/ghi state từ `runs/`, KHÔNG chứa logic pipeline (ADR-0005).
Base URL local: `http://localhost:8000`. React dev: `http://localhost:5173` — CORS cho phép origin này.

## Endpoints

### GET /health

→ `200 {"status": "ok"}`

### GET /api/v1/review?meeting=tc2

Trả trạng thái hiện tại để React render 4 cột.

| Kết quả | Body |
|---|---|
| `200` | `meeting_state.json` (envelope + items + stats + known_limitations) |
| `404` | `{"detail": "meeting not found"}` — chưa chạy `cli run` |

### PUT /api/v1/review?meeting=tc2

Body: `{"items": [...], "changes": [{"item_id": "T2", "action": "edit", "old": {...}, "new": {...}}]}`

- Ghi `confirmed_state.json` (bản mới sau review) + **append** vào `review_log.json`.
- Actions: `agree | edit | remove` — mọi thay đổi phải có `changes` để audit (ADR-0004).

| Kết quả | Body |
|---|---|
| `200` | `{"ok": true, "stats": {...}}` |
| `422` | schema không hợp lệ (Pydantic) |

### POST /api/v1/export?meeting=tc2

Gate R6: export chỉ sau khi **mọi item đỏ (<0.50) đã được Đồng ý/Sửa/Loại**.

| Kết quả | Body |
|---|---|
| `403` | `{"error": "gate_red_items", "red_items": ["B1"]}` — còn thẻ đỏ, export bị khoá |
| `200` | `{"files": ["runs/tc2/<ts>/minutes.md", "runs/tc2/<ts>/tasks_jira.csv"]}` |

## Quy ước chung

- Error format: `{"detail": string}` (FastAPI mặc định); riêng gate dùng `{"error": code, ...}`.
- Tên file output: `minutes.md`, `tasks_jira.csv` — chi tiết: `spec/export-format.md`.
- CORS: `allow_origins=["http://localhost:5173"]` (dev), không mở wildcard.

## Transcript viewer + upload (P5)

### GET /api/v1/transcript?meeting=tc2

Trả turns để UI hiện context quanh evidence (±4 turns). Tìm ở `data/transcripts/`
trước, `data/uploads/` sau.

| Kết quả | Body |
|---|---|
| `200` | `{meeting, source, turns: [{turn, t_start, t_end, speaker, text}], limitations}` |
| `404` | `{"detail": "transcript not found"}` |

### POST /api/v1/meetings/upload (multipart/form-data)

Upload transcript + chạy pipeline ngay, trả state để review luôn.

Fields: `file` (.txt/.srt, bắt buộc) · `meeting_id` (trống = từ tên file, sanitize)
· `title` · `date` (YYYY-MM-DD, bắt buộc — R2) · `participants`
(JSON `[{name, role?, aliases?}]`, thiếu aliases → `[name]`) · `chunk_size` (40) · `overlap` (10).

| Kết quả | Body |
|---|---|
| `200` | `{meeting_id, state, turns_count, out_dir}` — file + meta lưu `data/uploads/` (gitignored) |
| `400` | sai ext/date/participants/file rỗng |
| `422` | parse transcript lỗi |
| `503` | thiếu LLM (Ollama chưa bật / chưa cấu hình `.env`) |