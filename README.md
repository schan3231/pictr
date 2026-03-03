# Pictr Storyboard Agent

> **Tubi Take-Home MVP** — Generate a 30-second commercial storyboard from a creative brief, with per-shot iterative approval and regeneration.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Quickstart](#quickstart)
5. [API Reference](#api-reference)
6. [Running Tests](#running-tests)
7. [Linting & Formatting](#linting--formatting)
8. [Configuration](#configuration)
9. [Design Decisions](#design-decisions)
10. [Roadmap (Tomorrow)](#roadmap-tomorrow)

---

## Overview

Pictr lets a user describe an advertising brief (brand, product, audience, tone) and then iteratively builds a storyboard — one shot card at a time.  Each Shot Card is an atomic unit containing:

- Generated image (`image_url`)
- Example voiceover / dialogue (`dialogue_text`)
- Sound-effects guidance (`sfx_notes`)
- Camera motion notes (`camera_notes`)

The user reviews each shot and either **approves** it or **requests changes**; the agent cannot advance to the next shot until the current one is approved (sequential gating).

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Browser / CLI (dumb client)                             │
│  Sends briefs, approvals, feedback via REST              │
└────────────────────┬─────────────────────────────────────┘
                     │  HTTP (JSON)
┌────────────────────▼─────────────────────────────────────┐
│  FastAPI  (backend/app/main.py)                          │
│  • /health  /echo  /session  /session/{id}               │
│  • Input validation via Pydantic                         │
│  • Consistent error payloads; no stack traces exposed    │
└────┬──────────────────────┬───────────────────────────────┘
     │                      │
     ▼                      ▼
┌─────────────┐    ┌──────────────────────────────────────┐
│ SessionStore│    │  StoryboardAgent  (agent.py)         │
│ (store.py)  │    │  • Owns workflow phase transitions   │
│ thread-safe │◄───│  • Enforces sequential shot gating   │
│ in-memory   │    │  • Calls tool functions              │
│ dict+Lock   │    └──────────────┬───────────────────────┘
└─────────────┘                   │
                                  ▼
                    ┌─────────────────────────────┐
                    │  Tools  (tools.py)           │
                    │  • plan_shot_list()          │
                    │  • generate_shot_card() ←stub│
                    │  Pure functions; no I/O      │
                    └─────────────────────────────┘
```

**Key boundary rules:**

| Layer | Responsibility |
|---|---|
| `main.py` | HTTP request/response, auth (future), CORS |
| `agent.py` | Workflow logic, phase enforcement, orchestration |
| `tools.py` | Deterministic computation — no session state |
| `store.py` | Persistence — swap to Redis/DB without touching other layers |
| `models.py` | Shared types — imported by all layers |

---

## Project Structure

```
pictr/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py        # FastAPI app, routes, middleware
│   │   ├── models.py      # Pydantic domain models (Session, Brief, Shot)
│   │   ├── store.py       # Thread-safe in-memory session store
│   │   ├── agent.py       # StoryboardAgent orchestration
│   │   ├── tools.py       # Tool functions (shot planning, card generation)
│   │   └── config.py      # Settings loaded from environment
│   └── tests/
│       ├── conftest.py    # Shared fixtures (isolated TestClient)
│       ├── test_health.py
│       └── test_sessions.py
├── .env.example           # Copy to .env — never commit real values
├── .gitignore
├── LICENSE                # MIT
├── Makefile
├── pyproject.toml         # Dependencies + ruff/black/mypy/pytest config
├── README.md
└── SECURITY.md
```

---

## Quickstart

### Prerequisites

- Python 3.11+

### 1. Clone and set up environment

```bash
git clone <repo-url>
cd pictr

# Create and activate virtualenv
python3.11 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install (includes dev dependencies)
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if you need non-default CORS origins
```

### 3. Run the server

```bash
make dev
# or directly:
uvicorn backend.app.main:app --reload
```

Server starts at **http://localhost:8000**

Swagger UI: **http://localhost:8000/docs**

### 4. Quick smoke test

```bash
curl http://localhost:8000/health
# {"ok":true}

curl -s -X POST http://localhost:8000/session | python3 -m json.tool
# Returns a Session object with a fresh session_id
```

---

## API Reference

### Meta

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe — returns `{"ok": true}` |
| `POST` | `/echo` | Returns the request body unchanged (debug helper) |

### Sessions

| Method | Path | Description |
|---|---|---|
| `POST` | `/session` | Create a new session in INTAKE phase |
| `GET` | `/session/{session_id}` | Retrieve session state |

**Session object shape:**

```json
{
  "session_id": "uuid4",
  "phase": "INTAKE",
  "brief": null,
  "shots": [],
  "current_shot_index": 0,
  "created_at": "2026-03-03T00:00:00+00:00",
  "updated_at": "2026-03-03T00:00:00+00:00"
}
```

**Error response shape (all endpoints):**

```json
{ "detail": "Human-readable error message" }
```

---

## Running Tests

```bash
make test
# or:
pytest backend/tests/ -v
```

All 20 tests should pass in < 1 second.

### What's tested

| Test file | Coverage |
|---|---|
| `test_health.py` | `/health` returns `ok`, `/echo` round-trips payload, bad JSON → 400 |
| `test_sessions.py` | Create returns 201 + valid UUID4 + phase=INTAKE; GET returns same state; 404 on unknown ID; consistent error shape; store isolation (deep copy) |

---

## Linting & Formatting

```bash
make lint    # ruff check
make format  # black format check
```

Or auto-fix:

```bash
ruff check --fix backend/
black backend/
```

---

## Configuration

All configuration is via environment variables (or `.env` file):

| Variable | Default | Description |
|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated CORS origins |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## Design Decisions

**Why threading.Lock and not asyncio.Lock?**
FastAPI with a single Uvicorn worker uses an event loop for async handlers, but the store may also be accessed from background threads in the future.  A `threading.Lock` is safe in both contexts and avoids the footgun of mixing sync/async locking primitives.

**Why return deep copies from the store?**
Returning a reference to the internal dict value would allow callers to silently corrupt stored state.  Deep copies make the isolation contract explicit and testable.

**Why a stub for image generation?**
The stub (`tools.py: _stub_image_url`) uses picsum.photos with a deterministic seed, so demos are reproducible and the full pipeline (intake → shot list → card generation → approval gate) can be exercised without a live API key.  Swapping to a real provider requires changing only the body of `generate_shot_card`.

**Why not use a global `app` dependency for the store?**
FastAPI's `Depends()` machinery is clean but adds boilerplate for a one-module MVP.  The module-level store singleton is simpler and the tests replace it via targeted monkey-patching.  If the project grows, switching to `Depends(get_store)` is straightforward.

---

## Roadmap (Tomorrow)

- [ ] `POST /session/{session_id}/message` — agent processes user messages (submit brief, chat)
- [ ] `POST /session/{session_id}/shot/{index}/generate` — trigger shot generation
- [ ] `POST /session/{session_id}/shot/{index}/approve`
- [ ] `POST /session/{session_id}/shot/{index}/revise` — attach feedback + queue regeneration
- [ ] Wire real ADK agent runner (replace hand-rolled orchestrator)
- [ ] Minimal React UI (brief form → storyboard view with per-shot approval)
- [ ] Real image generation (Gemini Imagen or equivalent)
