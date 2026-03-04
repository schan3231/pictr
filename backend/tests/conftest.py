"""
Shared pytest fixtures.

Each test gets a fully isolated environment:
- A fresh SessionStore (empty, no shared state between tests)
- A fresh StoryboardAgent wired to that same fresh store
- A stubbed image_client (no real Vertex AI calls, regardless of .env)

Both singletons are monkey-patched onto the `main` module so that route
handlers and the agent singleton pick up the isolated instances without any
dependency-injection plumbing in production code.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import backend.app.tools as tools_module
from backend.app import main as app_module
from backend.app.agent import StoryboardAgent
from backend.app.store import SessionStore


@pytest.fixture(autouse=True)
def stub_image_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Replace the image_client singleton in tools.py with a deterministic stub.

    Prevents any real Vertex AI calls during the test suite, regardless of
    what GOOGLE_CLOUD_PROJECT is set to in .env.

    Tests that need to control image_client behaviour (e.g. to simulate
    errors) can override this by patching backend.app.tools.image_client
    inside their own `with patch(...)` block; that inner patch takes priority.
    """
    mock = MagicMock()
    mock.generate_image.return_value = "https://picsum.photos/seed/0/1280/720"
    monkeypatch.setattr(tools_module, "image_client", mock)


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
