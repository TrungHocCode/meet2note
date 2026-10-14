# Spec - API contract (`backend/api.py`, P2 + P6b auth)

Service layer **mỏng** — đọc/ghi state từ `runs/`, KHÔNG chứa logic pipeline (ADR-0005).
Base URL local: `http://localhost:8000`. React dev: `http://localhost:5173` — CORS cho phép origin này.

## §0. Auth (P6b) — mọi /api/v1/* yêu cầu Bearer access token

- Access token: JWT HS256, TTL 60 phút, gửi qua header `Authorization: Bearer <token>`.
- Refresh token: opaque 32 bytes, lưu **hash** ở `refresh_tokens`, TTL 7 ngày,
  trao qua cookie httpOnly `refresh_token` (path `/auth`, SameSite=Lax).
- Meeting bị giới hạn theo owner: không tồn tại HOẶC không phải của mình
  → `404 {"detail": "meeting not found"}` như nhau (không lộ sự tồn tại).
- Thiếu/sai token → `401 {"detail": "..."}`.

### POST /auth/register

Body `{"email": "...", "password": "≥8 ký tự"}`.

| Kết quả | Body |
|---|---|
| `201` | `{"id": "<uuid>", "email": "..."}` |
| `409` | `{"detail": "email đã tồn tại"}` |

### POST /auth/login

Form `username=<email>&password=...` (OAuth2PasswordRequestForm).
| Kết quả | Body |
|---|---|
| `200` | `{"access_token": "...", "token_type": "bearer"}` + set cookie `refresh_token` |
| `401` | `{"detail": "email hoặc mật khẩu sai"}` |

### POST /auth/refresh — POST /auth/logout — GET /auth/me

| Endpoint | Kết quả |
|---|---|
| `POST /auth/refresh` (đọc cookie) | `200` access mới + xoay refresh · `401` không cookie/hết hạn/bị revoke |
| `POST /auth/logout` | `200 {"ok": true}` + revoke refresh hiện tại + xoá cookie |
| `GET /auth/me` (Bearer) | `200 {"id", "email"}` · `401` không token |

### GET /api/v1/meetings (Bearer bắt buộc)

Danh sách meeting của chính mình (mới nhất trước) kèm run mới nhất —
để UI hiện danh sách bấm xem lại, user không cần nhớ id.

| Kết quả | Body |
|---|---|
| `200` | `{meetings: [{id, title, date, source, created_at, runs_count, latest_ts, badges, no_decision}]}` |
| `401` | thiếu/sai access token |

## Endpoints

### GET /health

→ `200 {"status": "ok"}`

### GET /api/v1/review?meeting=tc2 (Bearer bắt buộc)

Trả trạng thái hiện tại để React render 4 cột.

| Kết quả | Body |
|---|---|
| `200` | `meeting_state.json` (envelope + items + stats + known_limitations) |
| `401` | thiếu/sai access token |
| `404` | `{"detail": "meeting not found"}` — chưa chạy `cli run` HOẶC không phải của mình |

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
Gate đọc `review_log.json`: id nào đã có entry xử lý thì không chặn nữa
(không đọc state.json thô — nếu không host xử lý xong vẫn bị 403 mãi).

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

### POST /api/v1/meetings/upload (multipart/form-data, Bearer bắt buộc)

Upload transcript + chạy pipeline ngay, trả state để review luôn.
Ghi `meetings` (upsert, owner = user hiện tại) + `runs` (mỗi upload 1 run mới).
`meeting_id` đã thuộc user khác → `409`.

Fields: `file` (.txt/.srt, bắt buộc) · `meeting_id` (trống = từ tên file, sanitize)
· `title` · `date` (YYYY-MM-DD, bắt buộc — R2) · `participants`
(JSON `[{name, role?, aliases?}]`, thiếu aliases → `[name]`) · `chunk_size` (40) · `overlap` (10).

| Kết quả | Body |
|---|---|
| `200` | `{meeting_id, state, turns_count, out_dir}` — file + meta lưu `data/uploads/` (gitignored) |
| `400` | sai ext/date/participants/file rỗng |
| `422` | parse transcript lỗi |
| `503` | thiếu LLM (Ollama chưa bật / chưa cấu hình `.env`) |