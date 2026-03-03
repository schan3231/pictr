"""
Shared pytest fixtures.

Each test gets a fully isolated environment:
- A fresh SessionStore (empty, no shared state between tests)
- A fresh StoryboardAgent wired to that same fresh store

Both are monkey-patched onto the `main` module so that route handlers and the
agent singleton pick up the isolated instances without any dependency-injection
plumbing in production code.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import main as app_module
from backend.app.agent import StoryboardAgent
from backend.app.store import SessionStore


@pytest.fixture()
def client() -> TestClient:
    """
    Return a TestClient backed by a fresh, isolated SessionStore + StoryboardAgent.

    Teardown restores the original module-level singletons so other fixtures
    or test files are not affected.
    """
    fresh_store = SessionStore()
    fresh_agent = StoryboardAgent(session_store=fresh_store)

    original_store = app_module.store
    original_agent = app_module.agent

    app_module.store = fresh_store  # type: ignore[attr-defined]
    app_module.agent = fresh_agent  # type: ignore[attr-defined]

    try:
        with TestClient(app_module.app, raise_server_exceptions=True) as c:
            yield c
    finally:
        app_module.store = original_store  # type: ignore[attr-defined]
        app_module.agent = original_agent  # type: ignore[attr-defined]
