"""
test_extract.py — Mock LLM test cho extract (chunking, retry, prompt fill, log).

Phủ (theo P1 yêu cầu):
- prompt fill đúng meta (date, participants, glossary)
- chunking với input nhỏ / vừa / lớn, có overlap
- retry khi JSON lỗi (attempt 1 fail → attempt 2 success)
- retry hết (3 lần fail → trả empty + ghi limitation)
- dedup theo `id` xuyên chunk
- llm_log.jsonl ghi đúng format
- call_llm raise rõ khi thiếu env
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline.extract import (
    _strip_llm_wrappers,
    _try_parse_items,
    build_messages,
    call_llm,
    chunk_turns,
    extract,
    fill_meta_placeholders,
    load_prompt,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def tc1_meta() -> dict[str, Any]:
    return {
        "id": "tc1",
        "title": "Sprint 14 planning",
        "date": "2026-10-13",
        "participants": [
            {"name": "Lan", "role": "PM", "aliases": ["chị Lan", "Lan"]},
            {"name": "Nam", "role": "BA", "aliases": ["Nam", "em Nam"]},
            {"name": "Hà", "role": "Dev", "aliases": ["em Hà", "Hà"]},
            {"name": "Minh", "role": "QA", "aliases": ["em Minh", "Minh"]},
        ],
        "glossary": {
            "sprint": "chu kỳ phát triển 2 tuần",
            "blocker": "vướng mắc cần hỗ trợ gỡ",
        },
    }


@pytest.fixture
def small_turns() -> list[dict[str, Any]]:
    """5 turns — 1 chunk duy nhất."""
    return [
        {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
         "speaker": "Lan", "text": "Chào cả nhóm."},
        {"turn": 2, "t_start": "00:00:11", "t_end": "00:00:11",
         "speaker": "Nam", "text": "Em đề xuất phương án A."},
        {"turn": 3, "t_start": "00:00:30", "t_end": "00:00:30",
         "speaker": "Lan", "text": "Chốt B nhé."},
        {"turn": 4, "t_start": "00:01:00", "t_end": "00:01:00",
         "speaker": "Nam", "text": "Em đồng ý."},
        {"turn": 5, "t_start": "00:02:00", "t_end": "00:02:00",
         "speaker": "Hà", "text": "Em đồng ý."},
    ]


# ──────────────────────────────────────────────────────────────────────
# Prompt load + fill
# ──────────────────────────────────────────────────────────────────────


def test_load_prompt_returns_text() -> None:
    txt = load_prompt("system_extract.md")
    assert "{date}" in txt  # template có placeholder
    assert len(txt) > 100


def test_load_prompt_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist.md")


def test_fill_meta_placeholders_full(tc1_meta) -> None:
    tpl = "Date: {date}\nParticipants: {name (role, aliases)}\nGlossary: {terms}"
    out = fill_meta_placeholders(tpl, tc1_meta)
    assert "Date: 2026-10-13" in out
    assert "Lan (PM, aliases: chị Lan, Lan)" in out
    assert "Nam (BA, aliases: Nam, em Nam)" in out
    assert "sprint = chu kỳ phát triển 2 tuần" in out
    assert "blocker = vướng mắc cần hỗ trợ gỡ" in out


def test_fill_meta_placeholders_empty_participants_glossary() -> None:
    out = fill_meta_placeholders(
        "P: {name (role, aliases)}\nG: {terms}",
        {"participants": [], "glossary": {}},
    )
    assert out == "P: (none)\nG: (none)"


def test_build_messages_structure(tc1_meta, small_turns) -> None:
    msgs = build_messages(tc1_meta, small_turns)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    # System có date + glossary đã fill
    sys_content = msgs[0]["content"]
    assert "2026-10-13" in sys_content
    assert "sprint" in sys_content
    # User có fewshot + transcript
    user_content = msgs[1]["content"]
    assert "Few-shot" in user_content or "few-shot" in user_content.lower()
    assert "[turn 1]" in user_content
    assert "[turn 5]" in user_content
    assert "Chào cả nhóm." in user_content


# ──────────────────────────────────────────────────────────────────────
# Chunking
# ──────────────────────────────────────────────────────────────────────


def test_chunk_turns_empty() -> None:
    assert chunk_turns([]) == []


def test_chunk_turns_smaller_than_chunk_size() -> None:
    """5 turns < 80 → 1 chunk chứa tất cả."""
    turns = [{"turn": i, "text": f"t{i}"} for i in range(1, 6)]
    chunks = chunk_turns(turns)
    assert len(chunks) == 1
    assert len(chunks[0]) == 5


def test_chunk_turns_exactly_chunk_size() -> None:
    """80 turns = chunk_size → 1 chunk."""
    turns = [{"turn": i, "text": "x"} for i in range(1, 81)]
    chunks = chunk_turns(turns, chunk_size=80, overlap=10)
    assert len(chunks) == 1
    assert len(chunks[0]) == 80


def test_chunk_turns_with_overlap_default() -> None:
    """100 turns với chunk_size=80, overlap=10 → step=70, 2 chunks có overlap 71-80."""
    turns = [{"turn": i, "text": f"Turn {i}"} for i in range(1, 101)]
    chunks = chunk_turns(turns, chunk_size=80, overlap=10)

    assert len(chunks) == 2
    # Chunk 0: turns 1-80
    assert chunks[0][0]["turn"] == 1
    assert chunks[0][-1]["turn"] == 80
    # Chunk 1: turns 71-100 (overlap 71-80)
    assert chunks[1][0]["turn"] == 71
    assert chunks[1][-1]["turn"] == 100
    # Overlap: chunk 1's first 10 = chunk 0's last 10
    overlap_text_0 = [t["text"] for t in chunks[0][-10:]]
    overlap_text_1 = [t["text"] for t in chunks[1][:10]]
    assert overlap_text_0 == overlap_text_1


def test_chunk_turns_three_chunks() -> None:
    """170 turns với chunk=80, overlap=10 → step=70 → 3 chunks (70→140, 140→170)."""
    turns = [{"turn": i, "text": "x"} for i in range(1, 171)]
    chunks = chunk_turns(turns, chunk_size=80, overlap=10)
    # i=0: turns[0:80], i=70: turns[70:150], i=140: turns[140:170]
    assert len(chunks) == 3
    assert chunks[0][-1]["turn"] == 80
    assert chunks[1][0]["turn"] == 71
    assert chunks[1][-1]["turn"] == 150
    assert chunks[2][0]["turn"] == 141
    assert chunks[2][-1]["turn"] == 170


def test_chunk_turns_overlap_geq_size_clamps_step() -> None:
    """overlap >= chunk_size (cấu hình sai) → ép step=1."""
    turns = [{"turn": i, "text": "x"} for i in range(1, 11)]
    chunks = chunk_turns(turns, chunk_size=5, overlap=10)
    # step = max(1, 5-10) = 1
    # i=0: [0:5], i=1: [1:6], i=2: [2:7], i=3: [3:8], i=4: [4:9], i=5: [5:10]
    assert len(chunks) == 6
    assert chunks[-1][-1]["turn"] == 10


# ──────────────────────────────────────────────────────────────────────
# Retry on JSON parse error
# ──────────────────────────────────────────────────────────────────────


def test_extract_retry_recovers_on_attempt_2(tmp_path: Path, tc1_meta, small_turns) -> None:
    """LLM trả JSON hỏng attempt 1 → retry attempt 2 → thành công."""
    valid_response = json.dumps({"items": [{
        "id": "D1", "type": "decision", "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Chốt B nhé.", "timestamp": "00:00:30",
            "speaker": "Lan", "turn": 3, "role_in_discussion": "decide",
        }],
    }]})

    call_count = {"n": 0}

    def llm_fn(messages):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "not valid json {{{ broken"
        return valid_response

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == "D1"
    assert call_count["n"] == 2  # 1 fail + 1 success
    assert result["conf_llm_map"]["D1"] == pytest.approx(0.8)
    assert result["known_limitations"] == []

    # Log có 2 entries (1 fail + 1 success)
    log_lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(log_lines) == 2
    log0 = json.loads(log_lines[0])
    log1 = json.loads(log_lines[1])
    assert log0["attempt"] == 0
    assert "error" in log0
    assert log1["attempt"] == 1
    assert log1.get("items_count") == 1


def test_extract_retry_on_unknown_type(
    tmp_path: Path, tc1_meta, small_turns
) -> None:
    """LLM trả type lạ → retry → success.

    Extract chỉ check shape (id + type thuộc 6 loại); validate chặt dời sang
    verify theo từng item (layering sau live-test qwen3 local).
    """
    bad_response = json.dumps({"items": [{
        "id": "D1", "type": "verdict", "content": "Chốt B",  # INVALID type
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [],
    }]})
    good_response = json.dumps({"items": [{
        "id": "D1", "type": "decision", "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Chốt B nhé.", "timestamp": "00:00:30",
            "speaker": "Lan", "turn": 3, "role_in_discussion": "decide",
        }],
    }]})

    call_count = {"n": 0}

    def llm_fn(messages):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return bad_response
        return good_response

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    assert len(result["items"]) == 1
    assert result["items"][0]["status"] == "final"
    assert call_count["n"] == 2


def test_extract_gives_up_after_max_retries(
    tmp_path: Path, tc1_meta, small_turns
) -> None:
    """LLM fail 3 lần liên tiếp (initial + 2 retries) → trả empty + limitation."""
    call_count = {"n": 0}

    def llm_fn(messages):
        call_count["n"] += 1
        return "still broken json"

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    assert result["items"] == []
    assert result["conf_llm_map"] == {}
    assert call_count["n"] == 3  # initial + 2 retries
    assert len(result["known_limitations"]) == 1
    assert "chunk 0" in result["known_limitations"][0]
    assert "không trả JSON hợp lệ" in result["known_limitations"][0]
    assert "3 lần" in result["known_limitations"][0]


def test_extract_retry_message_contains_error_feedback(tc1_meta, small_turns) -> None:
    """Retry message phải chứa error text để LLM biết cần sửa gì."""
    captured: list[list[dict[str, str]]] = []

    def llm_fn(messages):
        captured.append(messages)
        return "still bad"

    extract(tc1_meta, small_turns, llm_fn=llm_fn, max_retries=2)

    # Attempt 0: gốc, attempt 1: + user message có "không hợp lệ", attempt 2: + user message
    assert len(captured) == 3
    assert len(captured[0]) == 2  # system + user (gốc)
    assert len(captured[1]) == 3  # + feedback
    assert "không hợp lệ" in captured[1][-1]["content"]
    assert "JSON" in captured[2][-1]["content"]


# ──────────────────────────────────────────────────────────────────────
# Dedup across chunks
# ──────────────────────────────────────────────────────────────────────


def test_extract_dedup_ids_across_chunks(tmp_path: Path, tc1_meta) -> None:
    """LLM trả cùng `id` ở 2 chunk overlap → chỉ giữ 1 bản."""
    # 100 turns → 2 chunks (overlap turns 71-80)
    turns = [{"turn": i, "t_start": f"00:00:{i:02d}", "t_end": f"00:00:{i:02d}",
              "speaker": "Lan", "text": f"Turn {i}"} for i in range(1, 101)]

    item = {
        "id": "D1", "type": "decision", "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Turn 50", "timestamp": "00:00:50",
            "speaker": "Lan", "turn": 50, "role_in_discussion": "decide",
        }],
    }

    chunk_idx = {"n": 0}

    def llm_fn(messages):
        # Cả 2 chunk đều trả cùng item D1
        chunk_idx["n"] += 1
        return json.dumps({"items": [item]})

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, turns, log_path=log_path, llm_fn=llm_fn)

    assert len(result["items"]) == 1  # dedup
    assert result["items"][0]["id"] == "D1"
    assert chunk_idx["n"] == 2  # 2 chunks được gọi


def test_extract_distinct_ids_merged(tmp_path: Path, tc1_meta) -> None:
    """LLM trả id khác nhau ở 2 chunk → giữ cả 2."""
    turns = [{"turn": i, "t_start": f"00:00:{i:02d}", "t_end": f"00:00:{i:02d}",
              "speaker": "Lan", "text": f"Turn {i}"} for i in range(1, 101)]

    item1 = {
        "id": "D1", "type": "decision", "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Turn 10", "timestamp": "00:00:10",
            "speaker": "Lan", "turn": 10, "role_in_discussion": "decide",
        }],
    }
    item2 = {
        "id": "T1", "type": "task",
        "what": "X task", "owner": "Nam", "owner_source": "explicit",
        "due": "2026-10-20", "due_source": "explicit",
        "due_hint": None, "link_to_decision": None,
        "confidence": 0.7, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Turn 85", "timestamp": "00:00:85"[:11].replace("85", "25"),
            "speaker": "Nam", "turn": 85, "role_in_discussion": "confirm",
        }],
    }

    chunk_idx = {"n": 0}

    def llm_fn(messages):
        chunk_idx["n"] += 1
        if chunk_idx["n"] == 1:
            return json.dumps({"items": [item1]})
        return json.dumps({"items": [item2]})

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, turns, log_path=log_path, llm_fn=llm_fn)

    assert len(result["items"]) == 2
    ids = {i["id"] for i in result["items"]}
    assert ids == {"D1", "T1"}


def test_extract_dedup_within_single_chunk(tmp_path: Path, tc1_meta, small_turns) -> None:
    """LLM trùng id trong cùng 1 chunk → chỉ giữ 1."""
    item = {
        "id": "D1", "type": "decision", "content": "Chốt B",
        "status": "final", "decided_by": "Lan",
        "confidence": 0.8, "confidence_reason": "ok",
        "evidence": [{
            "quote": "Chốt B nhé.", "timestamp": "00:00:30",
            "speaker": "Lan", "turn": 3, "role_in_discussion": "decide",
        }],
    }

    def llm_fn(messages):
        return json.dumps({"items": [item, item]})  # duplicate

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    assert len(result["items"]) == 1


# ──────────────────────────────────────────────────────────────────────
# Empty input
# ──────────────────────────────────────────────────────────────────────


def test_extract_empty_turns_returns_empty(tmp_path: Path, tc1_meta) -> None:
    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, [], log_path=log_path)
    assert result["items"] == []
    assert result["conf_llm_map"] == {}
    # Log file được tạo nhưng rỗng (không có request)
    assert log_path.exists()


# ──────────────────────────────────────────────────────────────────────
# LLM call env guard
# ──────────────────────────────────────────────────────────────────────


def test_call_llm_raises_without_env(monkeypatch) -> None:
    """Không có OPENAI_BASE_URL hoặc MODEL_NAME → raise RuntimeError rõ ràng."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LLM chưa cấu hình"):
        call_llm([{"role": "user", "content": "hi"}])


def test_call_llm_raises_when_only_base_url(monkeypatch) -> None:
    """Có base_url nhưng thiếu model → vẫn raise."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    with pytest.raises(RuntimeError, match="LLM chưa cấu hình"):
        call_llm([{"role": "user", "content": "hi"}])


def test_call_llm_url_construction_no_chat_completions(monkeypatch) -> None:
    """URL không có /chat/completions → tự append."""
    # Verify URL building bằng cách monkeypatch httpx.Client
    import httpx as _httpx

    captured_url = {"value": None}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, **kwargs):
            captured_url["value"] = url
            # Trả response giả
            r = _httpx.Response(200, json={
                "choices": [{"message": {"content": "{}"}}]
            })
            return r

    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(_httpx, "Client", FakeClient)

    call_llm([{"role": "user", "content": "x"}])
    assert captured_url["value"] == "https://api.example.com/v1/chat/completions"


def test_call_llm_url_construction_with_chat_completions(monkeypatch) -> None:
    """URL đã có /chat/completions → không append thêm."""
    import httpx as _httpx

    captured_url = {"value": None}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, **kwargs):
            captured_url["value"] = url
            r = _httpx.Response(200, json={
                "choices": [{"message": {"content": "{}"}}]
            })
            return r

    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1/chat/completions")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(_httpx, "Client", FakeClient)

    call_llm([{"role": "user", "content": "x"}])
    assert captured_url["value"] == "https://api.example.com/v1/chat/completions"


# ──────────────────────────────────────────────────────────────────────
# Log file format
# ──────────────────────────────────────────────────────────────────────


def test_extract_log_entry_format(tmp_path: Path, tc1_meta, small_turns) -> None:
    """Mỗi request/response ghi 1 dòng JSON hợp lệ với ts, chunk, attempt, request, response."""
    def llm_fn(messages):
        return json.dumps({"items": []})

    log_path = tmp_path / "subdir" / "llm.jsonl"
    extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1  # 1 chunk, 1 attempt
    entry = json.loads(lines[0])
    assert entry["ts"]  # ISO timestamp
    assert entry["chunk"] == 0
    assert entry["attempt"] == 0
    assert isinstance(entry["request"], list)
    assert entry["request"][0]["role"] == "system"
    assert entry["response"] == '{"items": []}'
    assert entry["items_count"] == 0


def test_extract_appends_to_existing_log(tmp_path: Path, tc1_meta, small_turns) -> None:
    """Log file append (không overwrite) — cho phép resume / multi-call."""
    log_path = tmp_path / "llm.jsonl"
    log_path.write_text('{"existing": true}\n', encoding="utf-8")

    def llm_fn(messages):
        return json.dumps({"items": []})

    extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"existing": True}


# ──────────────────────────────────────────────────────────────────────
# Confidence capture
# ──────────────────────────────────────────────────────────────────────


def test_extract_conf_out_of_range_passes_through(
    tmp_path: Path, tc1_meta, small_turns
) -> None:
    """Confidence ngoài [0,1] → extract CHO QUA (lenient shape), VERIFY loại ở mức item.

    Layering sau live-test: extract không phán confidence; verify gate 1b
    (thiếu/ngoài [0,1] → bỏ item + limitation, không giết chunk).
    """
    def llm_fn(messages):
        return json.dumps({"items": [{
            "id": "D1", "type": "decision", "content": "x",
            "status": "final", "decided_by": "Lan",
            "confidence": 1.5,  # out of range — verify sẽ loại
            "confidence_reason": "ok",
            "evidence": [{
                "quote": "Chốt B nhé.", "timestamp": "00:00:30",
                "speaker": "Lan", "turn": 3, "role_in_discussion": "decide",
            }],
        }]})

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    # Extract lenient: item qua shape-check (id + type), verify loại sau.
    assert len(result["items"]) == 1
    assert result["conf_llm_map"]["D1"] == pytest.approx(1.5)
    assert result["known_limitations"] == []


def test_extract_conf_missing_passes_through(
    tmp_path: Path, tc1_meta, small_turns
) -> None:
    """Item thiếu `confidence` → extract CHO QUA (có id + type), VERIFY loại ở mức item.

    Giữ quyết định #7 (không silent default 0.5) nhưng dời gate sang verify
    để 1 item lỗi không giết chunk (layering sau live-test qwen3 local).
    """
    def llm_fn(messages):
        return json.dumps({"items": [{
            "id": "D1", "type": "decision", "content": "x",
            "status": "final", "decided_by": "Lan",
            # no confidence field
            "confidence_reason": "ok",
            "evidence": [{
                "quote": "Chốt B nhé.", "timestamp": "00:00:30",
                "speaker": "Lan", "turn": 3, "role_in_discussion": "decide",
            }],
        }]})

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    # Extract lenient: item qua shape-check, verify loại sau (gate 1b).
    assert len(result["items"]) == 1
    assert result["known_limitations"] == []


def test_extract_skips_item_missing_id(tmp_path: Path, tc1_meta, small_turns) -> None:
    """Item không có `id` → Pydantic reject → drop chunk + log limitation với detail."""
    def llm_fn(messages):
        return json.dumps({"items": [
            {"type": "knowledge", "content": "orphan item"},  # thiếu id + confidence
        ]})

    log_path = tmp_path / "llm.jsonl"
    result = extract(tc1_meta, small_turns, log_path=log_path, llm_fn=llm_fn)

    assert result["items"] == []
    # Pydantic error message có chứa "knowledge.id"
    assert any("knowledge.id" in lim or "id" in lim for lim in result["known_limitations"])


# ──────────────────────────────────────────────────────────────────────
# Parser cứng cho model local (think-tag, fence, lời dẫn)
# ──────────────────────────────────────────────────────────────────────


def test_strip_think_tags() -> None:
    """Bóc <think>...</think> của qwen3 trước khi parse JSON."""
    raw = '<think>phân tích...\nchốt B</think>\n{"items": []}'
    assert _strip_llm_wrappers(raw) == '{"items": []}'


def test_strip_json_fence() -> None:
    """Bóc ```json fences model local hay thêm."""
    raw = '```json\n{"items": []}\n```'
    assert _strip_llm_wrappers(raw) == '{"items": []}'


def test_try_parse_items_with_leading_text() -> None:
    """Lời dẫn ngoài JSON → cắt từ '{' đầu tới '}' cuối rồi parse."""
    items, err = _try_parse_items('Đây là kết quả:\n{"items": []}\nHết.')
    assert err is None
    assert items == []


# ──────────────────────────────────────────────────────────────────────
# Prompt fill via extract (capture messages)
# ──────────────────────────────────────────────────────────────────────


def test_extract_prompt_includes_meta_context(tc1_meta, small_turns) -> None:
    """System prompt phải chứa date, participants, glossary đã fill."""
    captured: list[list[dict[str, str]]] = []

    def llm_fn(messages):
        captured.append(messages)
        return json.dumps({"items": []})

    extract(tc1_meta, small_turns, llm_fn=llm_fn)

    assert len(captured) == 1
    sys_msg = captured[0][0]
    assert sys_msg["role"] == "system"
    assert "2026-10-13" in sys_msg["content"]
    assert "Lan (PM" in sys_msg["content"]
    assert "Nam (BA" in sys_msg["content"]
    assert "sprint = chu kỳ phát triển 2 tuần" in sys_msg["content"]
    assert "blocker = vướng mắc cần hỗ trợ gỡ" in sys_msg["content"]


def test_extract_user_message_includes_turns(tc1_meta) -> None:
    """User message có transcript turns được format `[turn N] [ts] speaker: text`."""
    turns = [
        {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
         "speaker": "Lan", "text": "Xin chào"},
        {"turn": 2, "t_start": "00:00:10", "t_end": "00:00:10",
         "speaker": "Nam", "text": "Bắt đầu nhé"},
    ]

    captured: list[list[dict[str, str]]] = []

    def llm_fn(messages):
        captured.append(messages)
        return json.dumps({"items": []})

    extract(tc1_meta, turns, llm_fn=llm_fn)

    user_msg = captured[0][1]
    assert "[turn 1] [00:00:05] Lan: Xin chào" in user_msg["content"]
    assert "[turn 2] [00:00:10] Nam: Bắt đầu nhé" in user_msg["content"]


# ──────────────────────────────────────────────────────────────────────
# Smoke: realistic tc2-shaped mock → 1 chunk, expect D0+D1+T1
# ──────────────────────────────────────────────────────────────────────


def test_extract_tc2_shaped_mock() -> None:
    """Mock LLM trả shape giống fewshot (D0, D1, T1) cho 5 turns."""
    meta = {
        "id": "tc2", "title": "Chọn vendor CRM",
        "date": "2026-10-12",
        "participants": [
            {"name": "Lan", "role": "PM", "aliases": ["chị Lan"]},
            {"name": "Nam", "role": "BA", "aliases": ["em Nam"]},
        ],
        "glossary": {},
    }
    turns = [
        {"turn": 1, "t_start": "00:00:05", "t_end": "00:00:05",
         "speaker": "Lan", "text": "Chào cả nhóm."},
        {"turn": 2, "t_start": "00:00:42", "t_end": "00:00:42",
         "speaker": "Nam", "text": "Em đề xuất phương án A, bên X rẻ hơn 20%."},
        {"turn": 3, "t_start": "00:45:30", "t_end": "00:45:30",
         "speaker": "Lan", "text": "Vậy chốt B nhé, cả team đồng ý không?"},
        {"turn": 4, "t_start": "00:46:05", "t_end": "00:46:05",
         "speaker": "Nam", "text": "Dạ em gửi báo giá B cho khách trước 12/10."},
        {"turn": 5, "t_start": "00:47:00", "t_end": "00:47:00",
         "speaker": "Lan", "text": "Vậy mình end meeting nhé."},
    ]

    def llm_fn(messages):
        return json.dumps({"items": [
            {
                "id": "D0", "type": "decision", "content": "Đề xuất phương án A",
                "status": "discarded",
                "confidence": 0.7, "confidence_reason": "đề xuất",
                "evidence": [{
                    "quote": "Em đề xuất phương án A, bên X rẻ hơn 20%.",
                    "timestamp": "00:00:42", "speaker": "Nam",
                    "turn": 2, "role_in_discussion": "propose",
                }],
            },
            {
                "id": "D1", "type": "decision", "content": "Chốt phương án B",
                "status": "final", "decided_by": "Lan",
                "reason": "A rủi ro vượt 30%", "supersedes": ["D0"],
                "objections": [], "confidence": 0.9,
                "confidence_reason": "chốt rõ",
                "evidence": [{
                    "quote": "Vậy chốt B nhé, cả team đồng ý không?",
                    "timestamp": "00:45:30", "speaker": "Lan",
                    "turn": 3, "role_in_discussion": "decide",
                }],
            },
            {
                "id": "T1", "type": "task",
                "what": "Gửi báo giá B cho khách",
                "owner": "Nam", "owner_source": "explicit",
                "due": "2026-10-12", "due_source": "explicit",
                "due_hint": None, "link_to_decision": "D1",
                "confidence": 0.85, "confidence_reason": "rõ",
                "evidence": [{
                    "quote": "Dạ em gửi báo giá B cho khách trước 12/10.",
                    "timestamp": "00:46:05", "speaker": "Nam",
                    "turn": 4, "role_in_discussion": "confirm",
                }],
            },
        ]})

    result = extract(meta, turns, llm_fn=llm_fn)

    assert len(result["items"]) == 3
    ids = {i["id"] for i in result["items"]}
    assert ids == {"D0", "D1", "T1"}
    assert result["conf_llm_map"]["D0"] == pytest.approx(0.7)
    assert result["conf_llm_map"]["D1"] == pytest.approx(0.9)
    assert result["conf_llm_map"]["T1"] == pytest.approx(0.85)
    assert result["known_limitations"] == []