# ADR-0001 — Monorepo Python + React

- Status: Proposed
- Date: 2026-10-13

## Context

Hệ thống có 2 runtime (pipeline Python + review UI) nhưng team 1–2 dev, sprint 1–2 ngày.
Cần 1 repo duy nhất để demo end-to-end mà vẫn tách được lớp để lên production sau.

## Decision

Một repo `meet2note` chứa `backend/` (Python) + `frontend/` (React Vite) + `prompts/` + `data/` + `eval/`.
Chung `.env.example`, chung `PLAN_MVP.md`, chung version pipeline.

## Consequences

- (+) Clone 1 lần chạy được cả demo. (+) Không lệch version giữa pipeline và UI.
- (−) CI phải build 2 stack. Chấp nhận được ở quy mô này; khi team lớn mới tách repo.

## Alternatives considered

- 2 repo riêng: loại vì tốn công đồng bộ version ở MVP.
- Full TypeScript (pipeline bằng TS): loại vì xử lý text/JSON + sinh thái LLM của Python tốt hơn.
