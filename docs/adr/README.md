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
| 0006 | Decision model làm arbitration scorer sau MVP (chưa chọn model) | Proposed |
| 0007 | service.run_pipeline dùng chung cho CLI và API | Accepted |
| 0008 | Tailwind CSS v4 + shadcn/ui cho frontend review (kèm design tokens) | Accepted |
| 0009 | Postgres local + JWT cho P6 (metadata DB, file ở disk) | Accepted |

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
