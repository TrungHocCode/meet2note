# ADR-0005 - Pipeline ở root, API là adapter mỏng

- Status: Accepted
- Date: 2026-10-13
- Supersedes: ADR-0002

## Context

ADR-0002 đặt pipeline trong `backend/app/pipeline/`. Đánh giá lại theo cây thư mục 2.3 của plan:
pipeline là sản phẩm lõi (transcript → structured state), cần chạy độc lập (CLI + eval 5 ca)
và dễ tách thành repo riêng khi team lớn. Đặt pipeline dưới `backend/` khiến nó phụ thuộc layout
của backend — trái với chính tinh thần của ADR-0002 ("API chỉ là lớp mỏng").

## Decision

- Giữ cây PLAN_MVP 2.3: `pipeline/` ở **root repo**:
  `pipeline/{schema, ingest, extract, resolve, verify, export, store, cli}.py`
- `backend/` chỉ là adapter mỏng: `backend/api.py` (GET/PUT state, POST export có gate R6).
- Cách chạy:
  - Pipeline CLI: `python -m pipeline.cli run --meeting tc2`
  - API: `python -m uvicorn backend.api:app --reload`
  - Test: `pytest tests -q`
- `tests/` ở root; eval là lệnh `cli eval` ghi `eval/report.md`.

## Consequences

- (+) Pipeline độc lập — eval và demo không cần server; dễ tách repo sau.
- (+) Khớp cây 2.3 của plan, không rẽ hai hướng.
- (-) `backend/api.py` phải import `pipeline.*` từ root — chạy bằng `python -m` để đảm bảo import path;
  chấp nhận ở quy mô MVP.

## Alternatives considered

- Giữ ADR-0002 (`backend/app/pipeline/`): loại vì pipeline gắn cứng vào backend,
  khó tách repo và lệch với plan 2.3 đã đánh giá tốt.