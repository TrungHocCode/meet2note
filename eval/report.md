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
