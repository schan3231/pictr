"""
FastAPI application entry point for Pictr Storyboard Agent.

Module layout:
  main.py   — app factory, middleware, exception handlers, router inclusion
  models.py — Pydantic domain models
  store.py  — in-memory session store (thread-safe)
  agent.py  — orchestration layer (phase machine + LLM/tool dispatch)
  tools.py  — deterministic tool functions called by the agent
  llm_client.py — Gemini LLM client for planning phase

Run locally:
  uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.agent import AgentError, agent
from backend.app.config import settings
from backend.app.llm_client import LLMGenerationError
from backend.app.models import (
    Brief,
    ErrorResponse,
    PlanningChatRequest,
    ReviseRequest,
    Session,
)
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
    version="0.2.0",
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
# Routes — meta
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
        raise HTTPException(
            status_code=400, detail="Request body must be valid JSON."
        ) from None
    return body


# ---------------------------------------------------------------------------
# Routes — sessions
# ---------------------------------------------------------------------------


@app.post(
    "/session",
    response_model=Session,
    status_code=201,
    summary="Create a new storyboard session",
    tags=["sessions"],
)
async def create_session() -> Session:
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
# Routes — brief submission (INTAKE → PLANNING)
# ---------------------------------------------------------------------------


@app.post(
    "/session/{session_id}/message",
    response_model=Session,
    summary="Submit creative brief (INTAKE → PLANNING)",
    tags=["workflow"],
)
async def submit_message(session_id: str, brief: Brief) -> Session:
    """
    Accept the user's creative brief and transition to PLANNING phase.

    **Phase gate:** only valid when `phase == INTAKE`.  Returns 400 if the
    session is already past INTAKE.

    On success the response includes an initial assistant message in
    `planning_messages` to kick off the creative conversation.  Shots are
    NOT created yet — proceed to the planning endpoints to build the plan.
    """
    try:
        return agent.submit_brief(session_id, brief)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found."
        ) from None
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Routes — planning phase (PLANNING phase only)
# ---------------------------------------------------------------------------


@app.post(
    "/session/{session_id}/planning/message",
    response_model=Session,
    summary="Send a message to the AI planner",
    tags=["planning"],
)
async def planning_message(session_id: str, body: PlanningChatRequest) -> Session:
    """
    Send a user message to the AI creative director and receive a reply.

    **Phase gate:** only valid when `phase == PLANNING`.

    The message is appended to `planning_messages` along with the assistant
    response.  Repeat as many times as needed before calling `/planning/plan`.

    Returns 503 if the Gemini LLM service is unavailable (e.g. GCP not configured).
    """
    try:
        return agent.planning_chat(session_id, body.message)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found."
        ) from None
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/session/{session_id}/planning/plan",
    response_model=Session,
    summary="Generate a storyboard plan from the conversation",
    tags=["planning"],
)
async def generate_plan(session_id: str) -> Session:
    """
    Ask the AI to produce a full `StoryboardPlan` from the brief + conversation.

    **Phase gate:** only valid when `phase == PLANNING`.

    The plan is stored as a draft (`plan_status == "draft"`) and the session
    remains in PLANNING.  Review the plan and call `/planning/approve` to commit
    it and advance to STORYBOARD.

    Returns 503 if the Gemini LLM service is unavailable.
    """
    try:
        return agent.generate_plan(session_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found."
        ) from None
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/session/{session_id}/planning/approve",
    response_model=Session,
    summary="Approve the draft plan and begin shot generation",
    tags=["planning"],
)
async def approve_plan(session_id: str) -> Session:
    """
    Approve the current draft `StoryboardPlan` and transition to STORYBOARD phase.

    **Phase gate:** only valid when `phase == PLANNING` and `plan_status == "draft"`.

    On success the `shots` list is populated from the plan (one Shot per
    PlannedShot), all in `draft` status, ready for sequential generation.
    The session transitions to `phase == "STORYBOARD"`.
    """
    try:
        return agent.approve_plan(session_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found."
        ) from None
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Routes — storyboard phase (STORYBOARD phase only)
# ---------------------------------------------------------------------------


@app.post(
    "/session/{session_id}/shots/{shot_index}/generate",
    response_model=Session,
    summary="Generate the current shot card",
    tags=["workflow"],
)
async def generate_shot(session_id: str, shot_index: int) -> Session:
    """
    Generate image + narrative content for the shot at `shot_index`.

    **Phase gate:** only valid when `phase == STORYBOARD` (plan must be approved).

    Shot must be in `draft`, `needs_changes`, or `failed` status.  After
    generation the shot transitions to `ready`.
    """
    try:
        return agent.generate_shot(session_id, shot_index)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found."
        ) from None
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/session/{session_id}/shots/{shot_index}/approve",
    response_model=Session,
    summary="Approve the current shot card",
    tags=["workflow"],
)
async def approve_shot(session_id: str, shot_index: int) -> Session:
    """
    Approve the shot at `shot_index` and advance to the next shot.

    **Gate:** shot must be in `ready` status.
    After approval `current_shot_index` increments by one.
    """
    try:
        return agent.approve_shot(session_id, shot_index)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found."
        ) from None
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/session/{session_id}/shots/{shot_index}/revise",
    response_model=Session,
    summary="Request changes to a shot card",
    tags=["workflow"],
)
async def revise_shot(session_id: str, shot_index: int, body: ReviseRequest) -> Session:
    """
    Attach feedback to a shot and mark it for regeneration.

    The shot transitions from `ready` → `needs_changes` and
    `current_shot_index` resets to `shot_index` (unless it is already ahead).
    The next `/generate` call will incorporate the feedback.
    """
    try:
        return agent.request_changes(session_id, shot_index, body.feedback)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not found."
        ) from None
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
