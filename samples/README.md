# Samples — transcripts mẫu để upload test trên UI

> 3 file tăng dần độ khó. Upload ở sidebar → form "Upload transcript".
> File mẫu là **synthetic**, commit được (khác `data/uploads/` là chỗ chứa file BẠN upload).

## 1. `sample_standup.txt` — DỄ (standup 15 phút, ~30 turns)

- Meeting id gợi ý: `demo_standup`
- Title: `Standup ngày`
- Date: hôm nay (YYYY-MM-DD)
- Participants (mỗi dòng `Tên (role)`):
  ```
  Lan (PM)
  Nam (Dev)
  Hà (Dev)
  Minh (QA)
  ```
- Kỳ vọng: 1 quyết định nhỏ (seed script chung, Hà, thứ Năm) + 2–3 task rõ owner.
  Hệ thống phải đạt gần như tuyệt đối ở ca này.

## 2. `sample_dam_phan.txt` — TRUNG BÌNH (đàm phán license, ~50 turns)

- Meeting id gợi ý: `demo_dam_phan`
- Title: `Đàm phán license DataFlow`
- Date: hôm nay
- Participants:
  ```
  Lan (PM)
  Nam (BA)
  Hà (Dev)
  ```
- Kỳ vọng: chốt trial 1 tháng + lock giá 85 triệu (trần 85/sàn 80 là điều kiện, không phải
  quyết định độc lập); task Nam liên hệ sales + Hà review SLA. Có 1 ý tưởng bị bác
  (tự build) — không được thành Decision.

## 3. `sample_brainstorm_roi.txt` — KHÓ (brainstorm rối, ~60 turns)

- Meeting id gợi ý: `demo_brainstorm`
- Title: `Bàn redesign landing page`
- Date: hôm nay
- Participants:
  ```
  Lan (PM)
  Nam (BA)
  Hà (Dev)
  ```
- Kỳ vọng: `no_decision=true` — KHÔNG có quyết định design nào được chốt. Bẫy:
  câu "vậy mình chốt—" bị ngắt giữa chừng + sarcasm "tuyệt vời" → không được thành Decision.
  2 task tìm hiểu (Nam hỏi giá, Hà tổng hợp ý tưởng) owner rõ nhưng due mơ hồ ("sớm nhé")
  → phải TBD + giữ hint. Nếu hệ thống bịa ra Decision ở ca này là FAIL — báo lại để fix.
