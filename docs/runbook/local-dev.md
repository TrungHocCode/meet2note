# Runbook — setup local & chạy từng lớp

> Áp dụng sau khi hiện thực xong từng phase (P0→P3). Phase nào chưa xong thì bỏ qua bước đó.

## 1. Chuẩn bị

```powershell
Set-Location -LiteralPath "F:\AI\project\next_gen\meet2note"
Copy-Item .env.example .env   # điền OPENAI_BASE_URL + MODEL_NAME
pip install -r requirements.txt
```

### 1b. Dùng Ollama local (tạm thời, thay hosted LLM)

`.env` (gitignored — không commit):

```
OPENAI_BASE_URL=http://localhost:11434/v1
MODEL_NAME=qwen3:8b
LLM_TIMEOUT=300
```

- Không cần API key (Ollama local bỏ qua `Authorization` khi trống).
- Parser đã chịu được `<think>` + fence + lời dẫn của model local
  (bóc trước khi parse JSON, retry vẫn giữ).
- Chạy mock khi chưa có key: `python -m pipeline.cli run --meeting tc2 --llm-fixture data/fixtures/tc2_llm.json`

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
2. Sidebar → form "Upload transcript": chọn file `.txt/.srt`, điền id/title/date/participants → **Upload + chạy**.
3. Pipeline chạy đồng bộ (vài phút với model local) → state hiện ngay để review.
4. Bấm timestamp evidence bất kỳ → drawer transcript hiện ±4 turns quanh câu đó.
5. File upload nằm ở `data/uploads/` (gitignored — không bao giờ commit).

## 4. Chạy test + eval

```powershell
pytest tests -q
python -m pipeline.cli eval   # 5 ca → eval/report.md
```
