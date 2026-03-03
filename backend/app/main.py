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

from backend.app.config import settings
from backend.app.models import CreateSessionRequest, ErrorResponse, Session
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
