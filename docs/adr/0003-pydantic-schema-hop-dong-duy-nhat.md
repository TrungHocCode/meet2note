# ADR-0003 — Pydantic v2 làm hợp đồng schema duy nhất

- Status: Proposed
- Date: 2026-10-13

## Context

6 loại thông tin + evidence là hợp đồng chung của pipeline, API, React, eval.
Không có schema chặt thì LLM trả JSON lỗi format, UI và eval mỗi nơi hiểu một kiểu.

## Decision

Định nghĩa mọi model trong `backend/app/pipeline/schema.py` bằng Pydantic v2.
Schema này vừa validate output LLM (kèm retry ≤2 khi fail), vừa generate JSON schema đưa vào prompt,
vừa là kiểu trả về của API.

## Consequences

- (+) Một nguồn sự thật. (+) Lỗi LLM fail-validate crash rõ ràng thay vì im lặng.
- (−) Đổi field phải sửa schema + prompt + UI cùng lúc. Đây là ý muốn (fail nhanh, rõ).

## Alternatives considered

- JSON Schema viết tay / dataclass thường: loại vì mất validate runtime và không sinh được schema cho prompt.
