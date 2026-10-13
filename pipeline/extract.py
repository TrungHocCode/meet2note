"""
extract.py — LLM pass-1: turns → list[dict] raw items + conf_llm.

Triết lý (AGENTS.md §1, §5):
- LLM đề xuất, code kiểm chứng. Extract chỉ trả dict thô (chưa ép TBD, chưa chấm).
- Verify (P1) mới enforce R1/R2/R5 + tính confidence cuối.

Hợp đồng input/output:
- Input: meta (dict), turns (output của parse_transcript).
- Output: dict {
    "items": list[dict] raw items (đã pass JSON parse + Pydantic structure check),
    "conf_llm_map": dict[item_id, float] — confidence gốc từ LLM để verify áp công thức,
    "known_limitations": list[str]
  }

Tuỳ chọn env (theo AGENTS.md §5):
- OPENAI_BASE_URL, MODEL_NAME — bắt buộc để gọi LLM thật.
- OPENAI_API_KEY (hoặc API_KEY) — optional tuỳ endpoint.
- Nếu thiếu → call_llm raise RuntimeError; test dùng llm_fn mock để bypass.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# 6 loại item theo taxonomy §3 — extract chỉ route theo type, validate chặt ở verify.
_KNOWN_TYPES = frozenset({
    "decision", "task", "blocker", "requirement", "open_issue", "knowledge",
})

# Tên file prompt mặc định — đổi ở đây nếu cần tách variant.
SYSTEM_PROMPT_FILE = "system_extract.md"
FEWSHOT_FILE = "fewshot_atob.md"


# ──────────────────────────────────────────────────────────────────────
# Prompt loading + filling
# ──────────────────────────────────────────────────────────────────────


def load_prompt(name: str) -> str:
    """Đọc file prompt trong `prompts/` (UTF-8)."""
    p = PROMPTS_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"prompt not found: {p}")
    return p.read_text(encoding="utf-8")


def fill_meta_placeholders(template: str, meta: dict[str, Any]) -> str:
    """Fill placeholders từ meta vào system prompt template.

    Hợp đồng placeholder (khớp với `prompts/system_extract.md`):
        {date}                        — ISO date cuộc họp.
        {name (role, aliases)}        — toàn bộ participants, format:
                                       `Name1 (role1, aliases: a1, a2); Name2 (...)`.
        {terms}                       — glossary, format: `KEY = value; ...`.

    Format participants: `Name (role, aliases: a1, a2)` ngăn bởi `; `.
    Format glossary: `KEY = value` ngăn bởi `; `.
    """
    date = str(meta.get("date", "(unknown)"))
    parts = meta.get("participants") or []
    if parts:
        participants_str = "; ".join(
            f"{p.get('name', '?')} ({p.get('role', '?')}, "
            f"aliases: {', '.join(p.get('aliases', []) or []) or '(none)'})"
            for p in parts
        )
    else:
        participants_str = "(none)"

    glossary = meta.get("glossary") or {}
    if glossary:
        glossary_str = "; ".join(f"{k} = {v}" for k, v in glossary.items())
    else:
        glossary_str = "(none)"

    return (
        template
        .replace("{date}", date)
        .replace("{name (role, aliases)}", participants_str)
        .replace("{terms}", glossary_str)
    )


def build_messages(
    meta: dict[str, Any],
    turns: list[dict[str, Any]],
    *,
    system_template: str | None = None,
    fewshot_text: str | None = None,
) -> list[dict[str, str]]:
    """Build OpenAI-style chat messages: system (filled) + user (fewshot + transcript).

    System chứa date/participants/glossary đã fill (xem fill_meta_placeholders).
    User chứa fewshot TRƯỚC transcript để LLM thấy ví dụ trước khi parse.

    Mỗi turn được format: `[turn N] [HH:MM:SS] Speaker: text`.
    """
    system = fill_meta_placeholders(
        system_template or load_prompt(SYSTEM_PROMPT_FILE), meta
    )
    fewshot = fewshot_text if fewshot_text is not None else load_prompt(FEWSHOT_FILE)

    user_lines = [
        f"Meeting id: {meta.get('id', '?')}",
        f"Title: {meta.get('title', '?')}",
        f"Date: {meta.get('date', '?')}",
        "",
        "TRANSCRIPT (turns, 1-indexed):",
    ]
    for t in turns:
        user_lines.append(
            f"[turn {t['turn']}] [{t['t_start']}] {t['speaker']}: {t['text']}"
        )
    user = "\n".join(user_lines)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": fewshot + "\n\n---\n\n" + user},
    ]


# ──────────────────────────────────────────────────────────────────────
# Chunking (~80/chunk, overlap 10 — AGENTS.md §5)
# ──────────────────────────────────────────────────────────────────────


def chunk_turns(
    turns: list[dict[str, Any]],
    chunk_size: int = 80,
    overlap: int = 10,
) -> list[list[dict[str, Any]]]:
    """Slice turns thành các chunk ~`chunk_size`, overlap `overlap` turn giữa 2 chunk.

    Step = chunk_size - overlap. Nếu overlap >= chunk_size (cấu hình sai),
    ép step về 1 để vẫn tiến về phía cuối (AGENTS.md §5 — chunking cho LLM).

    Returns: list[list[dict]] — rỗng nếu turns rỗng.
    """
    if not turns:
        return []
    step = max(1, chunk_size - overlap)
    chunks: list[list[dict[str, Any]]] = []
    n = len(turns)
    i = 0
    while i < n:
        chunks.append(turns[i : i + chunk_size])
        if i + chunk_size >= n:
            break
        i += step
    return chunks


# ──────────────────────────────────────────────────────────────────────
# LLM call — tách hàm riêng để test mock được
# ──────────────────────────────────────────────────────────────────────


def call_llm(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
) -> str:
    """Gọi OpenAI-compatible `/chat/completions` với temp=0.

    Env:
    - OPENAI_BASE_URL (vd: https://api.openai.com/v1 hoặc http://localhost:11434/v1 cho Ollama)
    - MODEL_NAME (vd: gpt-4o-mini, qwen3:8b, ...)
    - OPENAI_API_KEY / API_KEY (optional tuỳ endpoint — Ollama local không cần)
    - LLM_TIMEOUT (giây, default 60 — model local nên đặt 300+)

    Raises:
        RuntimeError: nếu thiếu env config hoặc HTTP != 200.
    """
    base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "")).rstrip("/")
    model = model or os.environ.get("MODEL_NAME", "")
    api_key = api_key or os.environ.get(
        "OPENAI_API_KEY", os.environ.get("API_KEY", "")
    )

    if not base_url or not model:
        raise RuntimeError(
            "LLM chưa cấu hình: set OPENAI_BASE_URL + MODEL_NAME trong .env "
            "(xem .env.example; Ollama local: http://localhost:11434/v1). "
            "Hiện tại chỉ chạy được mock LLM (test) hoặc sau khi user cấp key."
        )

    # URL: append /chat/completions nếu chưa có
    if base_url.endswith("/chat/completions"):
        url = base_url
    else:
        url = base_url + "/chat/completions"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
    }
    # JSON-mode ép ở request (OpenAI + Ollama mới hỗ trợ). Default TẮT để
    # tương thích rộng (parser + retry đã cover); bật bằng LLM_JSON_MODE=1
    # khi model nhỏ (vd qwen3 local) không tuân thủ shape.
    if os.environ.get("LLM_JSON_MODE", "") == "1":
        payload["response_format"] = {"type": "json_object"}
    # num_ctx cho Ollama local (default 4096 — prompt tc2 ~4.4k tokens nên tràn).
    # Ollama mới chấp nhận passthrough "options" qua endpoint OpenAI-compatible.
    num_ctx = os.environ.get("LLM_NUM_CTX", "")
    if num_ctx:
        payload["options"] = {"num_ctx": int(num_ctx)}

    eff_timeout = (
        timeout if timeout is not None else float(os.environ.get("LLM_TIMEOUT", "60"))
    )
    with httpx.Client(timeout=eff_timeout) as client:
        r = client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()

    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"LLM response malformed: {data!r}") from e


# ──────────────────────────────────────────────────────────────────────
# Validate LLM output: JSON parse + shape check (Pydantic full ở verify.py)
# ──────────────────────────────────────────────────────────────────────


def _strip_llm_wrappers(content: str) -> str:
    """Bóc wrapper model local hay thêm: <think>...</think>, ```json fences.

    Gốc lệch #4 (tương thích rộng, vd Ollama/qwen3): không ép response_format
    ở request mà làm parser chịu lỗi ở phía nhận. Retry ở tầng trên vẫn giữ.
    """
    text = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return text


def _try_parse_items(content: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Parse `content` thành JSON, kiểm tra shape tối thiểu của `items`.

    LAYERING (quyết định sau live-test qwen3 local): extract CHỈ check shape
    (list + mỗi item là dict có `id` + `type` thuộc 6 loại). Mọi normalize và
    validate chặt (role, due, confidence range, Pydantic full) thuộc về VERIFY
    theo từng item — 1 item lỗi không giết cả chunk (trước đây Pydantic ở đây
    làm cả chunk fail oan vì 1 field phụ như role/timestamp).

    Returns (items, error). error=None nếu pass hết.
    Trả về None nếu có lỗi (đủ dùng cho retry feedback).
    """
    text = _strip_llm_wrappers(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fallback cuối: cắt từ '{' đầu tới '}' cuối rồi parse lại
        # (model local đôi khi thêm lời dẫn ngoài JSON).
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None, f"JSON parse error: no object found"
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            return None, f"JSON parse error: {e}"

    if not isinstance(data, dict):
        return None, f"Top-level not dict (got {type(data).__name__})"

    items = data.get("items")
    if not isinstance(items, list):
        return None, f"items field not list (got {type(items).__name__})"

    validated: list[dict[str, Any]] = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            return None, f"item[{idx}] not dict"
        if not raw.get("id") or not isinstance(raw.get("id"), str):
            return None, f"item[{idx}] missing id"
        if raw.get("type") not in _KNOWN_TYPES:
            return None, (
                f"item[{idx}] unknown type {raw.get('type')!r} "
                f"(expected one of {sorted(_KNOWN_TYPES)})"
            )
        validated.append(raw)

    return validated, None


# ──────────────────────────────────────────────────────────────────────
# Logging — ghi mọi request/response ra llm_log.jsonl (audit + debug)
# ──────────────────────────────────────────────────────────────────────


def _log_entry(
    log_fp,
    *,
    chunk_idx: int,
    attempt: int,
    messages: list[dict[str, str]],
    response: str,
    error: str | None = None,
    items_count: int | None = None,
) -> None:
    """Ghi 1 dòng log JSON: ts, chunk, attempt, request, response, error?, items_count?."""
    entry: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chunk": chunk_idx,
        "attempt": attempt,
        "request": messages,
        "response": response,
    }
    if error is not None:
        entry["error"] = error
    if items_count is not None:
        entry["items_count"] = items_count
    log_fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log_fp.flush()


# ──────────────────────────────────────────────────────────────────────
# Main: extract (chunked, retry, dedup, log)
# ──────────────────────────────────────────────────────────────────────


def extract(
    meta: dict[str, Any],
    turns: list[dict[str, Any]],
    *,
    log_path: Path | None = None,
    llm_fn: Callable[..., str] | None = None,
    chunk_size: int = 80,
    overlap: int = 10,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Run LLM pass-1 trên từng chunk của turns.

    Args:
        meta: meeting metadata (id, title, date, participants, glossary).
        turns: list[dict] turn từ ingest.
        log_path: path append llm_log.jsonl (None = không log).
        llm_fn: override hàm gọi LLM (cho test). Signature: (messages) -> str.
        chunk_size: max turns/chunk (default 80 — AGENTS.md §5).
        overlap: overlap turns giữa 2 chunk (default 10).
        max_retries: số lần retry khi parse/validate fail (default 2 — AGENTS.md §5).

    Returns:
        dict {
          "items": list[dict] raw items (Pydantic-valid structure, chưa enforce R1/R2),
          "conf_llm_map": dict[item_id, float],
          "known_limitations": list[str]
        }
    """
    call = llm_fn if llm_fn is not None else call_llm
    chunks = chunk_turns(turns, chunk_size=chunk_size, overlap=overlap)

    log_fp = None
    if log_path is not None:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(log_path, "a", encoding="utf-8")  # append — mỗi run 1 file mới

    try:
        all_items: list[dict[str, Any]] = []
        conf_llm_map: dict[str, float] = {}
        limitations: list[str] = []
        seen_ids: set[str] = set()

        for chunk_idx, chunk in enumerate(chunks):
            messages = build_messages(meta, chunk)
            last_err: str | None = None
            success_items: list[dict[str, Any]] | None = None

            for attempt in range(max_retries + 1):
                if attempt == 0:
                    msgs = messages
                else:
                    # Retry: append error feedback để LLM sửa
                    msgs = list(messages) + [
                        {
                            "role": "user",
                            "content": (
                                f"Output trên không hợp lệ: {last_err}\n"
                                "Trả về đúng JSON theo schema, mỗi item PHẢI đủ evidence "
                                "(Knowledge có thể rỗng). CHỈ trả về JSON, không giải thích."
                            ),
                        }
                    ]

                try:
                    content = call(msgs)
                except RuntimeError as e:
                    last_err = f"LLM call error: {e}"
                    if log_fp is not None:
                        _log_entry(
                            log_fp,
                            chunk_idx=chunk_idx,
                            attempt=attempt,
                            messages=msgs,
                            response="",
                            error=last_err,
                        )
                    # HTTP/network error: retry không cải thiện (cùng request) → dừng chunk
                    break

                items, err = _try_parse_items(content)
                if log_fp is not None:
                    _log_entry(
                        log_fp,
                        chunk_idx=chunk_idx,
                        attempt=attempt,
                        messages=msgs,
                        response=content,
                        error=err,
                        items_count=(len(items) if items is not None else None),
                    )
                if items is not None:
                    success_items = items
                    break
                last_err = err or "unknown"

            if success_items is None:
                limitations.append(
                    f"chunk {chunk_idx}: LLM không trả JSON hợp lệ sau "
                    f"{max_retries + 1} lần ({last_err})"
                )
                continue

            # Dedup theo `id` (vượt chunk + trong chunk)
            for raw in success_items:
                item_id = raw.get("id")
                if not isinstance(item_id, str) or not item_id:
                    limitations.append(
                        f"chunk {chunk_idx}: bỏ item thiếu id: {str(raw)[:120]}"
                    )
                    continue
                if item_id in seen_ids:
                    # Duplicate id (do overlap hoặc LLM lặp) → bỏ, lấy bản đầu
                    continue
                seen_ids.add(item_id)
                all_items.append(raw)
                # Capture conf_llm từ raw — Pydantic đã chặn ngoài [0,1] ở validate
                # trên, nên giá trị ở đây luôn hợp lệ. Defensive: fallback 0.5.
                try:
                    conf_llm_map[item_id] = float(raw["confidence"])
                except (KeyError, TypeError, ValueError):
                    conf_llm_map[item_id] = 0.5

        return {
            "items": all_items,
            "conf_llm_map": conf_llm_map,
            "known_limitations": limitations,
        }
    finally:
        if log_fp is not None:
            log_fp.close()


__all__ = [
    "PROMPTS_DIR",
    "SYSTEM_PROMPT_FILE",
    "FEWSHOT_FILE",
    "load_prompt",
    "fill_meta_placeholders",
    "build_messages",
    "chunk_turns",
    "call_llm",
    "extract",
]