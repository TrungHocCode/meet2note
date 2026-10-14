# ADR-0009 — Postgres local + JWT cho P6 (metadata DB, file ở disk)

- Status: Accepted
- Date: 2026-10-14

## Context

P5 xong: pipeline + review + export chạy tốt nhưng mọi thứ nằm file rời rạc
(`runs/`, `data/uploads/`) — không xem lại lịch sử, không phân biệt user,
không tải file có kiểm soát. Cần DB + auth mà không đập kiến trúc hiện có.

## Decision

- **Postgres 16 qua docker-compose** (volume `pgdata`, port host **5434** vì 5432
  là Postgres native của máy dev và 5433 là project khác — không đụng vào cái nào).
- **5 bảng, chỉ metadata** (`users`, `meetings`, `runs`, `exports`, `refresh_tokens`).
  Items chi tiết ở yên trong `state.json` (single source of truth — duplicate vào
  DB là mời lệch dữ liệu).
- **SQLAlchemy 2.0 + Alembic** từ migration đầu (`0001_initial`); JSONB với
  fallback JSON cho SQLite (test).
- **Argon2 qua pwdlib** (tránh bẫy passlib/bcrypt 4.x).
- **JWT (pyjwt) + multi-user ở P6b**; P6a chỉ seed admin + gắn owner (không HTTP auth).
- **Sync/backfill** (`sync-db`, idempotent theo `(meeting_id, ts)`) thay vì migrate
  dữ liệu tay — chạy lại bao nhiêu lần cũng không duplicate.
- Chưa làm (ghi rõ để khỏi scope-creep): SSO, RBAC roles, S3/cloud files,
  backup/restore tự động, read-replica.

## Consequences

- (+) Xem lại lịch sử + phân quyền owner + download có kiểm soát ở P6b/P6c.
- (+) Lên cloud sau chỉ đổi `DATABASE_URL` + layer đọc file (schema lưu path tương đối).
- (−) Dev phải chạy docker + migrate + seed (ghi vào runbook, 3 lệnh).
- (−) Thêm ~7 dependency (`sqlalchemy`, `alembic`, `psycopg`, `pwdlib`, `pyjwt`...).

## Alternatives considered

- SQLite file: loại vì đã chốt Postgres ở plan P6 (multi-user + concurrent write),
  và JSONB query sau này.
- Bảng `items`/`decisions` trong DB: loại vì duplicate `state.json` (ADR-0003:
  schema Pydantic là hợp đồng duy nhất).
- Supabase/Neon hosted: loại ở phase này — local docker đủ, không phụ thuộc mạng/tài khoản.
