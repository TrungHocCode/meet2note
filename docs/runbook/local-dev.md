# Runbook — setup local & chạy từng lớp

> Áp dụng sau khi hiện thực xong từng phase (P0→P3). Phase nào chưa xong thì bỏ qua bước đó.

## 1. Chuẩn bị

```powershell
Set-Location -LiteralPath "F:\AI\project\next_gen\meet2note"
Copy-Item .env.example .env   # điền OPENAI_BASE_URL + MODEL_NAME
pip install -r requirements.txt
```

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

## 4. Chạy test + eval

```powershell
pytest tests -q
python -m pipeline.cli eval   # 5 ca → eval/report.md
```
