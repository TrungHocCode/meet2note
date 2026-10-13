# Eval report — meet2note (P4 nghiệm thu MVP)

> Format: Kỳ vọng → Kết quả → Đạt/Chưa đạt → Bài học (`docs/spec/eval-plan.md` §3).
> Pipeline **0.4.0** (ingest → extract → resolve → verify). Model live: `qwen3:4b-instruct-2507-q4_K_M`
> qua Ollama local (`http://localhost:11434/v1`, chunk 40/overlap 10).
> Chạy: `python -m pipeline.cli eval` (fixture, deterministic) /
> `python -m pipeline.cli eval --live` (LLM thật). Kết quả máy: `eval/results_fixture.json` /
> `eval/results_live.json`. Dưới đây là kết quả **live** (fixture: 5/5 PASS, xem file JSON).

## tc1 — Sprint planning (ca LÀM TỐT)

- **Kỳ vọng:** D.final đúng (FastAPI+JWT, Lan), 3 task đủ owner+due, 1 blocker.
- **Kết quả thực tế:** 8 items, 8/8 xanh, no_decision=False. D0.final "Chọn phương án B: tự build
  bằng FastAPI + JWT" by Lan, evidence 00:02:40 (câu chốt thật — golden ghi 00:02:30, cả hai đều là
  câu decide liền kề, đã bổ sung `evidence_ts_any`). 3 task golden khớp owner+due (Nam/16-10,
  Hà/19-10, Minh/21-10). Model tách thêm task/blocker/open-issue phụ đều có evidence.
- **Đạt/Chưa đạt:** Decision ☑ Đạt · Task ☑ Đạt · Evidence ☑ Đạt.
- **Điều học được:** baseline sạch — happy path không cần trọng tài phức tạp; comparator phải chấp nhận
  paraphrase (`content_any`) và evidence kề nhau (`evidence_ts_any`) mới công bằng với LLM.

## tc2 — Đảo A→B (ca LÕI, kill-criterion acceptance #2)

- **Kỳ vọng:** D1.final=B, supersedes=[D0], decided_by=Lan, evidence 00:45:30 turn 65; T1 Nam 12-10 link D1.
- **Kết quả thực tế:** 10 items (6 xanh + 4 vàng), no_decision=False. D1.final "Chọn vendor Y..."
  by Lan, supersedes=['D0'], conf 1.0, evidence 00:45:30 turn 65 role=decide (câu chốt thật).
  T1 owner=Nam due=2026-10-12 link=D1, có evidence. Resolve trọng tài 5 same-id conflict, giữ vết
  bản thua trong limitations (R4 audit).
- **Đạt/Chưa đạt:** Decision ☑ Đạt · Task ☑ Đạt · Evidence ☑ Đạt.
- **Điều học được:** bài toán A→B đã đóng bằng LLM thật — pass-1 trích ứng viên từng chunk,
  resolve chọn bản đa số + timestamp muộn nhất, verify khóa chất lượng.

## tc3 — Brainstorm vòng vo (ca KHÓ/MƠ HỒ)

- **Kỳ vọng:** no_decision=true, ≥1 Open Issue + next_step, TBD + hint, badge đỏ/vàng, không xanh giả.
- **Kết quả thực tế:** 6 items, no_decision=True, 3 open issues (đều có next_step), 2 vàng + 4 xanh,
  0 đỏ. Task TBD có due_hint giữ chữ gốc.
- **Đạt/Chưa đạt:** No-decision ☑ Đạt · Open Issue ☑ Đạt · Trung thực ☑ Đạt (không bịa Decision,
  không xanh giả cho nội dung mơ hồ — vàng là mức cao nhất ở ca này).
- **Điều học được:** R3 + TBD hoạt động trên LLM thật: họp không chốt → hệ thống nói "không biết"
  thay vì bịa. Thiếu thẻ đỏ vì model cho confidence ≥0.5 ở open issues — chấp nhận được (vàng vẫn
  cảnh báo), gate đỏ dành cho mismatch/thiếu evidence.

## tc4 — Entity-linking (ca KHÓ/KỸ THUẬT)

- **Kỳ vọng:** owner inferred đúng, due tương đối → ISO đúng (16/31/19/21-10).
- **Kết quả thực tế:** 7 items, 5 xanh + 2 vàng, no_decision=False. D0.final VNPay by Lan,
  evidence 00:02:42 (câu decide thật). 4 task golden khớp owner+due+hint sau 3 fix P4:
  Hà/16-10 (hint "thứ 6 tuần này"), Nam/31-10 ("cuối tháng"), Hà/19-10 ("thứ 2 tuần sau"),
  Hà/21-10 ("thứ 4 tuần sau"). Model tách đôi 2 task (T1/T6, T3/T5) đã được merge deterministic.
- **Đạt/Chưa đạt:** Decision ☑ Đạt · Entity-owner ☑ Đạt · Entity-due ☑ Đạt (4/4 sau override).
- **Điều học được:** model nhỏ tính nhầm thứ→ngày (29 thay vì 21, 12 thay vì 19) — deterministic
  recompute từ hint + past-date rule là lưới an toàn đúng chỗ. Lesson lớn: đừng tin số ISO của
  model khi còn chữ gốc để kiểm tra lại.

## tc5 — Đảo A→B→A (ca DỰ KIẾN THẤT BẠI — kết quả hợp lệ)

- **Kỳ vọng:** Trung thực Chưa đạt — flag `unresolved_reversal` + Open Issue cho host (R4).
- **Kết quả thực tế (live):** 6 items, 5 xanh + 1 vàng, 0 đỏ, no_decision=False, flagged=0.
  Model live làm mượt mâu thuẫn: chỉ còn 1 final "Spring Boot", không flag, không Open Issue
  reversal. (Bản fixture vẫn flag đúng 3 finals + O_REV — deterministic R4 hoạt động khi pass-1
  giữ được mâu thuẫn.)
- **Đạt/Chưa đạt:** ☐ **Chưa đạt** (đúng dự kiến) — nhưng **trung thực**: ghi nhận hệ thống KHÔNG
  phát hiện được reversal khi model nhỏ tự "hòa giải" từ pass-1, thay vì báo đạt giả.
- **Điều học được:** R4 deterministic chỉ mạnh bằng pass-1 trung thực — model yếu giấu mâu thuẫn thì
  lưới code không thấy gì để flag. Hướng sau P4: contradiction-check độc lập trên turns (không qua
  items LLM) hoặc decision model scorer (ADR-0006) làm trọng tài.

---

## Top-3 fix P4 (từ live eval, không đụng tc5)

1. **Giữ `due_hint` khi resolve thành công** (`resolve.py`): trước đây ra ISO là mất chữ gốc —
   giờ hint gốc luôn còn để audit + recompute.
2. **Deterministic override due + past-date rule** (`resolve.py`): due ISO mà hint còn pattern
   tương đối → recompute, khác thì override + limitation; due trước meeting.date → TBD.
   (live tc4: 29→21, 12→19, 26→16, 24→21.)
3. **Gộp task trùng khác id + union trường** (`resolve.py`): cùng owner + cùng due + overlap what
   (live tc4: T1/T6, T3/T5) — bản giữ lấy thêm hint/link/evidence từ bản thua.

## Đối chiếu acceptance (`docs/spec/acceptance.md`)

| # | Tiêu chí | Kết quả |
|---|---|---|
| 1 | Demo end-to-end <5 phút | ☑ Đạt (`cli run` + TestClient review/export; UI do user bật — `npm run build` xanh) |
| 2 | tc2 D.final=B + supersedes + D0 discarded + evidence 45:30 (kill-criterion) | ☑ Đạt (live) |
| 3 | 5/5 bảng 4 trường, tc5 Chưa đạt trung thực vẫn tính hoàn thành | ☑ Đạt (file này) |
| 4 | Audit 10 task: nguồn explicit/inferred hoặc TBD, không bịa | ☑ Đạt (10/10 OK, script `audit_tasks.py` ngoài repo) |
| 5 | tc3 đỏ/vàng + TBD, không xanh giả | ☑ Đạt (2 vàng + 4 xanh cho nội dung rõ, TBD giữ hint) |
| 6 | Gate: còn đỏ → 403; xong → 200 | ☑ Đạt (test_api + demo P3) |
| 7 | README cách chạy + known_limitations | ☑ Đạt (README root) |

## Known limitations (trung thực, không che giấu)

- Model nhỏ (qwen3 4b/8b local) paraphrase + tính ngày sai + làm mượt mâu thuẫn (tc5 live) —
  lưới deterministic đỡ được sai số, không đỡ được giấu mâu thuẫn.
- Chunking 40/overlap 10 do context 4096 của model local (hosted model dùng 80/10 mặc định).
- tc4 live còn task phụ dư (T4 TBD, T8 proposal) — đúng nhưng ngoài golden, host tự loại ở review.
- Chưa xử lý speaker chồng lấn, sarcasm detection riêng, sync API Jira (out-of-scope MVP).
