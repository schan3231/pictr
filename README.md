# Pictr Storyboard Agent

> **Tubi Take-Home MVP** — Generate a 30-second commercial storyboard from a creative brief, with AI-assisted planning and per-shot iterative approval.

---

## Table of Contents

1. [Overview](#overview)
2. [Workflow](#workflow)
3. [Planning Phase (Gemini)](#planning-phase-gemini)
4. [Storyboard Phase (Imagen)](#storyboard-phase-imagen)
5. [Architecture](#architecture)
6. [Project Structure](#project-structure)
7. [Quickstart](#quickstart)
8. [Running the Frontend](#running-the-frontend)
9. [End-to-End Demo](#end-to-end-demo)
10. [API Reference](#api-reference)
11. [Running Tests](#running-tests)
12. [Linting & Formatting](#linting--formatting)
13. [Configuration](#configuration)
14. [Vertex AI Setup](#vertex-ai-setup)
15. [Optional: Firestore Persistence](#optional-firestore-persistence)
16. [Troubleshooting](#troubleshooting)
17. [Design Decisions](#design-decisions)

---

## Overview

Pictr lets a user describe an advertising brief (brand, product, audience, tone) and then iteratively builds a storyboard — one shot card at a time.  Each Shot Card is an atomic unit containing:

- Generated image (`image_url`)
- Example voiceover / dialogue (`dialogue_text`)
- Sound-effects guidance (`sfx_notes`)
- Camera motion notes (`camera_notes`)

The user reviews each shot and either **approves** it or **requests changes**; the agent cannot advance to the next shot until the current one is approved (sequential gating).

---

## Workflow

```
INTAKE ──► PLANNING ──► STORYBOARD
  │            │              │
  │   Submit   │  Chat with   │  Generate,
  │   Brief    │  AI planner, │  approve, or
  │            │  generate &  │  revise each
  │            │  approve     │  shot in order
  │            │  plan        │
  ▼            ▼              ▼
Brief       Draft plan     Shot cards
collected   reviewed       produced
```

The three phases are enforced server-side and the frontend mirrors the current phase automatically:

| Phase | What happens |
|---|---|
| **INTAKE** | User fills in the creative brief |
| **PLANNING** | User chats with the AI creative director (Gemini), generates a storyboard plan, and approves it |
| **STORYBOARD** | System creates shot placeholders from the plan; user generates, approves, or revises each shot sequentially (Imagen) |

---

## Planning Phase (Gemini)

After submitting the brief, the session enters the **PLANNING** phase:

1. **Chat** — An AI creative director (powered by Gemini) is pre-seeded with the brief. The user can ask questions, share ideas, or describe the mood they want. The conversation guides the final plan.
2. **Generate Plan** — When the user is satisfied, they click "Generate Storyboard Plan". Gemini produces a structured `StoryboardPlan` with:
   - Title and logline
   - Narrative beats (e.g., Hook → Problem → Solution → CTA)
   - Per-shot intent: title, purpose, visual description, camera hints, dialogue hints, and an `image_prompt` used later by Imagen
3. **Review** — The plan is displayed in the UI as a draft. The user can continue chatting and regenerate if needed.
4. **Approve Plan** — Approving locks the plan and creates shot placeholder records. The session transitions to `STORYBOARD`.

> The `image_prompt` field in each planned shot is passed directly to Imagen during shot generation, resulting in higher-quality, narratively coherent images compared to a generic prompt.

---

## Storyboard Phase (Imagen)

Once a plan is approved, the session is in the **STORYBOARD** phase:

1. **Generate Shot** — Click "⚡ Generate Shot N" to call Vertex AI Imagen. The shot card updates with an image, dialogue, SFX notes, and camera notes.
2. **Approve** — Click "✓ Approve" to advance the sequential pointer to the next shot. Only the current shot (or a complete storyboard) allows approval.
3. **Revise** — Click "✎ Revise", enter feedback, and submit. The shot status changes to `needs_changes`. Regenerating passes the stored feedback back to the generation tool.
4. **Retroactive editing** — After the storyboard is complete, any shot can be revised and regenerated. The sequential pointer does not roll back for past shots.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Browser  (React / Vite)                                 │
│  • INTAKE: BriefForm                                     │
│  • PLANNING: PlanningPanel (chat + plan approval)        │
│  • STORYBOARD: ShotCard + StoryboardGrid                 │
└────────────────────┬─────────────────────────────────────┘
                     │  HTTP (JSON)
┌────────────────────▼─────────────────────────────────────┐
│  FastAPI  (backend/app/main.py)                          │
│  • /health  /echo  /session  /session/{id}               │
│  • /session/{id}/planning/*  (message, plan, approve)    │
│  • /session/{id}/shots/{i}/* (generate, approve, revise) │
│  • Input validation via Pydantic                         │
│  • Consistent error payloads; no stack traces exposed    │
└────┬──────────────────────┬───────────────────────────────┘
     │                      │
     ▼                      ▼
┌─────────────┐    ┌──────────────────────────────────────┐
│ SessionStore│    │  StoryboardAgent  (agent.py)         │
│ (store.py)  │    │  • Phase transitions (INTAKE →       │
│ thread-safe │◄───│    PLANNING → STORYBOARD)            │
│ in-memory   │    │  • Sequential shot gating            │
│ dict+Lock   │    │  • Calls tool functions              │
└─────────────┘    └──────────────┬───────────────────────┘
                                  │
                    ┌─────────────┴───────────────┐
                    │                             │
                    ▼                             ▼
       ┌────────────────────┐     ┌──────────────────────────┐
       │  LLMClient         │     │  Tools  (tools.py)       │
       │  (llm_client.py)   │     │  • generate_shot_card()  │
       │  Gemini via        │     │  Pure functions; no I/O  │
       │  Vertex AI         │     └──────────────────────────┘
       │  • planning chat   │
       │  • plan generation │
       └────────────────────┘
                    │
                    ▼
       ┌────────────────────┐
       │  ImageClient       │
       │  (image_client.py) │
       │  Vertex AI Imagen  │
       │  • shot images     │
       │  • stub fallback   │
       └────────────────────┘
```

**Key boundary rules:**

| Layer | Responsibility |
|---|---|
| `main.py` | HTTP request/response, CORS |
| `agent.py` | Workflow logic, phase enforcement, orchestration |
| `llm_client.py` | Gemini API calls (planning chat + plan generation) |
| `tools.py` | Deterministic shot card generation — no session state |
| `image_client.py` | Vertex AI Imagen wrapper with stub fallback |
| `store.py` | Persistence — swap to Redis/DB without touching other layers |
| `models.py` | Shared types — imported by all layers |

---

## Project Structure

```
pictr/
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI app, routes, middleware
│   │   ├── models.py       # Pydantic domain models (Session, Brief, Shot, Plan)
│   │   ├── store.py        # Thread-safe in-memory session store
│   │   ├── agent.py        # StoryboardAgent orchestration
│   │   ├── tools.py        # Tool functions (shot card generation)
│   │   ├── llm_client.py   # Gemini LLM client (planning chat + plan generation)
│   │   ├── image_client.py # Vertex AI Imagen wrapper (stub fallback)
│   │   └── config.py       # Settings loaded from environment
│   └── tests/
│       ├── conftest.py     # Shared fixtures (isolated TestClient)
│       ├── test_health.py
│       ├── test_sessions.py
│       ├── test_planning.py   # Planning phase tests (chat, plan, approve)
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
│   │       ├── PlanningPanel.tsx  # PLANNING: chat + plan generation/approval
│   │       ├── PlanSummary.tsx    # Read-only plan visualization
│   │       ├── ShotList.tsx
│   │       ├── ShotCard.tsx
│   │       ├── StoryboardGrid.tsx
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
# Edit .env if you need non-default CORS origins or GCP settings
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
2. **Submit the brief** — Fill in brand name, product, audience, tone, platform, and duration, then click "Start Planning". The session enters the **PLANNING** phase.
3. **Chat with the AI planner** — Type messages in the planning chat to share ideas, refine the concept, or ask questions. The AI creative director replies based on your brief.
4. **Generate the plan** — Click "✦ Generate Storyboard Plan". Gemini produces a structured plan with narrative beats and per-shot intent.
5. **Review and approve** — Review the plan summary. If satisfied, click "✓ Approve Plan — Begin Shot Generation". The session transitions to **STORYBOARD**.
6. **Generate Shot 1** — Click "⚡ Generate Shot 1". The shot card updates with an image (or placeholder in stub mode), dialogue, SFX notes, and camera notes.
7. **Approve or revise** — Click "✓ Approve" to move to the next shot, or "✎ Revise" to enter feedback and regenerate.
8. **Repeat** until all shots are approved. A completion banner confirms the storyboard is done.

> **Stub mode** (no GCP): images are deterministic picsum.photos placeholders — no API key needed for a full demo run. Planning chat (Gemini) requires GCP credentials; without them you'll receive a 503 response for planning actions.

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
  "planning_messages": [],
  "plan": null,
  "plan_status": "none",
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

### Brief

| Method | Path | Description |
|---|---|---|
| `POST` | `/session/{session_id}/message` | Submit creative brief — INTAKE → PLANNING |

### Planning

| Method | Path | Description |
|---|---|---|
| `POST` | `/session/{session_id}/planning/message` | Send user message; AI replies. Phase: PLANNING |
| `POST` | `/session/{session_id}/planning/plan` | Generate StoryboardPlan from brief + conversation. Sets `plan_status = "draft"` |
| `POST` | `/session/{session_id}/planning/approve` | Approve draft plan — PLANNING → STORYBOARD. Creates shot placeholders |

Planning endpoints return `503` if the Gemini LLM is unavailable or misconfigured.

### Shots

| Method | Path | Description |
|---|---|---|
| `POST` | `/session/{session_id}/shots/{index}/generate` | Generate shot card (image + text). Phase: STORYBOARD, plan approved |
| `POST` | `/session/{session_id}/shots/{index}/approve` | Approve shot; advance sequential pointer |
| `POST` | `/session/{session_id}/shots/{index}/revise` | Attach feedback; status → needs_changes |

---

## Running Tests

```bash
make test
# or:
pytest backend/tests/ -v
```

101 tests pass; 1 integration test is skipped unless `RUN_IMAGE_TESTS=1`.

```bash
RUN_IMAGE_TESTS=1 pytest backend/tests/test_image_client.py -k integration
```

### What's tested

| Test file | Coverage |
|---|---|
| `test_health.py` | `/health` and `/echo` endpoints |
| `test_sessions.py` | Session create/get, deep-copy isolation, error shapes |
| `test_planning.py` | Planning chat, plan generation, plan approval, phase gating |
| `test_workflow.py` | Full brief → planning → generate → approve → revise cycle, all phase and status gates |
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
| `GOOGLE_CLOUD_PROJECT` | *(empty)* | GCP project for Vertex AI — leave empty for image stub mode |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex AI region |
| `IMAGE_MODEL` | `imagen-3.0-generate-001` | Imagen model identifier |
| `GEMINI_MODEL` | `gemini-2.0-flash-001` | Gemini model for planning chat and plan generation |

Frontend configuration (`frontend/.env`):

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |

---

## Vertex AI Setup

Both Gemini (planning) and Imagen (images) are accessed via Vertex AI using Application Default Credentials (ADC).

### 1. Authenticate

```bash
gcloud auth application-default login
```

### 2. Enable billing and the API

```bash
# Enable the Vertex AI API
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

Billing must be enabled on the GCP project — Vertex AI is not available on the free tier.

### 3. Set environment variables

```bash
# Required
export GOOGLE_CLOUD_PROJECT=your-project-id

# Optional — defaults shown
export GOOGLE_CLOUD_LOCATION=us-central1
export IMAGE_MODEL=imagen-3.0-generate-001
export GEMINI_MODEL=gemini-2.0-flash-001
```

Or add them to your `.env` file at the repo root.

### 4. Verify

```bash
# Start the server and test planning:
curl -s -X POST http://localhost:8000/session | python3 -c "import sys,json; sid=json.load(sys.stdin)['session_id']; print(sid)"
# Use the returned session_id in subsequent calls
```

---

## Optional: Firestore Persistence

By default, sessions are held in-memory and lost on restart. Enable Firestore to persist sessions across restarts and share them between processes.

### Named database

This project uses a **named** Firestore database (not the `(default)` database):

| Setting | Value |
|---|---|
| Database ID | `pictr-tubi` |
| Project | `pictr-488900` |
| Location | `nam5` (US multi-region) |

### Setup

**1. Authenticate** (same ADC credentials used for Vertex AI):

```bash
gcloud auth application-default login
```

**2. Set environment variables** (or add to `.env`):

```bash
USE_FIRESTORE=true
GOOGLE_CLOUD_PROJECT=pictr-488900

# Optional — defaults shown
FIRESTORE_DATABASE=pictr-tubi
FIRESTORE_COLLECTION=sessions
```

**3. Restart the backend.** Sessions will now be read from and written to Firestore on every operation.

When `USE_FIRESTORE=false` (default), the app runs entirely in-memory with no GCP dependency — no Firestore credentials needed.

---

## Troubleshooting

### 503 errors on planning endpoints

Planning endpoints (`/planning/message`, `/planning/plan`) return HTTP 503 when Gemini is unavailable or misconfigured. Common causes:

| Symptom | Likely cause | Fix |
|---|---|---|
| `503` immediately | `GOOGLE_CLOUD_PROJECT` not set | Set the env var and restart the server |
| `503` after a few seconds | ADC not configured | Run `gcloud auth application-default login` |
| `503` with billing error in server logs | Billing not enabled | Enable billing for the GCP project |
| `503` intermittently | Quota exceeded or Gemini outage | Wait and retry; check GCP status |

The error message shown in the UI is intentionally generic ("Planner temporarily unavailable") — full details are logged server-side.

### Image generation falls back to placeholders

If `GOOGLE_CLOUD_PROJECT` is not set, `ImageClient` operates in **stub mode**: it returns a deterministic `picsum.photos` URL instead of calling Imagen. This lets you run the full INTAKE → PLANNING → STORYBOARD workflow without any GCP credentials. Set `GOOGLE_CLOUD_PROJECT` to switch to real image generation.

### Planning works but images fail

If planning succeeds (Gemini is configured) but image generation fails (Imagen is not), each shot will have `status = "failed"`. The "↺ Retry Generation" button re-attempts the call. Check that:
- Billing is enabled for Imagen (separate quota from Gemini)
- The `IMAGE_MODEL` value is a valid Imagen model in your region

---

## Design Decisions

**Why threading.Lock and not asyncio.Lock?**
FastAPI with a single Uvicorn worker uses an event loop for async handlers, but the store may also be accessed from background threads in the future.  A `threading.Lock` is safe in both contexts and avoids the footgun of mixing sync/async locking primitives.

**Why return deep copies from the store?**
Returning a reference to the internal dict value would allow callers to silently corrupt stored state.  Deep copies make the isolation contract explicit and testable.

**Why a stub for image generation?**
`ImageClient` uses picsum.photos with a deterministic seed when `GOOGLE_CLOUD_PROJECT` is unset, so the full pipeline (intake → planning → shot generation → approval gate) can be exercised without a live API key.  Setting `GOOGLE_CLOUD_PROJECT` transparently switches to real Vertex AI Imagen with no other code changes.

**Why use the plan's `image_prompt` for Imagen?**
The planning phase has full narrative context (brief + conversation + beat structure). Gemini uses this to write a focused, visually specific Imagen prompt for each shot. This produces more coherent images than a generic prompt derived from the brief alone.

**Why not use a global `app` dependency for the store?**
FastAPI's `Depends()` machinery is clean but adds boilerplate for a one-module MVP.  The module-level store singleton is simpler and the tests replace it via targeted monkey-patching.  If the project grows, switching to `Depends(get_store)` is straightforward.
