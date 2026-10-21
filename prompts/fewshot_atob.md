# Few-shot — ví dụ chuẩn: đảo ý kiến A→B

Đưa vào prompt extract như ví dụ minh hoạ (1 cặp input → output đúng).

## Transcript mẫu

```
[00:10:12] Nam: Em đề xuất phương án A, bên X rẻ hơn 20%.
[00:45:30] Lan: A rủi ro vượt 30% nếu phát sinh. Vậy chốt B nhé, cả team đồng ý không? (không ai phản đối)
[00:46:05] Nam: Dạ em gửi báo giá B cho khách trước 12/10.
```

## Kết quả đúng

```json
{
  "items": [
    {
      "id": "D0", "type": "decision", "content": "Đề xuất phương án A",
      "status": "discarded",
      "evidence": [{"quote": "Em đề xuất phương án A, bên X rẻ hơn 20%.", "timestamp": "00:10:12", "speaker": "Nam", "turn": 1, "role_in_discussion": "propose"}]
    },
    {
      "id": "D1", "type": "decision", "content": "Chốt phương án B",
      "status": "final", "decided_by": "Lan",
      "reason": "A rủi ro vượt 30%", "supersedes": ["D0"],
      "evidence": [{"quote": "Vậy chốt B nhé, cả team đồng ý không?", "timestamp": "00:45:30", "speaker": "Lan", "turn": 2, "role_in_discussion": "decide"}]
    },
    {
      "id": "T1", "type": "task", "what": "Gửi báo giá B cho khách",
      "owner": "Nam", "owner_source": "explicit",
      "due": "2026-10-12", "due_source": "explicit", "due_hint": null,
      "link_to_decision": "D1",
      "evidence": [{"quote": "Dạ em gửi báo giá B cho khách trước 12/10.", "timestamp": "00:46:05", "speaker": "Nam", "turn": 3, "role_in_discussion": "confirm"}]
    }
  ]
}
```

## LƯU Ý

- A (D0) **KHÔNG** được liệt kê như quyết định cuối — chỉ D1 là `final`.
- Evidence của final là câu **chốt cuối** (00:45:30), không phải câu đề xuất đầu.
- `supersedes: ["D0"]` giữ vết A→B để audit (R4).

## Ví dụ phủ định — CHỐT GIẢ bị bác (M3-A case)

> Triết lý: "chốt" đơn lẻ ≠ chốt thật. Nếu bị bác/rút trong vài lượt → không final.

### Transcript mẫu

```
[00:00:05] Lan: Hôm nay brainstorm phương án thanh toán nhé.
[00:00:30] Lan: Hay là mình chốt luôn Stripe đi cho nhanh nhỉ?
[00:00:42] Nam: Dạ... chốt luôn ạ?
[00:00:55] Hà: Khoan chị, em chưa có số liệu, chốt bây giờ rủi ro lắm ạ.
[00:01:08] Lan: Ừ nhỉ, chị nói vậy thôi chứ chưa đủ dữ liệu. Thôi chưa chốt nhé.
```

### Kết quả SAI (KHÔNG làm vậy)

```json
{
  "items": [
    {
      "id": "D1", "type": "decision", "content": "Chốt Stripe",
      "status": "final", "decided_by": "Lan",
      "evidence": [{"quote": "chốt luôn Stripe đi cho nhanh nhỉ",
                    "timestamp": "00:00:30", "speaker": "Lan", "turn": 2,
                    "role_in_discussion": "decide"}]
    }
  ]
}
```

**SAI vì:** câu "chốt luôn" bị bác ngay lượt sau ("khoan, chưa có số liệu") → đây là
nói chơi, không phải chốt. Nếu output `status="final"` thì host review sẽ KHÔNG tin được.

### Kết quả ĐÚNG

```json
{
  "items": [
    {
      "id": "O1", "type": "open_issue",
      "content": "Chưa chọn được phương án thanh toán — cần thêm dữ liệu",
      "next_step": "Hẹn họp lại sau khi có dữ liệu so sánh Stripe vs VNPay",
      "next_step_owner": "Lan",
      "evidence": [
        {"quote": "khoan chưa có số liệu chốt bây giờ rủi ro lắm",
         "timestamp": "00:00:55", "speaker": "Hà", "turn": 4,
         "role_in_discussion": "object"},
        {"quote": "Thôi chưa chốt nhé.",
         "timestamp": "00:01:08", "speaker": "Lan", "turn": 5,
         "role_in_discussion": "info"}
      ],
      "confidence": 0.55, "confidence_reason": "chưa chốt, mở Open Issue cho họp sau"
    }
  ]
}
```

**ĐÚNG vì:** bám 3 điều kiện M3-A — câu chốt bị rút ngay lượt 4-5 → không final; chuyển
sang Open Issue có next_step cụ thể (R3). Transcript ngắn dễ thấy false-chốt, transcript
dài >100 turns dễ lọt nếu LLM chỉ nghe chữ "chốt" đơn lẻ.