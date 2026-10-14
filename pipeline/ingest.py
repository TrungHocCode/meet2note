"""
ingest.py — Parse transcript (.txt / .srt / .docx) → list[dict] turns.

Hợp đồng: `docs/spec/io-formats.md` §1, §2, §5.
Output `turns` là input cho `extract` (pass-1 LLM) ở P1+.

Triết lý (AGENTS.md §1, §5):
- LLM đề xuất, code kiểm chứng — ingest KHÔNG sửa nội dung transcript
  (giữ nguyên văn để verify fuzzy ở R5).
- Trung thực: timecode hỏng / thiếu speaker ghi vào `known_limitations`,
  KHÔNG bịa / KHÔNG im lặng.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────
# Regex theo io-formats §1.1, §1.2
# ──────────────────────────────────────────────────────────────────────

# .txt: [HH:MM:SS] Tên: nội dung — giờ 00-23, phút/giây 00-59.
RE_TXT = re.compile(
    r"^\[(?P<h>2[0-3]|[01]\d):(?P<m>[0-5]\d):(?P<s>[0-5]\d)\]\s*"
    r"(?P<speaker>.+?):\s*(?P<text>.+)$"
)

# .srt timecode: HH:MM:SS,mmm --> HH:MM:SS,mmm  (cho phép '.' thay ',')
RE_SRT_TIMECODE = re.compile(
    r"^(\d{2}:\d{2}:\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{2}:\d{2}:\d{2})[,.](\d{1,3})(?:\s.*)?$"
)

# Speaker: phần trước dấu ':' đầu tiên trong text SRT.
RE_SRT_SPEAKER = re.compile(r"^(?P<speaker>.+?):\s*(?P<text>.+)$", re.DOTALL)


# ──────────────────────────────────────────────────────────────────────
# Helpers nội bộ
# ──────────────────────────────────────────────────────────────────────


def _hms(seconds_or_full: str, ms: str = "0") -> str:
    """Bỏ phần milliseconds — chuẩn hoá về HH:MM:SS theo io-formats §1.3."""
    # HH:MM:SS đã đúng format; chỉ cần strip.
    if ":" not in seconds_or_full:
        return seconds_or_full
    return seconds_or_full.strip()


def _split_speaker(text: str) -> tuple[str, str]:
    """Tách 'Tên: nội dung'. Không có → ('', text nguyên)."""
    m = RE_SRT_SPEAKER.match(text.strip())
    if m is None:
        return "", text.strip()
    return m.group("speaker").strip(), m.group("text").strip()


def _parse_txt(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    turns: list[dict[str, Any]] = []
    limitations: list[str] = []
    raw = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(raw.splitlines(), start=1):
        line = line.rstrip()
        if not line.strip():
            continue
        m = RE_TXT.match(line)
        if m is None:
            limitations.append(
                f"txt line {lineno}: malformed, skipped -> '{line[:60]}'"
            )
            continue
        t_start = _hms(f"{m.group('h')}:{m.group('m')}:{m.group('s')}")
        # .txt không có t_end riêng → đặt bằng t_start (đánh dấu đơn điểm).
        t_end = t_start
        if t_end < t_start:
            limitations.append(
                f"txt line {lineno}: t_end < t_start, skipped -> '{line[:60]}'"
            )
            continue
        turns.append(
            {
                "turn": 0,  # gán ở bước cuối (1-indexed)
                "t_start": t_start,
                "t_end": t_end,
                "speaker": m.group("speaker").strip(),
                "text": m.group("text").strip(),
            }
        )
    # Gán turn 1-indexed
    for i, t in enumerate(turns, start=1):
        t["turn"] = i
    return turns, limitations


def _parse_srt(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse SRT: block 4 dòng (index / timecode / text 1-2 dòng / blank).

    Theo io-formats §1.2 + §5:
    - Text 2 dòng: gộp bằng khoảng trắng.
    - Không 'Tên:' → speaker="" (không tự đoán).
    - Timecode thiếu hoặc t_end < t_start: bỏ turn + ghi limitation.
    """
    turns: list[dict[str, Any]] = []
    limitations: list[str] = []
    raw = path.read_text(encoding="utf-8")

    # SRT dùng \r\n hoặc — chuẩn hoá về \n.
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    blocks = re.split(r"\n\s*\n", raw.strip())
    for block_idx, block in enumerate(blocks, start=1):
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if len(lines) < 2:
            limitations.append(
                f"srt block {block_idx}: <2 dòng, skipped -> '{block[:60]}'"
            )
            continue

        # Tìm dòng timecode — thường là dòng thứ 2, nhưng cho phép block
        # không có index (một số SRT rút gọn).
        tc_idx = None
        for i, ln in enumerate(lines):
            if "-->" in ln:
                tc_idx = i
                break
        if tc_idx is None:
            limitations.append(
                f"srt block {block_idx}: thiếu timecode, skipped"
            )
            continue

        m = RE_SRT_TIMECODE.match(lines[tc_idx].strip())
        if m is None:
            limitations.append(
                f"srt block {block_idx}: timecode malformed -> "
                f"'{lines[tc_idx][:60]}'"
            )
            continue

        t_start = _hms(m.group(1), m.group(2))
        t_end = _hms(m.group(3), m.group(4))

        # Phần text = các dòng sau timecode; bỏ dòng index nếu có.
        text_lines = lines[tc_idx + 1 :]
        # Nếu có dòng index là dòng đầu (chỉ chứa số), bỏ qua.
        if tc_idx >= 1 and lines[0].strip().isdigit():
            pass  # text_lines đã đúng; không cần xử lý thêm
        text = " ".join(ln.strip() for ln in text_lines).strip()
        if not text:
            limitations.append(
                f"srt block {block_idx}: rỗng text, skipped"
            )
            continue

        # t_end < t_start → bỏ (io-formats §5)
        if t_end < t_start:
            limitations.append(
                f"srt block {block_idx}: t_end < t_start ({t_end} < {t_start}), "
                f"skipped"
            )
            continue

        speaker, body = _split_speaker(text)
        turns.append(
            {
                "turn": 0,
                "t_start": t_start,
                "t_end": t_end,
                "speaker": speaker,
                "text": body,
            }
        )

    for i, t in enumerate(turns, start=1):
        t["turn"] = i
    return turns, limitations


def _parse_docx(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse .docx: mỗi paragraph (và mỗi cell table) là 1 dòng text,
    parse theo format `[HH:MM:SS] Tên: nội dung` như .txt (io-formats §1.3).

    Đoạn không đúng format → skip + limitation (KHÔNG bịa timestamp —
    evidence cần timestamp thật).
    """
    try:
        from docx import Document
    except ImportError as e:
        raise RuntimeError(
            "thiếu dependency python-docx (pip install python-docx)"
        ) from e

    doc = Document(str(path))
    lines: list[str] = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                lines.append(cell.text)

    turns: list[dict[str, Any]] = []
    limitations: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        line = (line or "").rstrip()
        if not line.strip():
            continue
        m = RE_TXT.match(line)
        if m is None:
            limitations.append(
                f"docx para {lineno}: không đúng format '[HH:MM:SS] Tên: ...', "
                f"skipped -> '{line[:60]}'"
            )
            continue
        t_start = _hms(f"{m.group('h')}:{m.group('m')}:{m.group('s')}")
        turns.append(
            {
                "turn": 0,  # gán ở bước cuối (1-indexed)
                "t_start": t_start,
                "t_end": t_start,  # như .txt (đánh dấu đơn điểm)
                "speaker": m.group("speaker").strip(),
                "text": m.group("text").strip(),
            }
        )
    for i, t in enumerate(turns, start=1):
        t["turn"] = i
    if not turns:
        limitations.append("docx: không có đoạn nào parse được (cần format '[HH:MM:SS] Tên: ...')")
    return turns, limitations


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def parse_transcript(
    path: str | Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse transcript file → (turns, limitations).

    Args:
        path: đường dẫn tới file `.txt` / `.srt` / `.docx` (utf-8).

    Returns:
        turns: list[dict] — `[{turn, t_start, t_end, speaker, text}, ...]`
            - turn: int, 1-indexed
            - t_start / t_end: chuỗi `HH:MM:SS`
            - speaker: chuỗi đã trim; "" nếu SRT thiếu 'Tên:'
            - text: nội dung lượt thoại, đã trim, **nguyên văn** (không sửa)
        limitations: list[str] — các vấn đề parse gặp phải
            (timecode hỏng, thiếu speaker, t_end < t_start...).

    Raises:
        FileNotFoundError: file không tồn tại.
        ValueError: extension không phải .txt / .srt / .docx.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"transcript not found: {p}")
    ext = p.suffix.lower()
    if ext == ".txt":
        return _parse_txt(p)
    if ext == ".srt":
        return _parse_srt(p)
    if ext == ".docx":
        return _parse_docx(p)
    raise ValueError(
        f"unsupported transcript extension: '{ext}' "
        "(chỉ chấp nhận .txt / .srt / .docx theo io-formats §1)"
    )


__all__ = ["parse_transcript"]