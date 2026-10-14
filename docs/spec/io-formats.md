# Spec - IO formats: transcript, turns, meta, golden

Hợp đồng dữ liệu vào/ra cho `ingest.py` (P0). Nguồn: PLAN_MVP §3, §6.2 — gom về 1 nơi.
Định nghĩa từ vựng: `glossary.md`.

## 1. Transcript đầu vào (`data/transcripts/`)

Ba định dạng được chấp nhận: `.txt`, `.srt` và `.docx`. Tất cả đều **synthetic** (repo public),
tiếng Việt, ≥3 speaker, timestamp tăng dần.

### 1.1. `.txt` — mỗi dòng = 1 turn

```
[00:00:05] Lan: Chào mọi người, bắt đầu họp nhé.
[00:00:12] Nam: Em xin phép trình bày phương án A.
```

- Regex: `^\[(\d{2}:\d{2}:\d{2})\]\s*(.+?):\s*(.+)$` → `{t_start, speaker, text}`
- Speaker là chuỗi trước dấu `:` đầu tiên (trim khoảng trắng dư).

### 1.2. `.srt` — block 4 dòng

```
1
00:00:05,000 --> 00:00:08,000
Lan: Chào mọi người, bắt đầu họp nhé.

2
00:00:12,000 --> 00:00:15,500
Nam: Em xin phép trình bày phương án A.
```

- Bỏ dòng index; parse timecode `HH:MM:SS,mmm --> HH:MM:SS,mmm`.
- Text có thể 1-2 dòng → **gộp thành 1 turn**.
- Speaker tách theo pattern `Tên:` như .txt; nếu không có → `speaker=""`, để pass-2 xử lý.

### 1.3. `.docx` — mỗi paragraph (và mỗi cell table) = 1 dòng, parse như `.txt`

- Chỉ dòng đúng format `[HH:MM:SS] Tên: nội dung` mới thành turn; đoạn khác → skip + limitation
  (KHÔNG bịa timestamp — evidence cần timestamp thật).
- File không có dòng nào parse được → ingest vẫn trả turns rỗng + limitation (caller báo 422).

### 1.4. Chuẩn hoá (cả 3 định dạng)

- `t_start`/`t_end`: chuẩn về `HH:MM:SS` (bỏ phần mmm).
- Trim khoảng trắng dư; **không tự sửa nội dung** (giữ nguyên văn để verify quote — R5).

## 2. turns.json (output ingest → input extract)

```json
[
  {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:08", "speaker": "Lan", "text": "Chào mọi người, bắt đầu họp nhé."},
  {"turn": 2, "t_start": "00:00:12", "t_end": "00:00:15", "speaker": "Nam", "text": "Em xin phép trình bày phương án A."}
]
```

## 3. meta.json (`data/meta/tcN_meta.json`)

```json
{
  "id": "tc2",
  "title": "Họp chọn vendor",
  "date": "2026-10-12",
  "participants": [
    {"name": "Lan", "role": "PM", "aliases": ["chị Lan", "Lan"]},
    {"name": "Nam", "role": "BA", "aliases": ["Nam", "em Nam"]}
  ],
  "glossary": {"KH": "khách hàng", "VG": "vòng gọi", "SLA": "service level agreement"}
}
```

- `date`: ISO `YYYY-MM-DD` — căn cứ deterministic cho entity-link ngày tương đối (R2).
- `participants[].aliases`: chứa biến thể (em/chị + tên). Tên ngoài danh sách này là **sai** (không suy ra).

## 4. golden.json (`data/golden/tcN_expected.json`)

Kỳ vọng **tối thiểu** để eval runner so (chi tiết tiêu chí: `spec/eval-plan.md`):

```json
{
  "decisions_final": [{"content": "Chốt phương án B", "decided_by": "Lan", "supersedes": ["D0"], "evidence_ts": "00:45:30"}],
  "tasks": [{"what": "Gửi báo giá B", "owner": "Nam", "due": "2026-10-12", "link_to_decision": "D1"}],
  "no_decision": false
}
```

- Chỉ so các trường then chốt; phần mơ hồ/sarcasm chấm tay (host).
- ID item (D1/T1): **không so cứng thứ tự** — so theo nội dung.

## 5. Quy tắc parse (tóm tắt cho code)

| Tình huống | Hành vi |
|---|---|
| SRT text 2 dòng | Gộp bằng khoảng trắng → 1 turn |
| Không có `Tên:` trong SRT text | `speaker=""` → pass-2 xử lý, không tự đoán |
| Timecode thiếu / `t_end < t_start` | Bỏ qua turn, ghi `known_limitations` |
| Timestamp không tăng dần | Giữ thứ tự dòng; eval không tính ca này |