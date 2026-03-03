"""
FastAPI application entry point for Pictr Storyboard Agent.

Module layout:
  main.py   — app factory, middleware, exception handlers, router inclusion
  models.py — Pydantic domain models
  store.py  — in-memory session store (thread-safe)
  agent.py  — ADK agent orchestration (stub for now)
  tools.py  — deterministic tool functions called by the agent

Run locally:
  uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.agent import AgentError, StoryboardAgent, agent
from backend.app.config import settings
from backend.app.models import Brief, CreateSessionRequest, ErrorResponse, ReviseRequest, Session
from backend.app.store import store

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Pictr Storyboard Agent",
    description="Generate 30-second commercial storyboards from a creative brief.",
    version="0.1.0",
    # Hide /docs in production by setting docs_url=None, but keep it for MVP.
)

# ---------------------------------------------------------------------------
# Middleware — CORS
#
# Restricted to configured origins only.  We never use allow_origins=["*"]
# because this API will eventually accept user content.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ---------------------------------------------------------------------------
# Exception handlers
#
# Override FastAPI's default to ensure a *consistent* error payload shape
# ({detail: str}) and to suppress internal stack traces from client responses.
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Return a consistent {detail: str} payload for all HTTP errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(detail=str(exc.detail)).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for unexpected errors.

    Log the full traceback server-side but return only a generic message to the
    client so internal details never leak.
    """
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail="An internal error occurred.").model_dump(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    summary="Health check",
    response_description="Service liveness indicator",
    tags=["meta"],
)
async def health() -> dict[str, bool]:
    """
    Simple liveness probe.

    Returns `{"ok": true}` when the service is up.  Does *not* check downstream
    dependencies (database, image API) — add a /ready endpoint for that later.
    """
    return {"ok": True}


@app.post(
    "/echo",
    summary="Echo request body (debug helper)",
    tags=["meta"],
)
async def echo(request: Request) -> Any:
    """
    Return the raw JSON request body unchanged.

    Useful during development to verify that the frontend is sending the expected
    payload shape.  Remove or gate behind a debug flag before production.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.")
    return body


@app.post(
    "/session",
    response_model=Session,
    status_code=201,
    summary="Create a new storyboard session",
    tags=["sessions"],
)
async def create_session(_body: CreateSessionRequest = CreateSessionRequest()) -> Session:
    """
    Create a new session in INTAKE phase.

    Returns the full Session object including the generated `session_id`.
    The caller must store this ID and pass it to all subsequent requests.
    """
    session = Session()  # defaults: phase=INTAKE, shots=[], etc.
    store.create(session)
    logger.info("Created session %s", session.session_id)
    return session


@app.get(
    "/session/{session_id}",
    response_model=Session,
    summary="Get session state",
    tags=["sessions"],
)
async def get_session(session_id: str) -> Session:
    """
    Retrieve the current state of a session by ID.

    Returns 404 if the session does not exist.
    """
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session


# ---------------------------------------------------------------------------
# Agent routes — message + shot workflow
# ---------------------------------------------------------------------------


@app.post(
    "/session/{session_id}/message",
    response_model=Session,
    summary="Submit creative brief (INTAKE phase)",
    tags=["workflow"],
)
async def submit_message(session_id: str, brief: Brief) -> Session:
    """
    Accept the user's creative brief and transition to STORYBOARD phase.

    **Phase gate:** only valid when `phase == INTAKE`.  If the session is
    already in STORYBOARD (brief already submitted) this returns 400.

    On success the response includes the populated `shots` list — one
    placeholder Shot per planned scene.  Content is generated per-shot via
    the `/shots/{index}/generate` endpoint.
    """
    try:
        return agent.submit_brief(session_id, brief)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post(
    "/session/{session_id}/shots/{shot_index}/generate",
    response_model=Session,
    summary="Generate the current shot card",
    tags=["workflow"],
)
async def generate_shot(session_id: str, shot_index: int) -> Session:
    """
    Generate image + narrative content for the shot at `shot_index`.

    **Sequential gating:** `shot_index` must equal `current_shot_index`.
    You cannot skip ahead or regenerate an already-approved shot.

    Shot must be in `draft` or `needs_changes` status.  After generation the
    shot transitions to `ready` and the full Shot Card is populated.
    """
    # Validate the requested index matches the active pointer before hitting
    # the agent, so the error message is precise.
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if shot_index != session.current_shot_index:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Shot {shot_index} is not the current shot. "
                f"Generate shot {session.current_shot_index} first."
            ),
        )
    try:
        return agent.generate_current_shot(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post(
    "/session/{session_id}/shots/{shot_index}/approve",
    response_model=Session,
    summary="Approve the current shot card",
    tags=["workflow"],
)
async def approve_shot(session_id: str, shot_index: int) -> Session:
    """
    Approve the shot at `shot_index` and advance to the next shot.

    **Gate:** shot must be in `ready` status (i.e. generated and not yet
    approved).  Attempting to approve a `draft` or `approved` shot returns 400.

    After approval `current_shot_index` increments by one.  When all shots are
    approved the storyboard is complete.
    """
    try:
        return agent.approve_shot(session_id, shot_index)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post(
    "/session/{session_id}/shots/{shot_index}/revise",
    response_model=Session,
    summary="Request changes to a shot card",
    tags=["workflow"],
)
async def revise_shot(session_id: str, shot_index: int, body: ReviseRequest) -> Session:
    """
    Attach feedback to a shot and mark it for regeneration.

    The shot transitions from `ready` → `needs_changes` and `current_shot_index`
    resets to `shot_index`.  The next call to `/generate` will pass the feedback
    to the generation tool so the new version reflects the user's notes.

    `revision` counter increments on each regeneration so the history is
    traceable.
    """
    try:
        return agent.request_changes(session_id, shot_index, body.feedback)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
