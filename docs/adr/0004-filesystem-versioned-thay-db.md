# ADR-0004 — Filesystem versioned thay DB ở MVP

- Status: Proposed
- Date: 2026-10-13

## Context

MVP cần lưu vết versioned (state → confirmed + review log + llm log) để audit và debug prompt,
nhưng dựng DB cho 5 transcripts test là quá nặng trong 1–2 ngày.

## Decision

Lưu file: `runs/<meeting_id>/<ts>/` chứa `state.json`, `confirmed.json`, `review_log.json`, `llm_log.jsonl`.
`runs/` gitignored. `backend/app/models/` + `db/` giữ chỗ trống cho SQLAlchemy khi lên production.

## Consequences

- (+) Không cần DB mà vẫn versioned + audit được ai sửa gì. (+) Debug prompt bằng cách diff 2 run.
- (−) Không query xuyên meeting, không concurrent write. Chấp nhận ở MVP (5 meeting test, 1 user demo).
- Lên production: thay `store.py` bằng repository qua DB, giữ nguyên interface đọc/ghi versioned.

## Alternatives considered

- SQLite ngay từ đầu: loại vì thêm migration/ORM mà chưa có query nào cần tới ở MVP.
