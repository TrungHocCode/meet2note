# AGENTS.md — Hướng dẫn agent làm việc trong meet2note

opencode tự nạp file này vào context đầu mỗi session. Đọc kỹ trước khi làm việc.

## 1. Mục đích & triết lý

Chuyển **transcript cuộc họp có sẵn** (txt/srt + timestamp + speaker) → **trạng thái có cấu trúc**
(6 loại item kèm evidence) → **human review 2 phút** → **export minutes.md + tasks_jira.csv**.

- Triết lý xuyên suốt: **"LLM đề xuất, code kiểm chứng, con người chốt."**
- MVP prototype 1-2 ngày: KHÔNG làm production, UI đẹp, realtime, ASR, sync API, auth.
- Chi tiết: `docs/c4/01-context.md`, `docs/runbook/local-dev.md`.

## 2. Bản đồ repo

| Đường dẫn | Nội dung |
|---|---|
| `pipeline/` | **Lõi** (root, độc lập): `schema ingest extract resolve verify export service cli` (`service.run_pipeline` dùng chung cho CLI + API) |
| `backend/api.py` | Lớp mỏng FastAPI: review (GET/PUT), export (POST + gate R6), transcript viewer (GET), upload chạy pipeline (POST) |
| `backend/db/` | SQLAlchemy models + session + security (P6a); `backend/db_cli.py` ops (migrate/seed/sync) |
| `docker-compose.yml` | Postgres 16 local, port host **5434** (tránh 5432 native, 5433 project khác) |
| `frontend/` | React review: 4 cột + brief + drawer transcript (±4 turns) + form upload |
| `prompts/` | `system_extract.md`, `system_resolve.md`, `system_brief.md`, `fewshot_atob.md` — tách khỏi code |
| `data/` | `transcripts/` `meta/` `golden/` — **bắt buộc SYNTHETIC** (repo public); `uploads/` gitignored (file người dùng) |
| `tests/` | `test_schema test_ingest test_verify test_resolve test_api test_export` (+ `test_eval` nếu có) |
| `eval/` | `runner.py` (fixture + live, so golden) + `report.md` + `results_*.json` |
| `runs/` | Output versioned, gitignored: `state.json confirmed.json review_log.json llm_log.jsonl` |
| `docs/` | `c4/` (kiến trúc), `adr/` (quyết định), `spec/` (taxonomy, io-formats, api-contract, export-format, eval-plan, acceptance), `runbook/`, `glossary.md` |
| `docs/private/` | 🔒 gitignored — PLAN_MVP.md + Mission1.docx. **KHÔNG commit, KHÔNG trích nội dung vào output public** |

## 3. Lệnh chạy

```powershell
python -m pipeline.cli run --meeting tc2     # pipeline CLI (độc lập, không cần server)
python -m pipeline.cli eval                  # chạy 5 ca → eval/report.md
python -m uvicorn backend.api:app --reload   # API :8000 (P2+)
pytest tests -q                              # test
```

## 4. Schema — 6 loại item + 8 quy tắc cứng

Chi tiết đầy đủ: `docs/spec/taxonomy.md`. Tóm tắt:

- **6 loại:** Decision (final/discarded + supersedes), Task (what/owner/due + link_to_decision),
  Blocker, Requirement, Open Issue (bắt buộc next_step), Knowledge.
- **Mỗi item:** `confidence 0-1` + `confidence_reason` + ≥1 evidence trừ Knowledge.
- **Evidence:** quote **nguyên văn** (cấm viết lại) + timestamp + speaker + turn + `role_in_discussion`.

| # | Quy tắc cứng (enforce bằng code, KHÔNG tin LLM) |
|---|---|
| R1 | Không bịa owner/deadline → `TBD` |
| R2 | Cấm đoán ngày + deterministic override (due ISO sai → recompute từ hint; due quá khứ → TBD) |
| R3 | Họp không chốt gì → `no_decision=true` + ≥1 Open Issue có next_step (trắng hẳn → O_SYS) |
| R4 | Giữ vết `supersedes`; A→B→A không tự chọn → `unresolved_reversal` + Open Issue cho host |
| R5 | Quote khớp transcript (fuzzy/substring); ts sai → sửa về turn khớp thật; không khớp → `evidence_mismatch` |
| R6 | Export chỉ sau confirm (gate ở React + backend) |
| R7 | Không xoá tranh luận → lưu vào `objections` của Decision |
| R8 | `link_to_decision` phải trỏ ID tồn tại, không thì null + limitation |

**Confidence:** `<0.50` đỏ (khoá export) · `0.50-0.75` vàng · `≥0.75` xanh.

## 5. Quy ước hiện thực

- `pipeline/schema.py` (Pydantic v2) là **single source of truth** — đổi schema = sửa prompt + UI + golden cùng lúc.
- LLM: temp ~0, JSON mode, retry ≤2 lần khi validate fail, chunk ~80 lượt overlap 10.
- Entity-linking: đổi `em/anh/chị/tên` → tên trong `participants`; ngày tương đối → ISO từ `meeting.date`
  (tính deterministic bằng Python); không suy ra được → TBD. Tên ngoài participants là sai.
- LLM qua env `LLM_BASE_URL` + `LLM_MODEL` (Ollama-first; fallback tên cũ `OPENAI_*`) — không khoá vendor.
- Ép shape ở request: `LLM_JSON_MODE=1` (json_object) hoặc `LLM_STRUCTURED=1` (json_schema
  từ Pydantic Literals — constrained decoding, provider không hỗ trợ thì tự fallback plain).
- Trung thực: không bịa, không che giấu hạn chế (`known_limitations`).

## 6. Eval

- 5 ca `tc1..tc5` (tiếng Việt, ≥3 speaker, timestamp tăng dần), so với `data/golden/`.
- Kết quả ghi vào `eval/report.md` (4 trường: Kỳ vọng → Kết quả → Đạt/Chưa đạt → Bài học).
- **tc5 dự kiến THẤT BẠI (Chưa đạt) là kết quả hợp lệ** — miễn là trung thực + có bài học.

## 7. Docs & ADR

- Mọi quyết định kiến trúc → `docs/adr/NNNN-*.md`, review qua PR như code.
- **Không sửa ADR cũ** — đổi ý thì tạo ADR mới, đánh dấu cũ `Superseded by NNNN`.
- Code lệch docs → sửa docs **trong cùng PR** (đừng để lệch quá 1 PR).
- Chỉ đọc docs theo nhu cầu (2-3 file/phase), không nhét hết vào context.

## 8. Git & dữ liệu nhạy cảm

- GitHub Flow: main luôn xanh, mọi thay đổi qua branch + PR, không push thẳng main.
- **KHÔNG bao giờ commit:** `.env`, transcript thật, `docs/private/`, `runs/`.
- Dữ liệu trong `data/` luôn synthetic (repo public).

## 9. Cấm treo terminal (bài học P3)

- **KHÔNG bao giờ bật server blocking** (`uvicorn --reload`, `npm run dev`, `ollama serve`)
  trong terminal của agent — chúng chạy mãi không tự dừng.
- Verify backend bằng `fastapi.testclient.TestClient` (pytest), frontend bằng `npm run build`.
- Demo tay có server = user tự bật trong terminal riêng; agent chỉ hướng dẫn lệnh.
- File log rác của server (`uvicorn.out`, `*.err`, `nohup.out`) không commit (đã ignore).