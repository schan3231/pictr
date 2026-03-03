"""
Shared pytest fixtures.

`client` gives each test a fresh TestClient wired to a clean SessionStore so
tests are fully isolated — no shared state between tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import main as app_module
from backend.app.store import SessionStore


@pytest.fixture()
def client() -> TestClient:
    """
    Return a TestClient backed by a fresh, empty SessionStore.

    We monkey-patch the store on the `main` module so that the route handlers
    pick up the isolated store without needing dependency injection plumbing.
    """
    fresh_store = SessionStore()

    # Patch the store used inside the route handlers.
    original_store = app_module.store
    app_module.store = fresh_store  # type: ignore[attr-defined]

    try:
        with TestClient(app_module.app, raise_server_exceptions=True) as c:
            yield c
    finally:
        app_module.store = original_store  # type: ignore[attr-defined]
