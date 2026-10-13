# meet2note

Transcript cuộc họp → trạng thái có cấu trúc (Decision / Task / Blocker / Requirement /
Open Issue / Knowledge) kèm evidence → human review 2 phút → export `minutes.md` + `tasks_jira.csv`.

- Triết lý: **LLM đề xuất, code kiểm chứng, con người chốt.**
- Trạng thái: **MVP nghiệm thu (P4)** — pipeline 0.4.0, 190 tests xanh, eval 5/5 ca
  (4 đạt live + tc5 thất bại trung thực đúng dự kiến). Chi tiết: `eval/report.md`.
- Quy ước làm việc: `AGENTS.md`. Kiến trúc: `docs/c4/`. Spec: `docs/spec/`.

## Chạy nhanh

```powershell
Copy-Item .env.example .env   # hosted LLM, hoặc Ollama local:
# OPENAI_BASE_URL=http://localhost:11434/v1
# MODEL_NAME=qwen3:4b-instruct-2507-q4_K_M
# LLM_TIMEOUT=300
# LLM_JSON_MODE=1
pip install -r requirements.txt
python -m pipeline.cli run --meeting tc2            # ingest → extract → resolve → verify
python -m pipeline.cli eval                         # fixture, deterministic
python -m pipeline.cli eval --live                  # LLM thật, so golden
pytest tests -q                                     # 190 tests
```

Review + export:

```powershell
python -m uvicorn backend.api:app --reload          # :8000 (bạn tự bật, agent không bật)
Set-Location frontend; npm install; npm run dev     # :5173
```

## Cấu trúc

`pipeline/` (ingest→extract→resolve→verify→export→cli) · `backend/api.py` (adapter mỏng) ·
`frontend/` (React 1 trang review) · `prompts/` · `data/` (transcripts/meta/golden synthetic) ·
`eval/` (runner + report) · `tests/` · `docs/` · `runs/` (output local, gitignored).

## Known limitations (trung thực)

- Model local nhỏ paraphrase, tính ngày sai (lưới deterministic đỡ), làm mượt mâu thuẫn
  (tc5 live không flag được — xem `eval/report.md`).
- Chunk 40/overlap 10 cho model context 4k (hosted dùng 80/10).
- Chưa có: speaker chồng lấn, sarcasm riêng, sync API Jira, auth/multi-user.
