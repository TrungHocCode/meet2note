# Eval report — meet2note (P4 nghiệm thu MVP + vòng Transcripts v2)

> Format: Kỳ vọng → Kết quả → Đạt/Chưa đạt → Bài học (`docs/spec/eval-plan.md` §3).
> Pipeline **0.4.0** (ingest → extract → resolve → verify). Model live: `qwen3:4b-instruct-2507-q4_K_M`
> qua Ollama local (`http://localhost:11434/v1`, chunk 40/overlap 10).
> Chạy: `python -m pipeline.cli eval` (fixture, deterministic) /
> `python -m pipeline.cli eval --live` (LLM thật). Kết quả máy: `eval/results_fixture.json` /
> `eval/results_live.json`.
>
> ## Vòng Transcripts v2 (mới nhất — transcripts dài 80–100 turns + khó hơn)
>
> Fixture **5/5 PASS**, live **5/5 PASS** (qwen3 local). Chi tiết từng ca dưới đây là kết quả
> **live** vòng v2. Lịch sử vòng P4 (transcripts v1) giữ trong git history.
>
> Điểm mới vòng v2 so với P4:
> - Transcripts dài gần gấp đôi + nhiễu thật (decoy, chốt giả, sarcasm, sửa deadline rồi hoàn,
>   overlapping, ngắt câu giữa chừng).
> - Pipeline cứng hơn nhờ live eval: demote final thiếu câu chốt thật, merge finals cùng nội dung,
>   evidence ts sửa về turn khớp thật, link ma → null, due override từ hint + past-date TBD,
>   gộp task trùng khác id, comparator best-match + owner/due-first + biến thể ngữ nghĩa.
> - tc5 live vòng này FLAG ĐÚNG reversal (không còn smoothing như vòng P4) — ca "dự kiến thất bại"
>   vẫn giữ nguyên kỳ vọng trung thực (fail là hợp lệ nếu model giấu mâu thuẫn).
> - Brief: tc1/tc3/tc4/tc5 có brief hợp lệ (refs sạch); tc2 brief None do prompt full transcript
>   (~6k tokens) tràn context 4096 của model local — pipeline vẫn chạy (brief là nice-to-have).

## tc1 — Sprint planning (ca LÀM TỐT, v2: +nhiễu)

- **Kỳ vọng:** D.final đúng (FastAPI+JWT, Lan), 3 task đủ owner+due, chốt giả ("chốt nghỉ trưa") bị loại.
- **Kết quả thực tế (live):** 9 items (0 đỏ + 2 vàng + 7 xanh), no_decision=False.
  D1.final "Chốt phương án B - FastAPI+JWT" by Lan, evidence SỬA về 00:04:14 turn 29
  (model gán nhầm 04:24 — verify sửa theo turn khớp thật + limitation). D0 (Nam note lại)
  bị hạ final→proposal (không có câu chốt thật). Câu đùa "chốt nghỉ trưa" không thành Decision.
  3 task golden khớp owner+due (Nam/16, Hà/19, Minh/21).
- **Đạt/Chưa đạt:** Decision ☑ Đạt · Task ☑ Đạt · Evidence ☑ Đạt.
- **Điều học được:** 2 luật mới đều phát huy: demote-note-lại + sửa evidence-ts theo turn khớp.
  Nhiễu không làm lệch kết quả cuối.

## tc2 — Đảo A→B (ca LÕI, kill-criterion acceptance #2)

- **Kỳ vọng:** D1.final=B, supersedes=[D0], decided_by=Lan, evidence câu chốt cuối; T1 Nam 12-10 link D1.
- **Kết quả thực tế (live):** 13 items (0 đỏ + 4 vàng + 9 xanh), no_decision=False.
  D1.final "vendor Y..." by Lan, supersedes=['D0'], evidence 00:52:10 (câu chốt thật;
  union còn giữ 52:34 — cả hai đều là câu decide thật). Decoy vendor Z bị loại đúng.
  QĐ phụ lịch demo PoC tồn tại riêng, không lẫn vào D1. T1 owner=Nam due=2026-10-12 link=D1.
- **Đạt/Chưa đạt:** Decision ☑ Đạt · Task ☑ Đạt · Evidence ☑ Đạt.
- **Điều học được:** decoy + đa quyết định không phá được arbitration đa số + timestamp muộn nhất.

## tc3 — Brainstorm vòng vo (ca KHÓ/MƠ HỒ, v2: +chốt giả)

- **Kỳ vọng:** no_decision=true, ≥1 Open Issue + next_step; câu "chốt luôn Stripe đi" (không
  dữ liệu, bị bác ngay, rút lại) KHÔNG được thành Decision.
- **Kết quả thực tế (live):** 12 items (1 đỏ + 4 vàng + 7 xanh), no_decision=True, 6 open issues.
  Chốt giả không thành Decision (đúng luật "nói ra ≠ chốt"). Task TBD giữ hint.
- **Đạt/Chưa đạt:** No-decision ☑ Đạt · Anti-false-chốt ☑ Đạt · Trung thực ☑ Đạt.
- **Điều học được:** bẫy chốt giả là bài test business-rule đắt giá nhất vòng này — hệ thống
  vượt qua vì đòi câu chốt + người chốt + đồng thuận, không nghe chữ "chốt" đơn lẻ.

## tc4 — Entity-linking (ca KHÓ/KỸ THUẬT, v2: +sửa deadline, +ngày không parse)

- **Kỳ vọng:** owner inferred đúng, due tương đối → ISO đúng (16/31/19/21-10).
- **Kết quả thực tế (live):** 13 items, 13/13 xanh, no_decision=False. D0.final VNPay by Lan,
  evidence 00:02:42. 4 task golden khớp owner+due+hint (T1_3/Hà/16, T1/Nam/31, T3_3/Hà/19,
  T4_2/Hà/21) — model tái dùng id T1..T8 mỗi chunk nên resolve phải tách id-collision
  (T1_3, T3_3...) rồi merge trùng. Deadline sửa-rồi-hoàn giữ đúng 16. `thứ 6 tuần sau nữa`
  không parse → TBD trung thực.
- **Đạt/Chưa đạt:** Decision ☑ Đạt · Entity-owner ☑ Đạt · Entity-due ☑ Đạt (4/4).
- **Điều học được:** id-collision (model tái dùng T1..Tn) là failure mode mới của model nhỏ —
  tách theo nội dung + rename có vết audit là cách xử đúng (không im lặng đè).

## tc5 — Đảo A→B→A (ca KHÓ NHẤT — vòng này HỆ THỐNG THẮNG)

- **Kỳ vọng:** Trung thực là trên hết — flag `unresolved_reversal` nếu phát hiện đảo chiều thật.
- **Kết quả thực tế (live v2):** 13 items (4 đỏ + 1 vàng + 8 xanh), flagged=2 finals, red=4.
  Transcript v2 hung hăng hơn (hùng biện 2 phe, chốt ngắt câu, sarcasm ×2) nhưng pass-1 giữ
  được mâu thuẫn → deterministic R4 flag đúng + Open Issue cho host.
- **Đạt/Chưa đạt:** ☑ Đạt (vòng này) — kèm lưu ý TRUNG THỰC: vòng P4 live model từng làm mượt
  mâu thuẫn (0 flag) trên transcript cũ ngắn hơn. R4 mạnh bằng pass-1 trung thực — variance
  theo input là bản chất của LLM nhỏ, lưới code không che được cũng không nên che.
- **Điều học được:** transcript càng dài + rhetoric càng mạnh, model càng giữ mâu thuẫn thay vì
  hòa giải — ngược với linh cảm ban đầu nhưng có lợi cho phát hiện. Ca "dự kiến thất bại" vẫn
  giữ nguyên trong eval-plan để bắt regression.

---

## Top fix vòng Transcripts v2 (từ live eval transcripts mới)

1. **Hạ final thiếu câu chốt thật** (`resolve.py`): evidence role=decide nhưng quote là tường thuật
   ("Em note lại: chốt...") → proposal. Luật business "nói≠chốt" thành code.
2. **Gộp finals cùng nội dung khác id** (`resolve.py`): model đặt D0/D1 cho cùng 1 chốt →
   gộp (winner = decide không-recap muộn nhất, union evidence/supersedes); khác nội dung giữ
   nguyên cho R4. Kèm sửa evidence-ts về turn khớp thật (`verify.py`).
3. **Tách id-collision task** (`resolve.py`): model tái dùng T1..Tn mỗi chunk cho task khác nhau →
   tách theo nội dung + rename có vết audit (thay vì trọng tài đè mất task thật).
4. **Toàn vẹn link** (`verify.py`): `link_to_decision` trỏ ID ma → null + limitation.
5. **Eval công bằng với paraphrase**: comparator best-match + owner/due-first, golden
   `content_any`/`evidence_ts_any`, `expected_red_min` thay vì đếm cứng.

## Đối chiếu acceptance (`docs/spec/acceptance.md`)

| # | Tiêu chí | Kết quả |
|---|---|---|
| 1 | Demo end-to-end <5 phút | ☑ Đạt (`cli run` + TestClient review/export + upload E2E; UI do user bật — `npm run build` xanh) |
| 2 | tc2 D.final=B + supersedes + D0 discarded + evidence câu chốt cuối (kill-criterion) | ☑ Đạt (live, evidence 52:10) |
| 3 | 5/5 bảng 4 trường, tc5 trung thực (đạt hay chưa đạt đều hợp lệ nếu trung thực) | ☑ Đạt (file này) |
| 4 | Audit 10 task: nguồn explicit/inferred hoặc TBD, không bịa | ☑ Đạt (10/10 OK vòng P4; lưới verify giữ nguyên vòng v2) |
| 5 | tc3 trung thực + TBD, chốt giả bị loại | ☑ Đạt (no_decision + chốt giả không thành Decision) |
| 6 | Gate: còn đỏ → 403; xong → 200 | ☑ Đạt (test_api + demo P3, giữ nguyên) |
| 7 | README cách chạy + known_limitations | ☑ Đạt (README root + § dưới) |

## Known limitations (trung thực, không che giấu)

- Model nhỏ paraphrase/đặt ID bừa/tính ngày sai — lưới deterministic đỡ được sai số có dấu vết,
  không đỡ được model giấu mâu thuẫn (variance live tc5 giữa 2 vòng).
- Brief cần full-transcript 1 call (~6k tokens) tràn context 4096 của model local (tc2 brief None) —
  pipeline vẫn chạy (brief nice-to-have).
- Chunk 40/overlap 10 do context 4k của model local (hosted dùng 80/10 mặc định).
- Task phụ dư ngoài golden (đúng nhưng thừa) — host tự loại ở review 2 phút.
- Chưa xử lý: speaker chồng lấn thật, sarcasm detection riêng, sync API Jira (out-of-scope MVP).

---

# Mission 3 — Từ MVP M2 lên M3 (chống false decision/task)

> Mục tiêu M3 (theo PLAN_M3.md, không commit): giảm false decision/task trên
> transcript dài + hedge + chốt giả. Thêm 4 thay đổi nhỏ (M3-A gate, M3-B hedge,
> M3-C evidence-chain, M3-D task↔knowledge) + 1 CR-giả định (due revision).
> Schema Pydantic KHÔNG đổi (chỉ dùng field có sẵn), R1–R8 giữ nguyên.

## BEFORE → AFTER trên tc6_long (~110 turns, 3 chủ đề)

tc6 là ca M3 mới: vendor (A→B→A? + chốt giả Stripe), deadline sửa 16→21,
quy ước dài hạn. Bằng chứng BEFORE/AFTER chạy cùng fixture, điểm khác biệt
duy nhất là 4 gate M3 (file `eval/run_tc6_before.py` patch no-op).

| Metric | BEFORE (M2) | AFTER (M3) | Cải thiện |
|---|---|---|---|
| `false_final` (final không khớp golden) | **1** (D3 Stripe chốt giả) | **0** (M3-A gate hạ proposal) | ✓ |
| `tasks` đúng loại | 6 (T1-T5 + K1 "quy ước" sai loại) | 5 (K1 reclassify → Knowledge) | ✓ |
| `knowledge` đúng loại | 1 (K2) | 2 (K1 + K2) | ✓ |
| T5 hedge "có lẽ tính sau" | owner=Nam due=2026-10-31 (sai) | owner=TBD due=TBD (đúng) | ✓ M3-B |
| T2 lead integration due | due=21-10 (M2 entity-link fix) | due=21-10 + hint `21/10 (revised turn 71)` (vết đầy đủ) | ✓ M3-CR |
| D3 Stripe status | `final` (sai) | `proposal` (đúng) | ✓ M3-A |

File `eval/results_tc6_before.json` (BEFORE) + `eval/results_tc6_after.json` (AFTER)
+ `eval/report.md` (BEFORE→AFTER khung theo PLAN_M3 §5).

## Kết quả test M3 (5 file mới, `tests/test_m3_*.py`)

| File test | Mục đích | Kết quả |
|---|---|---|
| `test_m3_decision_gate.py` | M3-A: chốt Stripe bị bác → final→proposal | 2/2 PASS |
| `test_m3_hedge.py` | M3-B: hedge content/quote → cấm final; hedge evidence → task TBD | 4/4 PASS |
| `test_m3_evidence_chain.py` | M3-C: single-evidence-final penalty (-0.20) + giữ item | 5/5 PASS |
| `test_m3_knowledge_task.py` | M3-D: Task "quy ước..." → Knowledge; gợi ý ngược qua limitation | 7/7 PASS |
| `test_m3_due_revision.py` | CR-DUE-REV: deadline sửa 16→19→21 → due=21 + vết cũ→mới | 5/5 PASS |

Tổng cộng 23/23 test M3 mới PASS. M2 regression: 214/214 PASS.

## Chấp nhận M3 theo PLAN_M3 §6.3

| # | Tiêu chí | Kết quả |
|---|---|---|
| 1 | Regression M2 xanh 100% (pytest + fixture eval 5/5) | ☑ Đạt (214/214 + 5/5 PASS) |
| 2 | 5 test M3 xanh | ☑ Đạt (23/23 PASS) |
| 3 | tc6_long: `false_final(M3) < false_final(M2)` + due_revision đúng + knowledge_precision tăng | ☑ Đạt (1→0, due 21-10 có vết, knowledge 1→2 đúng loại) |
| 4 | BEFORE→AFTER 6 dòng + file `runs/` hai phiên bản | ☑ Đạt (results_tc6_before.json + results_tc6_after.json; file runs/<tc6>/ không commit — gitignored) |
| 5 | Known limitations ghi trung thực (≥2 dòng) | ☑ Đạt (xem dưới) |

## Known limitations M3 (trung thực, không che giấu)

- CR-DUE-REV: chỉ xử lý 1 pattern (due_hint có ngày số + keyword "dời/sửa/chuyển").
  CR thật (multi-topic, owner-revision, export-filter) chưa được chỉ định — khi tới
  chỉ cần thay hàm `_apply_due_revision`, không đụng M3-A..D.
- M3-A retract check: chỉ quét ±5 turn sau decide cuối. Transcript chốt → nghỉ → 30
  phút sau rút lại (tc5) — gate không bắt được; R4 (reversal detection) vẫn loại.
- Hedge lexicon: danh sách cứng tiếng Việt (~12 marker). Tiếng lóng / sarcasm / double
  negative ("chốt đấy nhỉ") lọt qua — prompt LLM vẫn là lớp 1, code là lưới cuối.
- M3-C chain: heuristic len(chain_roles)==1 && len(evs)<=1 → đơn giản. Có final 1 evidence
  dài + đúng vẫn penalty -0.20; chấp nhận false negative để trung thực.
- Knowledge pattern: regex cố định. Câu dài paraphrase "Quan trọng là nhớ kỹ: ..."
  chứa "lưu ý" lẫn với task note → có thể reclassify nhầm; gợi ý chuyển ngược qua limitation.
- Evidence-chain R5 (regression): M3-C là NÂNG CẤP của R5 (penalty), không thay thế R5
  (verify vẫn check quote khớp + sửa ts theo turn khớp thật).
