# ADR-0002 — Pipeline tách khỏi API (pipeline chạy CLI độc lập)

- Status: Superseded by 0005
- Date: 2026-10-13

## Context

Có 2 luồng dùng lõi: (a) eval 5 kịch bản bằng CLI, (b) demo review qua React + API.
Nếu lõi dính vào code serve thì mỗi lần sửa prompt/schema phải đụng server.

## Decision

Lõi nằm ở `backend/app/pipeline/` (ingest, schema, extract, resolve, verify, export, store, cli),
chạy độc lập: `python -m backend.app.pipeline.cli run --meeting tc2`.
`backend/app/api/` chỉ là lớp mỏng (GET/PUT state, POST export có check gate R6).

## Consequences

- (+) Test tc2 đúng A→B và eval 5 ca không cần dựng server. (+) API thay được mà không sửa lõi.
- (−) Thêm 1 lớp chuyển đổi mỏng giữa pipeline model và API response. Giữ nguyên Pydantic model dùng chung để chi phí này ~0.

## Alternatives considered

- Gộp lõi vào router FastAPI: loại vì eval và debug prompt trở nên nặng nề, mất khả năng chạy offline từng bước.
