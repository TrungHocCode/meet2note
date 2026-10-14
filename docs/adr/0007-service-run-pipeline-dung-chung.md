# ADR-0007 — service.run_pipeline dùng chung cho CLI và API

- Status: Accepted
- Date: 2026-10-14

## Context

`cli.cmd_run` chứa toàn bộ orchestration ingest→extract→resolve→verify→save (~150 dòng).
API upload (P5) cần chạy đúng pipeline đó — copy code sang `backend/api.py` sẽ tạo 2 nguồn
sự thật (sửa 1 nơi quên 1 nơi), vi phạm ADR-0005 ("API chỉ là adapter mỏng").

## Decision

- Tách `pipeline/service.py::run_pipeline()` nhận meta/transcript/runs_dir/fns/brief,
  trả `{state, out_dir, turns_count, extraction, resolution}`.
- `cli.cmd_run` chỉ còn: parse args + fixture wiring + gọi service + in tiến trình.
- `backend/api.py` (upload) gọi service trực tiếp; brief do caller tự trích trước.

## Consequences

- (+) 1 đường pipeline duy nhất — CLI và UI cho cùng kết quả trên cùng input.
- (+) Test service 1 lần, cả 2 mặt cùng hưởng.
- (−) Signature service phình khi pipeline thêm bước (brief_raw đã là ví dụ).
  Chấp nhận ở quy mô này; khi >8 params thì gom thành config object.

## Alternatives considered

- Duplicate orchestration trong api.py: loại vì 2 nguồn sự thật.
- API gọi CLI qua subprocess: loại vì chậm, khó truyền lỗi có cấu trúc (400/422/503),
  khó test bằng TestClient.
