<div align="center">

# meet2note

**Turn raw meeting transcripts into actionable, verifiable state** — final decisions, owned tasks with deadlines, and blockers — backed by verbatim evidence linked to every turn.

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)](backend/api.py)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](frontend/)
[![Postgres 16](https://img.shields.io/badge/Postgres-16-336791?logo=postgresql)](docker-compose.yml)
[![Ollama](https://img.shields.io/badge/LLM-Ollama%20local-black)](docs/runbook/local-dev.md)
[![Tests](https://img.shields.io/badge/tests-287%20passed-brightgreen)](tests/)

*Core philosophy: **LLM proposes, deterministic code verifies, human confirms.***

</div>

---

## The Problem

A 60-minute meeting usually produces only 3–5 final decisions and 5–8 tasks — yet manual notes or naive AI summaries fail in three costly ways:

| Pain Point | Impact |
|---|---|
| **Drifting / Reversed Decisions** — Option A is proposed early, Option B is finalized at the end, but summaries list both equally | Teams implement the wrong decision (Option A), costing 10–50× more to fix later |
| **Orphaned Tasks** — *"let's roll this out soon"*, *"someone check this"* | Missing owner or deadline causes action items to fall through the cracks |
| **Lost Context & Rationale** — Why did we switch from A to B? Who raised objections? | Institutional knowledge disappears when team members leave |

## The Solution

A 4-step workflow completed in under 5 minutes:

```
Upload transcript → AI extracts state → 2-minute human review → Export minutes.md + Jira CSV
```

- **State, not summary**: Extracts 6 structured item types (`Decision`, `Task`, `Blocker`, `Requirement`, `Open Issue`, `Knowledge`) instead of prose paragraphs.
- **Evidence-first**: Every item links directly to verbatim quotes, timestamps, and speakers in the transcript.
- **Human-in-the-loop Gate (R6)**: Export is locked both in the UI and backend API until all low-confidence (`🔴 < 0.50`) items are resolved.
- **Honest by default**: Missing owners or ambiguous dates are explicitly marked as `TBD` with `known_limitations` — never hallucinated.

<p align="center">
  <img src="docs/images/demo.png" alt="meet2note review UI" width="800" />
  <br /><em>Review Workspace: 4-column Kanban + confidence badges + interactive state graph + transcript drawer</em>
</p>

## Key Features

| # | Feature | Description |
|---|---|---|
| 1 | **Multi-format Ingestion** | Upload `.txt`, `.srt`, or `.docx` transcripts → run the extraction pipeline via local Ollama or OpenAI-compatible endpoints |
| 2 | **2-Minute Review Workspace** | 4-column Kanban board, confidence badges (`🔴 <0.50` / `🟡 0.50–0.75` / `🟢 ≥0.75`), 1-click batch green approval, and keyboard navigation (`j/k/a/e/x`) |
| 3 | **Interactive State Graph** | Bi-directional navigation between Decisions (`D1`), linked Tasks (`T1`), and Meeting Brief outcome references |
| 4 | **Verbatim Evidence Drawer** | Click any `[HH:MM:SS]` timestamp to inspect `±4` surrounding turns or search the full meeting transcript |
| 5 | **Decision Reversal Tracking (`A → B → A`)** | Preserves `supersedes` history and `discarded` proposals; flags unresolved reversals (`unresolved_reversal`) for host arbitration |
| 6 | **Deterministic M3 Gates (`gates.py`)** | 3-condition Decision Gate (M3-A), Hedge Lexicon Gate (M3-B), Evidence-Chain Penalty (M3-C), Task ↔ Knowledge Reclassification (M3-D), and Mid-Meeting Due/Owner Revision tracking (CR) |
| 7 | **Export Gate (R6) & Download** | Blocks export while red items remain; generates `minutes.md` and `tasks_jira.csv` for direct download |
| 8 | **Multi-User Isolation** | JWT authentication (60m access token + 7d `httpOnly` refresh cookie) with strict per-owner meeting isolation |

## Example: Input → Output

**Input** (`[00:10:12] Nam: I propose Option A` … `[00:45:30] Lan: Option A has a 30% cost overrun risk, let's finalize Option B`):

```markdown
## Decisions
- ✅ **Finalize Option B** (replaces Option A) — decided by: Lan
  supersedes: D0 · evidence: [00:45:30] Lan · confidence: 0.90 🟢

## Tasks
- [ ] Nam: Send Option B quotation to client by 2026-10-12 → linked to Decision D1
```

## Tech Stack

| Layer | Technology |
|---|---|
| Core Pipeline | Python 3.11, Pydantic v2, deterministic verification rules R1–R8 + M3 gates |
| LLM Integration | Ollama local (`qwen3:4b-instruct-2507-q4_K_M`) or OpenAI-compatible API, JSON mode + constrained decoding |
| Backend API | FastAPI, JWT HS256 + rotating refresh tokens, SQLAlchemy 2.0 + Alembic |
| Database | PostgreSQL 16 (Docker, host port `5434`) for metadata & auth; versioned state artifacts on disk (`runs/`) |
| Frontend UI | React 18, Vite, Tailwind CSS v4, Radix UI / shadcn components |

## Quick Start

```powershell
# Prerequisites: Python 3.11+, Node 18+, Docker, Ollama + qwen3:4b-instruct-2507-q4_K_M
cd meet2note
# On Windows use .\.venv\Scripts\python.exe; on Linux/macOS use .venv/bin/python

Copy-Item .env.example .env   # Configure LLM_BASE_URL, LLM_MODEL, JWT_SECRET
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

docker compose up -d db
.\.venv\Scripts\python.exe -m backend.db_cli migrate
.\.venv\Scripts\python.exe -m backend.db_cli create-admin --email <email> --password <password-8+chars>

# Run in 2 separate terminals:
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --port 8000
cd frontend; npm install; npm run dev     # http://localhost:5173
```

Log in → Upload a transcript → Review items → Export → Download files. See [`docs/runbook/local-dev.md`](docs/runbook/local-dev.md) for detailed instructions.

## Configuration (`.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_BASE_URL` | ✓ | `http://localhost:11434/v1` | OpenAI-compatible endpoint (local Ollama) |
| `LLM_MODEL` | ✓ | `qwen3:4b-instruct-2507-q4_K_M` | Extraction model name |
| `LLM_TIMEOUT` / `LLM_NUM_CTX` / `LLM_JSON_MODE` | – | `300` / `8192` / `1` | Request timeout, context window, and JSON mode enforcement |
| `JWT_SECRET` | ✓ (API) | – | Random secret string (≥32 chars, **never commit**) |
| `DATABASE_URL` | – | `…@localhost:5434/meet2note` | PostgreSQL connection URL |

## API Overview

Full specification: [`docs/spec/api-contract.md`](docs/spec/api-contract.md).

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` · `/auth/login` · `/auth/refresh` · `/auth/logout` | Public / Cookie | Account & session lifecycle |
| `GET` | `/auth/me` | Bearer | Current authenticated user profile |
| `GET` | `/api/v1/meetings` | Bearer | List meetings owned by the current user |
| `GET` / `PUT` | `/api/v1/review?meeting=` | Bearer + Owner | Load state / confirm review changes (+ audit log) |
| `POST` | `/api/v1/export?meeting=` | Bearer + Owner | Enforce Gate R6 → generate `minutes.md` & `tasks_jira.csv` |
| `GET` | `/api/v1/export/file?meeting=&name=` | Bearer + Owner | Download exported `minutes.md` or `tasks_jira.csv` |
| `GET` | `/api/v1/transcript?meeting=` | Bearer + Owner | Fetch parsed transcript turns for the evidence drawer |
| `POST` | `/api/v1/meetings/upload` | Bearer | Upload transcript + run pipeline + persist metadata |

## Evaluation & Test Suite

6 synthetic Vietnamese test cases (`data/transcripts/` + `data/golden/`), documented in [`eval/report.md`](eval/report.md):

| Case | Scenario | Expected Outcome |
|---|---|---|
| **tc1** Sprint Planning | Clear decision + false-decision noise (*"let's finalize lunch"*) | Correct `D.final` & decider, 3 tasks with owner+due, joke decision filtered out |
| **tc2** A→B Reversal ⭐ | Core kill-criterion: Option A proposed early, Option B finalized late | `D1.final=B`, `supersedes=[D0]`, `D0=discarded`, task linked to `D1` |
| **tc3** Vague Brainstorm | No final decision + retracted false proposal (*"let's just pick Stripe"*) | `no_decision=true`, Open Issues with `next_step`, zero hallucinated Decisions |
| **tc4** Entity-Linking | Pronouns + relative dates (*"next Friday"*, *"end of month"*) | Resolved canonical owners & deterministic ISO dates; unparseable dates → `TBD` |
| **tc5** A→B→A Conflict | Unresolved multi-way reversal & sarcasm | Flags `unresolved_reversal` + creates host Open Issue — prioritizes honesty |
| **tc6** Long Multi-Topic (M3) | ~110 turns: retracted proposal + hedges + deadline revisions (`16→21/10`) + long-term policy | `false_final=0`, latest revised due date preserved with audit trail, policy reclassified to `Knowledge` |

```powershell
.\.venv\Scripts\python.exe -m pipeline.cli eval --cases tc1,tc2,tc3,tc4,tc5,tc6  # Deterministic fixture eval → 6/6 PASS
.\.venv\Scripts\python.exe -m pipeline.cli eval --live                           # Live LLM eval → 5/5 PASS
.\.venv\Scripts\python.exe -m pytest tests -q                                    # 287 passed, 1 skipped
cd frontend; npm run build                                                       # Verify production UI bundle
```

## Repository Structure

```
pipeline/   ingest → extract → resolve (+ M3 gates) → verify → export → service → cli (standalone core)
backend/    api.py (thin FastAPI adapter) · auth.py (JWT) · db/ (models/session) · db_cli.py (migrate/seed/sync)
frontend/   React Review Workspace (4-column Kanban + brief + transcript drawer + upload + auth)
prompts/    system_extract / resolve / brief + fewshot templates (decoupled from code)
data/       transcripts/ meta/ golden/ — strictly synthetic datasets for public repo
eval/       runner.py + report.md + results_fixture/live/tc6_*.json
tests/      pytest suite running against isolated temporary SQLite databases
docs/       c4/ (architecture) · adr/ (decisions) · spec/ (contracts) · runbook/ · slides/ · images/
runs/       versioned pipeline outputs — gitignored
```

## Roadmap

- [x] P0–P4: Core pipeline + FastAPI adapter + React review UI + 5-case evaluation
- [x] P5: Transcript upload (`.txt` / `.srt` / `.docx`) + interactive transcript viewer
- [x] P6: PostgreSQL metadata persistence + JWT multi-user auth + owner isolation
- [x] Mission 3 (M3): 3-condition Decision Gate + Hedge Gate + Evidence-Chain penalty + Task↔Knowledge reclassification + Due/Owner revision tracking (`tc6_long`)
- [x] UI/UX Redesign: Split-screen hero login, 1-click demo access, batch green approval, interactive state graph navigation
- [ ] Real-world Pilot: Measure Decision Accuracy (>95%), Task Usability (>85%), and Time-to-Value (<5 min) across live team meetings
- [ ] Post-MVP: Meeting-type templates, one-way Jira/Slack sync, cross-meeting Decision Search & Q&A, Enterprise SSO + PII redaction

## Known Limitations

- Small local LLMs can paraphrase or vary across runs; deterministic rules R1–R8 and M3 gates catch structural errors and log them in `known_limitations` (see `eval/report.md`).
- The M3-A retraction check scans a `±5` turn window after a decision turn; the Vietnamese hedge lexicon is a fixed rule set (subtle sarcasm still relies on the 2-minute human review).
- Real user transcripts are stored locally under `data/uploads/` (gitignored); `data/` contains only synthetic transcripts.
- Out of scope for MVP: auto-join meeting bots, real-time streaming ASR, audio clip playback, two-way Jira/Slack API sync, and SSO.
