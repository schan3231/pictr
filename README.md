# PICTr — AI Storyboard Generator

> **Tubi Builders Program submission** — Generate professional commercial storyboards from a creative brief using Gemini for planning and Imagen for image generation.
> 
<img width="1512" height="853" alt="Screenshot 2026-03-05 at 12 39 48 AM" src="https://github.com/user-attachments/assets/ac5f81e1-fe5b-4136-870e-f7d06d8f14d6" />

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Product Workflow](#2-product-workflow)
3. [System Architecture](#3-system-architecture)
4. [Architecture Diagrams](#4-architecture-diagrams)
5. [Local Setup](#5-local-setup)
6. [Vertex AI Setup](#6-vertex-ai-setup)
7. [Firestore Persistence](#7-firestore-persistence)
8. [End-to-End Demo](#8-end-to-end-demo)
9. [Design Decisions](#9-design-decisions)
10. [Tradeoffs](#10-tradeoffs)
11. [Phase 2 Roadmap](#11-phase-2-roadmap)

---

## 1. Project Overview

Creating a commercial storyboard today requires a creative director, a copywriter, a storyboard artist, and days of back-and-forth.  PICTr compresses that process into minutes.

A user submits a creative brief — brand, product, audience, tone — and the system uses **Gemini** to co-develop the narrative arc through a conversational planning interface.  Once the plan is approved, **Imagen** generates a shot card for each scene: image, voiceover, sound effects, and camera notes.  The user reviews each shot in sequence and either approves it or requests a revision before moving on.

The result is a complete, visually-grounded storyboard ready to hand off to a production team.

**Stack:** Python 3.11 / FastAPI · React + Vite + TypeScript · Google Vertex AI (Gemini + Imagen) · Google Cloud Firestore

---

## 2. Product Workflow

*This section is the demo guide — each step maps to a UI interaction.*

```
 1  Submit Brief          Enter brand, product, audience, tone, platform, duration
         ↓
 2  Planning Chat         Chat with the Gemini creative director to shape the narrative
         ↓
 3  Generate Plan         Gemini produces a structured StoryboardPlan (beats + shots)
         ↓
 4  Approve Plan          Review and lock the plan; shot placeholders are created
         ↓
 5  Generate Shot         Imagen produces image + voiceover + sfx + camera notes
         ↓
 6  Approve / Revise      Approve to advance, or request changes with feedback
         ↓
 7  Complete Storyboard   All shots approved — view the storyboard grid
```

**Phase gates are enforced server-side.** You cannot generate a shot until the plan is approved, and you cannot advance to the next shot until the current one is approved.

---

## 3. System Architecture

| Layer | Technology | Responsibility |
|---|---|---|
| **Frontend** | React + Vite + TypeScript | Session management, phase-aware UI, API calls via `fetch()` |
| **API** | FastAPI + Uvicorn | HTTP routing, request validation, error handling, CORS |
| **Agent** | `StoryboardAgent` | Workflow orchestration, phase gate enforcement, LLM/tool dispatch |
| **Tools** | `tools.py` | Shot card generation — pure functions, no store side-effects |
| **LLM Client** | `GeminiClient` | Gemini via Vertex AI; planning chat + structured plan generation |
| **Image Client** | `ImageClient` | Imagen via Vertex AI; returns base64 data URL or stub placeholder |
| **Persistence** | `SessionStore` / `FirestoreSessionStore` | Thread-safe session storage, swappable via `USE_FIRESTORE` flag |

**Request flow:**

```
Browser  →  React UI  →  FastAPI  →  StoryboardAgent  →  GeminiClient / ImageClient  →  Vertex AI
                                           ↓
                                    SessionStore (Memory or Firestore)
```

---

## 4. Architecture Diagrams

### Component Layout

```
┌─────────────────────────────────────────────────────┐
│                    User Browser                     │
│   ┌──────────────────┐  ┌────────────────────────┐  │
│   │   Left Panel     │  │      Right Panel       │  │
│   │ Session Controls │  │  Planning Chat /       │  │
│   │ Brief Summary    │  │  Storyboard Grid /     │  │
│   │ Shot List        │  │  Shot Card Detail      │  │
│   └────────┬─────────┘  └───────────┬────────────┘  │
└────────────┼───────────────────────-┼───────────────┘
             │       React (Vite)     │
             └───────────┬────────────┘
                         │ fetch() / JSON
                         ▼
              ┌──────────────────────┐
              │   FastAPI Backend    │
              │  (uvicorn, :8000)    │
              └──────────┬───────────┘
                         │
                ┌────────┴────────┐
                ▼                 ▼
        ┌──────────────┐  ┌──────────────────┐
        │ Storyboard   │  │  SessionStore    │
        │ Agent        │  │ (Mem/Firestore)  │
        └──────┬───────┘  └──────────────────┘
               │
      ┌────────┴─────────┐
      ▼                  ▼
┌──────────────┐   ┌─────────────────┐
│ GeminiClient │   │  ImageClient    │
│  (planning)  │   │  (generation)   │
└──────┬───────┘   └───────┬─────────┘
       │                   │
       └─────────┬──────────┘
                 ▼
      ┌───────────────────────┐
      │   Google Vertex AI    │
      │   Gemini  +  Imagen   │
      └───────────────────────┘
```

### Session State Machine

```
  ┌─────────┐  submit_brief   ┌──────────┐  approve_plan   ┌────────────┐
  │  INTAKE │ ──────────────► │ PLANNING │ ──────────────► │ STORYBOARD │
  └─────────┘                 └──────────┘                 └────────────┘
```

### Shot State Machine

```
  draft ──► ready ──► approved
               │
               ▼
         needs_changes ──► (regenerate) ──► ready
               │
          failed ──► (retry) ──► ready
```

---

## 5. Local Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- `make` (optional)

### Backend

```bash
# 1. Clone
git clone <repo-url>
cd pictr

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install (editable + dev deps)
pip install -e ".[dev]"

# 4. Start backend
make dev
# or: uvicorn backend.app.main:app --reload --port 8000
```

API at `http://localhost:8000` · Interactive docs at `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

### Tests and Linting

```bash
make test     # pytest (107 tests)
make lint     # ruff
make check    # lint + format check (CI-safe)
```

---

## 6. Vertex AI Setup

PICTr ships with **stub mode** enabled by default:

- **Gemini not configured** → planning endpoints return `503`
- **Imagen not configured** → shot images use `picsum.photos` placeholders

The full UI and storyboard workflow are usable in stub mode without any GCP account.

### Enable real AI generation

**1. Authenticate** (Application Default Credentials — no API keys stored in the repo):

```bash
gcloud auth application-default login
```

**2. Enable the Vertex AI API:**

```bash
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

Billing must be enabled on the GCP project.

**3. Set environment variables** (`.env` file at repo root):

```bash
# Required
GOOGLE_CLOUD_PROJECT=your-project-id

# Optional — defaults shown
GOOGLE_CLOUD_LOCATION=us-central1
IMAGE_MODEL=imagen-3.0-generate-001
GEMINI_MODEL=gemini-2.0-flash-001
```

**4. Restart the backend** — Vertex AI activates automatically.

---

## 7. Firestore Persistence

By default, sessions live **in-memory** and are lost on restart.  Enable Firestore to persist sessions across restarts and allow session sharing by ID.

### Named database

| Setting | Value |
|---|---|
| Database ID | `pictr-tubi` |
| Project | `pictr-488900` |
| Location | `nam5` (US multi-region) |

### Enable persistence

Add to `.env`:

```bash
USE_FIRESTORE=true
GOOGLE_CLOUD_PROJECT=pictr-488900

# Optional — defaults shown
FIRESTORE_DATABASE=pictr-tubi
FIRESTORE_COLLECTION=sessions
```

Requires the same ADC authentication as Vertex AI.

### Load a session by ID

1. Copy the **Session ID** shown in the left panel.
2. Paste it into the **Load** input field (shown in both no-session and active-session states).
3. Click **Load** — the session state is restored from Firestore.

---

## 8. End-to-End Demo

1. Open `http://localhost:5173` → click **＋ New Session**
2. Fill in the brief (brand, product, audience, tone, platform, duration) → **Submit Brief**
3. Chat with the AI creative director to refine the narrative
4. Click **Generate Storyboard Plan** — Gemini produces a plan with beats and shot intents
5. Review the plan and click **Approve Plan** — shot placeholders are created
6. Click **Generate** on Shot 1 — Imagen produces image + voiceover + sfx + camera notes
7. Approve the shot to advance, or click **Revise** to give feedback and regenerate
8. Repeat for each shot until all are approved
9. View the completed storyboard in the grid overview

---

## 9. Design Decisions

**FastAPI**
Async-ready, minimal boilerplate, and the automatic `/docs` endpoint is a useful demo artifact.  Pydantic models are shared as the validation layer for both API requests and domain objects.

**React + Vite + TypeScript**
Fast HMR during development.  TypeScript `types.ts` mirrors the backend Pydantic models exactly, so the contract is explicit and compiler-checked.

**Agent / tool architecture**
`StoryboardAgent` owns workflow logic and phase transitions.  `tools.py` contains pure functions with no store side-effects.  `GeminiClient` and `ImageClient` are provider-specific adapters — swapping either requires changing one file.

**Explicit sequential approval**
Each shot must be approved before the next generates.  This prevents runaway generation costs, creates a natural review checkpoint, and mirrors how real storyboard reviews work.

**Vertex AI with ADC**
Gemini and Imagen share a single authentication system (Application Default Credentials).  No per-service API keys, no secrets in the repository.

**Stub fallback modes**
`ImageClient` returns deterministic `picsum.photos` placeholders when GCP is unconfigured.  The full UI — all three phases, approval flow, revision cycle — is explorable without any cloud credentials.

---

## 10. Tradeoffs

| Decision | Benefit | Limitation |
|---|---|---|
| **Firestore over relational DB** | Schemaless fits rapid model iteration; Pydantic serialises cleanly to JSON documents | Ad-hoc cross-session queries are harder; no referential integrity |
| **Synchronous image generation** | No job queue needed; simpler request model | Blocks the request thread for the Imagen call duration (~3–8 s) |
| **Base64 images over GCS** | Zero blob storage infrastructure for the demo | Payload sizes inflate; not viable for production video thumbnails |
| **Single-node server** | Dead-simple deployment for demo and review | Multi-worker requires replacing in-memory store (Firestore flag addresses this) |
| **In-memory store (default)** | Zero dependencies for local development | Sessions lost on restart; acceptable for demos |

---

## 11. Phase 2 Roadmap

### Vision: AI-Generated Commercials

The logical evolution is moving from storyboard to video — using the approved shot cards as a production script for automated video segment generation and final assembly.

```
Approved Storyboard
        ↓
Video Segment Generation  (per shot — Veo or similar)
        ↓
Voiceover Sync  (per shot audio)
        ↓
Assembly + Timing
        ↓
Final Commercial Export  (MP4 / broadcast spec)
```

### Infrastructure changes

| Component | Change |
|---|---|
| **Database** | PostgreSQL via SQLAlchemy — relational integrity for users, projects, assets |
| **Asset storage** | Google Cloud Storage — durable store for images, video segments, final exports |
| **Job system** | Cloud Tasks or Pub/Sub — decouple long-running video generation from the request lifecycle |
| **Auth** | OAuth 2.0 / Firebase Auth — multi-user support, projects scoped to accounts |

### New backend modules

```
backend/app/
├── db.py          # SQLAlchemy session factory + ORM models
├── storage.py     # GCS upload / download helpers
├── jobs.py        # async job dispatch + status polling
└── assets.py      # brand logo + product image management
```

### New API endpoints

```
POST /session/{id}/export              kick off video export job
GET  /jobs/{job_id}                    poll export job status
POST /session/{id}/assets/upload       upload brand logo or product image
POST /session/{id}/shots/{i}/voice     generate voiceover audio for a shot
```

### Voice Interface

A voice-first planning mode is a natural extension of the chat interface:

- **Input:** Browser microphone → Web Speech API → transcript sent to `/planning/message`
- **Output:** TTS playback of Gemini responses via `SpeechSynthesis` API or a voice API (ElevenLabs, etc.)

This enables a fully conversational creative workflow — ideating an entire storyboard without typing.
