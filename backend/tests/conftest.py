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

import backend.app.agent as agent_module
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


@pytest.fixture(autouse=True)
def stub_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Replace the llm_client singleton in agent.py with a deterministic stub.

    Prevents any real Gemini/Vertex AI calls during the test suite, regardless
    of what GOOGLE_CLOUD_PROJECT is set to in .env.

    - chat() returns a canned assistant reply.
    - generate_plan() returns a valid 3-shot StoryboardPlan derived from the brief.

    Tests that need to control llm_client behaviour can patch
    backend.app.agent.llm_client inside their own `with patch(...)` block.
    """
    from backend.app.models import Beat, PlannedShot, StoryboardPlan

    mock = MagicMock()
    mock.chat.return_value = (
        "Great ideas! Let's focus on emotional impact and clear product messaging."
    )

    def _stub_generate_plan(brief: object, messages: object) -> StoryboardPlan:  # type: ignore[type-arg]
        """Return a deterministic 3-shot plan regardless of brief content."""
        from backend.app.models import Brief  # noqa: PLC0415

        b: Brief = brief  # type: ignore[assignment]
        return StoryboardPlan(
            title=f"{b.brand_name} — 30s Spot",
            logline=f"A compelling commercial for {b.product}.",
            target_audience=b.target_audience,
            tone=b.tone,
            beats=[
                Beat(index=0, name="Hook", description="Grab attention immediately."),
                Beat(index=1, name="Build", description="Demonstrate product value."),
                Beat(index=2, name="Close", description="Drive action."),
            ],
            shots=[
                PlannedShot(
                    index=i,
                    short_title=f"Shot {i + 1}",
                    purpose=f"Narrative purpose of shot {i + 1}.",
                    visual_description=f"Cinematic scene {i + 1} for {b.brand_name}.",
                    key_action=f"Key action in shot {i + 1}.",
                    image_prompt=(
                        f"Professional advertising photograph, shot {i + 1}, "
                        f"featuring {b.product} for {b.brand_name}."
                    ),
                )
                for i in range(3)
            ],
        )

    mock.generate_plan.side_effect = _stub_generate_plan
    monkeypatch.setattr(agent_module, "llm_client", mock)


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
