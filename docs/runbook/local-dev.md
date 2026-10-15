# Runbook — setup local & chạy từng lớp

> Áp dụng sau khi hiện thực xong từng phase (P0→P3). Phase nào chưa xong thì bỏ qua bước đó.

## 1. Chuẩn bị

```powershell
cd meet2note   # thư mục repo vừa clone
Copy-Item .env.example .env   # điền LLM_BASE_URL + LLM_MODEL (Ollama local)
pip install -r requirements.txt
```

### 1b. Dùng Ollama local (mặc định — thay hosted LLM)

`.env` (gitignored — không commit):

```
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M
LLM_TIMEOUT=300
LLM_JSON_MODE=1
LLM_NUM_CTX=8192
# LLM_STRUCTURED=1  # ép json_schema từ Pydantic (thử nghiệm, xem §1c)
```

- Không cần API key (Ollama local bỏ qua `Authorization` khi trống).
- Parser đã chịu được `<think>` + fence + lời dẫn của model local
  (bóc trước khi parse JSON, retry vẫn giữ).
- Tên cũ `OPENAI_BASE_URL`/`MODEL_NAME` vẫn dùng được (fallback).
- Chạy mock khi chưa có key: `python -m pipeline.cli run --meeting tc2 --llm-fixture data/fixtures/tc2_llm.json`

### 1c. Constrained decoding (thử nghiệm)

`LLM_STRUCTURED=1` gửi JSON Schema sinh từ Pydantic `Literal` theo request —
model bị ép chọn trong tập cho phép (type/status/role/...) ngay khi sinh,
thay vì để bịa rồi validate sau. Provider không hỗ trợ `response_format`
thì tự fallback plain + warning (không chết chunk).

## 2. Chạy pipeline CLI (không cần server — P0/P1)

```powershell
python -m pipeline.cli run --meeting tc2
# output: runs/tc2/<timestamp>/state.json
```

## 3. Chạy API + React (P2/P3)

```powershell
python -m uvicorn backend.api:app --reload   # :8000, GET /health
Set-Location frontend; npm install; npm run dev
```

## 3b. Upload transcript + chạy trực tiếp trên UI (P5)

1. Bật API + React như §3 (bạn tự bật trong terminal riêng — agent không bật server).
2. Sidebar → form "Upload transcript": chọn file `.txt/.srt/.docx`, điền id/title/date/participants → **Upload + chạy**.
3. Pipeline chạy đồng bộ (vài phút với model local) → state hiện ngay để review.
4. Bấm timestamp evidence bất kỳ → drawer transcript hiện ±4 turns quanh câu đó.
5. File upload nằm ở `data/uploads/` (gitignored — không bao giờ commit).
6. Muốn thử ngay: dùng 3 file mẫu trong `samples/` (dễ → khó) + meta gợi ý trong
   `samples/README.md`.

## 4. Chạy test + eval

```powershell
pytest tests -q
python -m pipeline.cli eval   # 5 ca → eval/report.md
```

## 5. Database Postgres (P6a)

```powershell
docker compose up -d db                                  # Postgres :5434 (tránh 5432 native, 5433 project khác)
python -m backend.db_cli migrate                         # alembic upgrade head
python -m backend.db_cli create-admin --email admin@local --password <pass-8+kt>
python -m backend.db_cli sync-db --owner admin@local     # quét runs/ upsert (chạy lại không duplicate)
```

- `.env`: `DATABASE_URL` (mặc định đã trỏ `localhost:5434`, không cần set nếu dùng default),
  `ADMIN_EMAIL`/`ADMIN_PASSWORD` (thay cho flag), `JWT_SECRET` (P6b mới dùng).
- Test PG thật: `$env:TEST_DATABASE_URL='postgresql+psycopg://meet2note:meet2note@localhost:5434/meet2note'; pytest tests/test_db.py -q`.
