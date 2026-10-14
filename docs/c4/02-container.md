# C4 L2 — Container: các khối chạy được

| Container | Công nghệ | Trách nhiệm |
|---|---|---|
| `frontend` — review app | React (Vite), 1 trang | 4 cột + brief + badge, sửa owner/due, gate thẻ đỏ, nút Export, drawer transcript (±4 turns), form upload |
| `backend` — API mini | FastAPI | review (GET/PUT), export (POST + gate R6), transcript viewer (GET), upload + chạy pipeline qua `service` (POST) |
| `pipeline` — lõi | Python + Pydantic v2 | ingest→extract→resolve→verify→export; `service.run_pipeline` dùng chung cho CLI + API; `cli` chỉ còn args + in tiến trình |
| `runs/` — filesystem | JSON files | `runs/<meeting_id>/<ts>/`: state, confirmed, review_log, llm_log (versioned, thay DB ở MVP) |
| `data/` — fixtures | `.txt/.srt/.docx` + JSON | transcripts tc1–tc5, meta, golden để eval; `uploads/` (gitignored) cho file người dùng |
| `db` — Postgres (P6a) | Postgres 16 (docker, port host **5434**) | 5 bảng metadata (`users/meetings/runs/exports/refresh_tokens`); file ở yên trên disk |

```mermaid
flowchart TB
    React[frontend — React review app<br/>review + drawer + upload]
    API[backend — FastAPI mini<br/>review + export + upload + auth (P6b)]
    Svc[pipeline.service<br/>run_pipeline dùng chung]
    Pipe[pipeline — modules<br/>ingest→extract→resolve→verify→export]
    FS[(runs/ — JSON versioned)]
    Data[(data/ — transcripts/meta/golden)]
    Up[(data/uploads — gitignored)]
    DB[(Postgres — metadata)]
    LLM[(LLM API)]
    React -->|REST| API
    API --> Svc
    API --> DB
    Svc --> Pipe
    Pipe --> FS
    Pipe --> Data
    API --> Up
    Pipe <--> LLM
```

MVP chạy được pipeline CLI mà không cần frontend/backend (xem `runbook/local-dev.md`).
