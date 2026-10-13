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