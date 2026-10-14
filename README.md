# meet2note

Transcript cuộc họp → trạng thái có cấu trúc (Decision / Task / Blocker / Requirement /
Open Issue / Knowledge) kèm evidence → human review 2 phút → export `minutes.md` + `tasks_jira.csv`.

- Triết lý: **LLM đề xuất, code kiểm chứng, con người chốt.**
- Trạng thái: **MVP hoàn thành (P0–P6b + UI polish)** — pipeline 0.4.0, multi-user (Postgres + JWT),
  upload + review + export tải về trên UI. Tests: **261 passed**. Eval: fixture 5/5, live 5/5 —
  chi tiết: `eval/report.md`.
- Quy ước làm việc: `AGENTS.md`. Kiến trúc: `docs/c4/`. Spec: `docs/spec/`. Vận hành: `docs/runbook/`.

## 1. Yêu cầu

| Thứ | Ghi chú |
|---|---|
| Python 3.11+ (dùng `.venv` trong repo) | `.\.venv\Scripts\python.exe` trên Windows |
| Node 18+ (frontend) | `npm install` trong `frontend/` |
| Ollama + model `qwen3:4b-instruct-2507-q4_K_M` | `ollama pull qwen3:4b-instruct-2507-q4_K_M` |
| Docker (Postgres 16) | `docker compose up -d db` — port host **5434** |

## 2. Chạy lần đầu (5 bước)

```powershell
Set-Location -LiteralPath "F:\AI\project\next_gen\meet2note"

# 1. Env (gitignored — không commit)
Copy-Item .env.example .env
# Điền tối thiểu: LLM_BASE_URL=http://localhost:11434/v1
#                 LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M
#                 JWT_SECRET=<chuỗi ngẫu nhiên dài, vd: openssl rand -hex 32>

# 2. Libs
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Database
docker compose up -d db
.\.venv\Scripts\python.exe -m backend.db_cli migrate
.\.venv\Scripts\python.exe -m backend.db_cli create-admin --email <email> --password <mat-khau-8+ky-tu>

# 4. Server (2 terminal riêng, giữ nguyên khi dùng)
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --port 8000
cd frontend; npm install; npm run dev

# 5. Mở http://localhost:5173 → Đăng ký/Đăng nhập → Upload transcript → Review → Export → Tải file
```

Đồng bộ meetings/runs từ disk vào DB (tùy chọn, khi có sẵn `runs/`):

```powershell
.\.venv\Scripts\python.exe -m backend.db_cli sync-db --owner-email <email>
```

## 3. Luồng dùng thật (live E2E)

1. **Đăng nhập** (`http://localhost:5173`) — mỗi user chỉ thấy meeting của mình.
2. **Upload** (sidebar ③): file `.txt/.srt/.docx` + date (YYYY-MM-DD) + participants
   (mỗi dòng `Tên (role)`) → pipeline chạy qua Ollama vài phút → state hiện ngay để review.
3. **Review**: 4 cột + badge 🔴<0.50 / 🟡0.50–0.75 / 🟢≥0.75 → Đồng ý / Sửa / Loại từng thẻ.
   Bấm timestamp evidence → drawer transcript ±4 turns quanh câu gốc.
4. **Export**: hết thẻ đỏ mới mở nút (gate R6) → bấm **Tải minutes.md / tasks_jira.csv** về máy.
5. **Xem lại**: danh sách meeting ở sidebar ① — bấm là xem, không cần nhớ id.

## 4. Pipeline CLI (không cần server)

```powershell
.\.venv\Scripts\python.exe -m pipeline.cli run --meeting tc2            # ingest → extract → resolve → verify
.\.venv\Scripts\python.exe -m pipeline.cli eval                         # fixture, deterministic
.\.venv\Scripts\python.exe -m pipeline.cli eval --live                  # LLM thật, so golden
```

## 5. Test cases (5 ca, `data/transcripts/` + `data/golden/`)

| Ca | File | Kiểm gì | Kỳ vọng |
|---|---|---|---|
| tc1 | `tc1_happy.txt` — sprint planning | Decision cuối + task đủ owner/due, loại chốt giả ("chốt nghỉ trưa") | D.final đúng (Lan), 3 task khớp owner+due |
| tc2 | `tc2_atob.txt` — đảo A→B | Kill-criterion: chốt B thay A, giữ vết | D1.final=B, `supersedes=[D0]`; T1 link D1 |
| tc3 | `tc3_vague.txt` — brainstorm vòng vo | Không bịa quyết định; bẫy "chốt luôn" bị bác ngay | `no_decision=true` + Open Issue có next_step |
| tc4 | `tc4_entity.txt` — entity-linking | Đại từ → tên, ngày tương đối → ISO | owner/due đúng; không parse được → TBD |
| tc5 | `tc5_fail.txt` — đảo A→B→A | Trung thực khi mâu thuẫn không giải được | Flag `unresolved_reversal` + Open Issue cho host |

Đánh giá 4 trường/ca (Kỳ vọng → Kết quả → Đạt/Chưa đạt → Bài học) trong `eval/report.md`.
Quy tắc cứng R1–R8 (cấm bịa owner/deadline, cấm đoán ngày, quote phải khớp transcript…): `AGENTS.md` §4.

## 6. Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q        # 261 passed, 1 skipped (skip = test PG thật)
# Test PG thật: $env:TEST_DATABASE_URL='postgresql+psycopg://meet2note:meet2note@localhost:5434/meet2note'
.\.venv\Scripts\python.exe -m pytest tests/test_db.py -q
cd frontend; npm run build                            # verify UI (không bật server blocking)
```

Phủ: schema/ingest/verify/resolve/export (`test_*`), API + gate R6 (`test_api.py`),
auth + owner isolation (`test_auth.py`), download + meeting list, DB Postgres (`test_db.py`).

## 7. Cấu trúc

```
pipeline/   ingest → extract → resolve → verify → export → service → cli (lõi, độc lập)
backend/    api.py (lớp mỏng) + auth.py (JWT) + db/ (models/session) + db_cli.py (migrate/seed/sync)
frontend/   React + Tailwind v4 + shadcn: review 4 cột + brief + drawer + upload + login
prompts/    system_extract/resolve/brief + fewshot (tách khỏi code)
data/       transcripts/ meta/ golden/ — BẮT BUỌC synthetic (repo public)
eval/       runner.py + report.md + results_fixture/live.json
tests/      pytest (sqlite tmp, không chạm PG local)
runs/       output versioned, gitignored · docs/private/ PLAN + Mission1.docx, gitignored
```

## 8. Known limitations (trung thực)

- Model local nhỏ paraphrase, tính ngày sai (lưới deterministic R2 đỡ), variance theo input —
  xem `eval/report.md` (tc5 từng smoothing mâu thuẫn ở vòng P4).
- `data/` synthetic; transcript thật chỉ nằm ở `data/uploads/` (gitignored).
- Chưa có: bot auto-join, realtime, ASR/audio clips, sync API Jira/Slack, SSO, redaction PII —
  đúng scope MVP (Mission1: chỉ làm lớp nâng cấp).

## 9. Git

GitHub Flow: `main` luôn xanh, mọi thay đổi qua branch `feat/*` + PR (squash-merge),
không push thẳng `main`. Không commit: `.env`, transcript thật, `docs/private/`, `runs/`.
