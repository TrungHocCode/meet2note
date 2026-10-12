# C4 L3 — Component: chi tiết pipeline (lõi MVP)

6 bước, input/output file rõ ràng. Bước (4) VERIFY thuần Python — mọi lời LLM đều bị code kiểm tra lại.

```mermaid
sequenceDiagram
    participant CLI as pipeline CLI
    participant P1 as extract<br/>(LLM pass-1)
    participant P2 as resolve<br/>(LLM pass-2 + rules)
    participant V as verify<br/>(Python, không LLM)
    participant FS as runs/ versioned
    CLI->>P1: turns.json (chunk ~80 lượt, overlap 10)
    P1-->>CLI: raw_items.json (6 loại + evidence thô + conf_llm)
    CLI->>P2: raw_items toàn meeting
    P2-->>CLI: resolved.json (supersedes A→B, merge trùng, entity-link, flag mâu thuẫn)
    CLI->>V: resolved.json
    V-->>CLI: meeting_state.json (confidence cuối, TBD, evidence_verified, known_limitations)
    CLI->>FS: state + review_log + llm_log.jsonl
```

| Bước | Module | LLM? | Việc chính |
|---|---|---|---|
| (1) INGEST | `ingest.py` | Không | Parse txt/srt → `turns.json` [{turn, t_start, t_end, speaker, text}] |
| (2) EXTRACT | `extract.py` | Có (pass-1) | Trích 6 loại + evidence + conf_llm, temp 0, JSON mode, retry ≤2 |
| (3) RESOLVE | `resolve.py` | Có (pass-2) + rules Python | Nối supersedes xuyên chunk, merge trùng, entity-link tên/ngày, flag `unresolved_reversal` |
| (4) VERIFY | `verify.py` | Không | Quote fuzzy ≥85%, công thức confidence, ép TBD (R1/R2/R5) |
| (5) REVIEW | React + API | Người | Đồng ý/Sửa/Loại, gate R6, ghi review_log |
| (6) EXPORT | `export.py` | Không | `minutes.md` + `tasks_jira.csv`, chỉ chạy sau confirm |

Tách pass-2 vì đề xuất A (đầu họp) và chốt B (cuối họp) nằm khác chunk — pass-1 không thấy toàn cảnh.
Chi tiết schema + quy tắc: `spec/taxonomy.md`.
