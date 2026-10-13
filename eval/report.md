# Eval report — meet2note (P2 milestone)

> Format: Kỳ vọng → Kết quả → Đạt/Chưa đạt → Bài học (theo `spec/eval-plan.md` §3).
> Phiên bản pipeline: **0.3.0** (P2: ingest → extract → resolve → verify).
> Cách chạy: `python -m pipeline.cli run --meeting tcN --llm-fixture data/fixtures/tcN_llm.json`
>            (Ollama local ở `localhost:11434` không chạy → buộc dùng fixture mock —
>            xem phần "Trung thực" dưới.)

## Trung thực (AGENTS.md §5)

- **Ollama local DOWN tại thời điểm P2:** `curl localhost:11434/v1/models` → connect refused.
- `.env` cấu hình `qwen3:4b-instruct-2507-q4_K_M` vẫn hợp lệ về key/endpoint, nhưng
  daemon Ollama không chạy → không thể live LLM pass-1 + pass-2.
- **Hệ quả:** live run dùng `data/fixtures/*.json` (mock LLM — đã được dùng để
  smoke-test P1 và vẫn giữ nguyên cách dùng trong P2). Fixture cover đủ 5 ca tc1..tc5.
- **Khuyến nghị:** user khởi động `ollama serve` + `ollama pull qwen3:4b-instruct-2507-q4_K_M`
  rồi chạy lại `cli run --meeting tcN` để có live test thật.

---

## tc1 — Sprint 14 planning (happy path)

- **Kỳ vọng:** D.final dùng FastAPI+JWT supersedes=[], evidence 00:02:30; 3 task đủ owner+due; 1 blocker.
- **Kết quả:** 7 items (1 decision + 5 task + 1 blocker). 7/7 green.
  - D1 final decided_by=Lan, evidence 00:02:30 turn 20 (substring match — câu chốt).
  - 5 task: research pricing (Nam/16/10), setup dev (Hà/19/10), test plan (Minh/21/10),
    vendor AM (Hà/21/10), slide rehearsal (Minh/28/10).
  - 1 blocker: vendor API key (Hà, severity high).
- **Đạt:** Decision ☐ Đạt · Task ☐ Đạt · Evidence ☐ Đạt.
- **Bài học:** tc1 happy path — không có gì đặc biệt, là baseline.

## tc2 — Đảo A→B sạch (gate P1 còn thiếu P2 fix)

- **Kỳ vọng:** D1.final=B supersedes=[D0], evidence 00:45:30 turn 65, reason chi phí 30%;
  T1 Nam 2026-10-12 link D1.
- **Kết quả (live multi-chunk fixture — chứng minh fix case P1 để lại):**
  - chunk_size=40, overlap=5 → 3 chunks. LLM pass-1 trích D1 sai @05:46 ở chunk 0
    (đoán sớm — case P1 bug). Chunk 1 trích D1 đúng @45:30 turn 65.
  - **resolve pick winner @45:30** (majority 1:1 + tie-break latest-decide cùng ts;
    bản @05:46 chunk 0 ghi `known_limitations` audit).
  - D1 final: decided_by=Lan, confidence=1.0, supersedes=['D0'], unresolved_reversal=False,
    **evidence[0].timestamp = "00:45:30"** turn=65 role=decide.
  - D0 discarded, evidence 00:08:04 turn 39 role=propose.
  - T1 Nam gửi báo giá B due 2026-10-12 link D1; T2 Hà sandbox TBD (due_hint='sau khi ký hợp đồng').
  - 4 items: 3 green + 1 yellow (T2 do TBD).
- **Đạt:** Decision ☑ Đạt · Task ☑ Đạt · Evidence ☑ Đạt (D1.evidence=09:45:30 turn 65).
- **Bài học:** cross-chunk arbitration đã fix P1. Bản thua giữ trace qua `known_limitations`
  (audit, không xoá — R4 triết lý "không xoá tranh luận").

## tc3 — Brainstorm vòng vo (no_decision)

- **Kỳ vọng:** no_decision=true, ≥1 Open Issue + next_step, TBD + hint, badge đỏ/vàng.
- **Kết quả:** 2 items (1 open_issue + 1 task TBD), 2/2 đỏ.
  - O1: "Chưa chốt hướng tích hợp thanh toán" next_step="Hẹn họp lại sau khi có thêm dữ liệu".
  - T1: "Triển khai research thanh toán" owner=TBD due=TBD due_hint='sớm nhé'.
  - no_decision=True (LLM không tạo Decision, có Open Issue có next_step).
- **Đạt:** Decision N/A (no_decision) · Open Issue ☑ Đạt · Task TBD+hint ☑ Đạt · Badge đỏ ☑ Đạt.
- **Bài học:** pipeline CHÁNH từ tối: họp không chốt gì → không gắn false `no_decision=False`,
  flag đỏ + TBD + hint. Host biết ngay cần xử lý tiếp.

## tc4 — Entity-link (em, anh, chị, tuần sau, cuối tháng)

- **Kỳ vọng:** owner inferred đúng (em/anh/chị + tên), due tương đối → ISO đúng.
- **Kết quả:** 5 items (1 decision + 4 task), 1 green + 4 yellow.
  - D1 final VNPay, evidence 00:02:42+00:03:06 (2 decide → heuristic R1 ≥3 mới flag → KHÔNG
    flag reversal — đúng).
  - T1: owner=Hà (em Hà → Hà), due=2026-10-16 (thứ 6 tuần này từ 2026-10-15).
  - T2: owner=Nam, due=2026-10-31 (cuối tháng từ 2026-10-15).
  - T3: owner=Hà, due=2026-10-21 (thứ 4 tuần sau từ 2026-10-15).
  - T4: owner=Hà, due=2026-10-19 (thứ 2 tuần sau từ 2026-10-15).
- **Đạt:** Decision ☑ · Entity-link owners ☑ · Entity-link due ISO ☑ (4/4 đúng ISO).
- **Bài học:** `parse_relative_date` deterministic — 1 test pass 8 case
  (`thứ 2..CN`, `tuần sau`, `ngày N/M`, `cuối tháng`, `sau N ngày`). Filler
  "nhé" / "sớm" giữ nguyên trong `due_hint`.

## tc5 — Đảo A→B→A thật (DỰ KIẾN THẤT BẠI — kết quả hợp lệ)

- **Kỳ vọng:** Trung thực Chưa đạt — flag `unresolved_reversal` + Open Issue cho host.
- **Kết quả:** 4 items (3 decision flagged reversal + 1 Open Issue O_REV_1), 3/3 đỏ.
  - D_SB, D_FA, D_REV (3 final mâu thuẫn Spring Boot ↔ FastAPI) — tất cả `unresolved_reversal=true`.
  - O_REV_1 (system_generated, no evidence — audit marker): "Phát hiện mâu thuẫn..." next_step="Host mở transcript gốc..."
  - 3 đỏ (R4 contradiction + R4 reversal penalty -0.20 cộng dồn).
- **Đạt:** ☐ **Chưa đạt** (đúng kỳ vọng — chưa quyết được, host xử lý) nhưng **trung thực**:
  - unresolved_reversal=True trên cả 3 Decision final.
  - O_REV_1 tạo cho host, system_generated=True.
  - badge đỏ khoá export (R6 gate).
- **Bài học:** pipeline tuân thủ R4 — KHÔNG tự chọn 1 bên giữa 3 final mâu thuẫn.
  Cần module chồng lấn speaker (sarcasm "tuyệt vời lắm" hiện vẫn qua heuristic OK,
  P3 sẽ detect sarcasm) và pass-3 arbitration (nếu vẫn tay host quá nhiều).

---

## Tóm tắt P2 gate

| Gate P2 | Mô tả | Trạng thái |
|---|---|---|
| §1 resolve.py | Merge + supersedes + reversal + entity-link | ☑ Đạt (25/25 test_resolve pass) |
| §2 backend/api.py | GET/PUT review + POST export gate R6 | ☑ Đạt (13/13 test_api pass) |
| §3 fixtures tc3+tc4+tc5 | Synthetic Việt, ≥3 speakers, timestamp ↑ | ✅ |
| §4 tests | test_resolve + test_api + test_ingest + test_verify + test_schema + test_extract | ☑ **158/158 pass** |
| §5 live tc2 | D1.evidence @45:30 turn 65 (gate P1 còn thiếu) | ☑ **ĐẠT** (multi-chunk fixture demo) |
| §5'. open issues | Ollama local DOWN → báo user | ⚠ Đã ghi trong "Trung thực" |

**Gate P2: ĐẠT** (158/158 tests + live tc2 evidence @45:30 + API smoke OK).