# Pictr Storyboard Agent

> **Tubi Take-Home MVP** — Generate a 30-second commercial storyboard from a creative brief, with per-shot iterative approval and regeneration.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Quickstart](#quickstart)
5. [Running the Frontend](#running-the-frontend)
6. [End-to-End Demo](#end-to-end-demo)
7. [API Reference](#api-reference)
8. [Running Tests](#running-tests)
9. [Linting & Formatting](#linting--formatting)
10. [Configuration](#configuration)
11. [Design Decisions](#design-decisions)

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
│   │   ├── main.py         # FastAPI app, routes, middleware
│   │   ├── models.py       # Pydantic domain models (Session, Brief, Shot)
│   │   ├── store.py        # Thread-safe in-memory session store
│   │   ├── agent.py        # StoryboardAgent orchestration
│   │   ├── tools.py        # Tool functions (shot planning, card generation)
│   │   ├── image_client.py # Vertex AI Imagen wrapper (stub fallback)
│   │   └── config.py       # Settings loaded from environment
│   └── tests/
│       ├── conftest.py     # Shared fixtures (isolated TestClient)
│       ├── test_health.py
│       ├── test_sessions.py
│       ├── test_workflow.py
│       └── test_image_client.py
├── frontend/
│   ├── src/
│   │   ├── types.ts        # TS mirrors of backend Pydantic models
│   │   ├── api.ts          # fetch() wrappers for all endpoints
│   │   ├── styles.css      # Dark Tubi-inspired theme (CSS variables)
│   │   ├── main.tsx        # Vite entry point
│   │   ├── App.tsx         # Layout shell + state root
│   │   └── components/
│   │       ├── SessionControls.tsx
│   │       ├── BriefForm.tsx
│   │       ├── ShotList.tsx
│   │       ├── ShotCard.tsx
│   │       └── Toast.tsx
│   ├── .env.example        # VITE_API_BASE_URL=http://localhost:8000
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── .env.example            # Backend env vars — copy to .env
├── .gitignore
├── LICENSE                 # MIT
├── Makefile
├── pyproject.toml          # Dependencies + ruff/black/pytest config
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

## Running the Frontend

### Prerequisites

- Node.js 18+ and npm

### Setup

```bash
cd frontend
cp .env.example .env    # defaults to http://localhost:8000
npm install
npm run dev             # Vite dev server at http://localhost:5173
```

Production build:

```bash
npm run build           # output in frontend/dist/
```

---

## End-to-End Demo

Run both servers simultaneously:

```bash
# Terminal 1 — backend
make dev               # FastAPI on http://localhost:8000

# Terminal 2 — frontend
cd frontend && npm run dev   # Vite on http://localhost:5173
```

Then open **http://localhost:5173** and follow these steps:

1. **Create a session** — Click "New Session". The session ID appears in the left panel and is persisted in `localStorage` so a page refresh restores it.
2. **Submit the brief** — Fill in brand name, product, audience, tone, platform, and duration, then click "Submit Brief". The shot list appears on the left.
3. **Generate Shot 1** — Click "⚡ Generate Shot 1". The shot card updates with an image placeholder (or a real Imagen image if GCP is configured), dialogue, SFX notes, and camera notes.
4. **Approve or revise** — Click "✓ Approve" to move to the next shot, or "✎ Revise" to enter feedback and regenerate.
5. **Repeat** until all shots are approved. A completion banner confirms the storyboard is done.

> **Stub mode** (no GCP): images are deterministic picsum.photos placeholders — no API key needed for a full demo run.

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

67 tests pass; 1 integration test is skipped unless `RUN_IMAGE_TESTS=1`.

```bash
RUN_IMAGE_TESTS=1 pytest backend/tests/test_image_client.py -k integration
```

### What's tested

| Test file | Coverage |
|---|---|
| `test_health.py` | `/health` and `/echo` endpoints |
| `test_sessions.py` | Session create/get, deep-copy isolation, error shapes |
| `test_workflow.py` | Full brief → generate → approve → revise cycle, all phase and status gates |
| `test_image_client.py` | Stub mode, base64 output, error classification, shot failure handling |

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

All backend configuration is via environment variables (or `.env` file):

| Variable | Default | Description |
|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated CORS origins |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `GOOGLE_CLOUD_PROJECT` | *(empty)* | GCP project for Vertex AI Imagen — leave empty for stub mode |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex AI region |
| `IMAGE_MODEL` | `imagen-3.0-generate-001` | Imagen model identifier |

Frontend configuration (`frontend/.env`):

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |

---

## Design Decisions

**Why threading.Lock and not asyncio.Lock?**
FastAPI with a single Uvicorn worker uses an event loop for async handlers, but the store may also be accessed from background threads in the future.  A `threading.Lock` is safe in both contexts and avoids the footgun of mixing sync/async locking primitives.

**Why return deep copies from the store?**
Returning a reference to the internal dict value would allow callers to silently corrupt stored state.  Deep copies make the isolation contract explicit and testable.

**Why a stub for image generation?**
`ImageClient` uses picsum.photos with a deterministic seed when `GOOGLE_CLOUD_PROJECT` is unset, so the full pipeline (intake → shot list → card generation → approval gate) can be exercised without a live API key.  Setting `GOOGLE_CLOUD_PROJECT` transparently switches to real Vertex AI Imagen with no other code changes.

**Why not use a global `app` dependency for the store?**
FastAPI's `Depends()` machinery is clean but adds boilerplate for a one-module MVP.  The module-level store singleton is simpler and the tests replace it via targeted monkey-patching.  If the project grows, switching to `Depends(get_store)` is straightforward.
