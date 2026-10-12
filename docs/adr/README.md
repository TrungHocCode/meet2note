# ADR — Architecture Decision Records

Mỗi quyết định 1 file, đặt tên `NNNN-ten-kebab-case.md`. Đổi ý thì KHÔNG sửa file cũ —
tạo ADR mới và đánh status file cũ thành `Superseded by NNNN`.

## Quy ước status

`Proposed | Accepted | Deprecated | Superseded by NNNN`

## Index

| ADR | Tiêu đề | Status |
|---|---|---|
| 0001 | Monorepo Python + React | Proposed |
| 0002 | Pipeline tách khỏi API | Superseded by 0005 |
| 0003 | Pydantic v2 làm hợp đồng schema duy nhất | Proposed |
| 0004 | Filesystem versioned thay DB ở MVP | Proposed |
| 0005 | Pipeline ở root, API là adapter mỏng | Accepted |

## Mẫu file ADR

```markdown
# ADR-NNNN — Tiêu đề
- Status: Proposed
- Date: YYYY-MM-DD
## Context
## Decision
## Consequences
## Alternatives considered
```
