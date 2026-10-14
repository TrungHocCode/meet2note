"""
test_ingest.py — Parse transcript .txt / .srt theo io-formats §1, §5.

Bao phủ:
- parse .txt mẫu (happy path)
- parse .srt gộp 2 dòng text thành 1 turn
- speaker thiếu → speaker="" (không tự đoán)
- timecode hỏng → bỏ turn + ghi limitation
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.ingest import parse_transcript


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "transcripts"


# ──────────────────────────────────────────────────────────────────────
# TXT — happy path
# ──────────────────────────────────────────────────────────────────────


def test_parse_txt_returns_list_of_turns(tmp_path: Path) -> None:
    f = tmp_path / "ok.txt"
    f.write_text(
        "[00:00:05] Lan: Chào mọi người, bắt đầu họp nhé.\n"
        "[00:00:12] Nam: Em xin phép trình bày phương án A.\n",
        encoding="utf-8",
    )
    turns, lims = parse_transcript(f)
    assert lims == []
    assert len(turns) == 2
    assert turns[0]["turn"] == 1
    assert turns[0]["t_start"] == "00:00:05"
    assert turns[0]["t_end"] == "00:00:05"  # txt: t_end = t_start
    assert turns[0]["speaker"] == "Lan"
    assert turns[0]["text"].startswith("Chào")
    assert turns[1]["turn"] == 2
    assert turns[1]["speaker"] == "Nam"
    assert turns[1]["text"].startswith("Em xin")


def test_parse_txt_keeps_quote_verbatim(tmp_path: Path) -> None:
    """R5: quote phải khớp nguyên văn → ingest KHÔNG sửa nội dung.

    Inner whitespace + dấu câu giữ nguyên, chỉ trim đầu/cuối.
    """
    f = tmp_path / "verbatim.txt"
    f.write_text(
        "[00:01:00] Nam:  Chào   Lan,  test  \n",  # nhiều khoảng trắng bên trong
        encoding="utf-8",
    )
    turns, _ = parse_transcript(f)
    assert turns[0]["speaker"] == "Nam"
    assert turns[0]["text"] == "Chào   Lan,  test"  # giữ nguyên khoảng trắng giữa, trim đầu/cuối


def test_parse_txt_skips_malformed(tmp_path: Path) -> None:
    f = tmp_path / "bad.txt"
    f.write_text(
        "[00:00:05] Lan: OK dòng hợp lệ.\n"
        "không có timestamp\n"
        "[99:99:99] Nam: bad timecode\n",
        encoding="utf-8",
    )
    turns, lims = parse_transcript(f)
    assert len(turns) == 1
    assert turns[0]["speaker"] == "Lan"
    assert len(lims) >= 1
    assert any("malformed" in s.lower() or "line" in s.lower() for s in lims)


# ──────────────────────────────────────────────────────────────────────
# SRT — happy path + 2-line text + missing speaker
# ──────────────────────────────────────────────────────────────────────


def test_parse_srt_basic(tmp_path: Path) -> None:
    f = tmp_path / "ok.srt"
    f.write_text(
        "1\n"
        "00:00:05,000 --> 00:00:08,000\n"
        "Lan: Chào mọi người, bắt đầu họp nhé.\n"
        "\n"
        "2\n"
        "00:00:12,000 --> 00:00:15,500\n"
        "Nam: Em xin phép trình bày phương án A.\n",
        encoding="utf-8",
    )
    turns, lims = parse_transcript(f)
    assert lims == []
    assert len(turns) == 2
    assert turns[0]["t_start"] == "00:00:05"
    assert turns[0]["t_end"] == "00:00:08"
    assert turns[0]["speaker"] == "Lan"
    assert turns[1]["t_end"] == "00:00:15"


def test_parse_srt_merges_two_line_text(tmp_path: Path) -> None:
    """io-formats §5: SRT text 2 dòng → gộp thành 1 turn bằng khoảng trắng."""
    f = tmp_path / "twoline.srt"
    f.write_text(
        "1\n"
        "00:00:05,000 --> 00:00:08,000\n"
        "Lan: Chào mọi người,\n"
        "bắt đầu họp nhé.\n",
        encoding="utf-8",
    )
    turns, lims = parse_transcript(f)
    assert lims == []
    assert len(turns) == 1
    assert turns[0]["text"] == "Chào mọi người, bắt đầu họp nhé."
    assert turns[0]["speaker"] == "Lan"


def test_parse_srt_missing_speaker(tmp_path: Path) -> None:
    """io-formats §1.2 + §5: không 'Tên:' → speaker='' (không tự đoán)."""
    f = tmp_path / "nospeaker.srt"
    f.write_text(
        "1\n"
        "00:00:05,000 --> 00:00:08,000\n"
        "Chào mọi người, bắt đầu họp nhé.\n",
        encoding="utf-8",
    )
    turns, lims = parse_transcript(f)
    assert turns[0]["speaker"] == ""
    assert turns[0]["text"].startswith("Chào")


def test_parse_srt_malformed_timecode(tmp_path: Path) -> None:
    f = tmp_path / "bad.srt"
    f.write_text(
        "1\n"
        "GARBAGE_TIME\n"
        "Lan: Không có timecode.\n",
        encoding="utf-8",
    )
    turns, lims = parse_transcript(f)
    assert len(turns) == 0
    assert any("thiếu timecode" in s or "timecode" in s.lower() for s in lims)


def test_parse_srt_t_end_lt_t_start(tmp_path: Path) -> None:
    """io-formats §5: t_end < t_start → bỏ turn + ghi limitation."""
    f = tmp_path / "reverse.srt"
    f.write_text(
        "1\n"
        "00:00:10,000 --> 00:00:05,000\n"  # end < start
        "Lan: Test\n",
        encoding="utf-8",
    )
    turns, lims = parse_transcript(f)
    assert len(turns) == 0
    assert any("t_end" in s or "t_end < t_start" in s for s in lims)


# ──────────────────────────────────────────────────────────────────────
# Error path
# ──────────────────────────────────────────────────────────────────────


def test_parse_transcript_unsupported_extension(tmp_path: Path) -> None:
    f = tmp_path / "weird.md"
    f.write_text("whatever", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_transcript(f)


def test_parse_transcript_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_transcript(tmp_path / "nope.txt")


# ──────────────────────────────────────────────────────────────────────
# Fixtures P0 — smoke test (không phải gate, nhưng giúp phát hiện sớm)
# ──────────────────────────────────────────────────────────────────────


def test_tc1_fixture_parses(fixtures_dir: Path) -> None:
    f = fixtures_dir / "tc1_happy.txt"
    if not f.exists():
        pytest.skip(f"fixture chưa có: {f}")
    turns, _ = parse_transcript(f)
    # Transcripts v2 (dài + nhiễu): tc1 ~90 turns; để biên độ rộng
    assert 80 <= len(turns) <= 110, f"tc1 expected ~90 turns, got {len(turns)}"


def test_tc2_fixture_parses(fixtures_dir: Path) -> None:
    f = fixtures_dir / "tc2_atob.txt"
    if not f.exists():
        pytest.skip(f"fixture chưa có: {f}")
    turns, _ = parse_transcript(f)
    assert 90 <= len(turns) <= 120, f"tc2 expected ~100 turns, got {len(turns)}"
    # Quote then chốt phải tồn tại đúng nguyên văn
    full = " ".join(t["text"] for t in turns)
    assert "Em đề xuất phương án A, bên X rẻ hơn 20%." in full
    assert "Vậy chốt B nhé, cả team đồng ý không?" in full
    assert "Dạ em gửi báo giá B cho khách trước 12/10." in full