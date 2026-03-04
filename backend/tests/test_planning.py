"""
Tests for the PLANNING phase endpoints.

Coverage targets:
- submit_brief → PLANNING transition (no shots yet)
- planning/message: chat turn appended, LLM called, 503 on LLM failure
- planning/plan: plan stored as draft, LLM called, 503 on LLM failure
- planning/approve: plan approved, shots created, STORYBOARD transition
- Phase gating: shot generation rejected until plan approved
- Input validation: empty message rejected
- Error paths: unknown session, wrong phase

All LLM calls are intercepted by the stub_llm_client autouse fixture in conftest.py.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.app.agent as agent_module
from backend.app.llm_client import LLMGenerationError

# ---------------------------------------------------------------------------
# Shared data
# ---------------------------------------------------------------------------

VALID_BRIEF = {
    "brand_name": "Zesty Drinks",
    "product": "Lemon Burst",
    "target_audience": "Health-conscious Gen Z",
    "tone": "vibrant and fresh",
    "platform": "youtube",
    "duration_seconds": 30,
}


def _create_and_brief(client: TestClient) -> str:
    """Create session, submit brief, return session_id (in PLANNING phase)."""
    resp = client.post("/session")
    assert resp.status_code == 201
    sid = resp.json()["session_id"]
    resp = client.post(f"/session/{sid}/message", json=VALID_BRIEF)
    assert resp.status_code == 200
    return sid


def _reach_storyboard(client: TestClient) -> str:
    """Create session, brief, generate plan, approve plan, return session_id."""
    sid = _create_and_brief(client)
    resp = client.post(f"/session/{sid}/planning/plan")
    assert resp.status_code == 200
    resp = client.post(f"/session/{sid}/planning/approve")
    assert resp.status_code == 200
    return sid


# ---------------------------------------------------------------------------
# submit_brief moves to PLANNING
# ---------------------------------------------------------------------------


class TestSubmitBriefMovesToPlanning:
    def test_submit_brief_transitions_to_planning(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.get(f"/session/{sid}")
        assert resp.json()["phase"] == "PLANNING"

    def test_submit_brief_starts_with_no_shots(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.get(f"/session/{sid}")
        assert resp.json()["shots"] == []

    def test_submit_brief_plan_status_is_none(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.get(f"/session/{sid}")
        assert resp.json()["plan_status"] == "none"
        assert resp.json()["plan"] is None

    def test_submit_brief_adds_welcome_assistant_message(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.get(f"/session/{sid}")
        msgs = resp.json()["planning_messages"]
        assert len(msgs) >= 1
        assert msgs[0]["role"] == "assistant"
        assert len(msgs[0]["content"]) > 0


# ---------------------------------------------------------------------------
# planning/message
# ---------------------------------------------------------------------------


class TestPlanningChat:
    def test_planning_chat_appends_user_message(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.post(
            f"/session/{sid}/planning/message",
            json={"message": "Focus on joy and refreshment"},
        )
        assert resp.status_code == 200
        msgs = resp.json()["planning_messages"]
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert any("joy" in m["content"].lower() for m in user_msgs)

    def test_planning_chat_appends_assistant_response(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.post(
            f"/session/{sid}/planning/message",
            json={"message": "What about a beach scene?"},
        )
        assert resp.status_code == 200
        msgs = resp.json()["planning_messages"]
        assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
        # welcome + one reply = at least 2 assistant messages
        assert len(assistant_msgs) >= 2

    def test_planning_chat_calls_llm(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        client.post(
            f"/session/{sid}/planning/message",
            json={"message": "Let's try a city setting"},
        )
        assert agent_module.llm_client.chat.called

    def test_planning_chat_rejects_empty_message(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.post(
            f"/session/{sid}/planning/message",
            json={"message": ""},
        )
        assert resp.status_code == 422

    def test_planning_chat_rejects_whitespace_message(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.post(
            f"/session/{sid}/planning/message",
            json={"message": "   "},
        )
        assert resp.status_code == 422

    def test_planning_chat_returns_503_on_llm_failure(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        with patch.object(
            agent_module.llm_client,
            "chat",
            side_effect=LLMGenerationError("LLM quota exceeded. Please wait and try again."),
        ):
            resp = client.post(
                f"/session/{sid}/planning/message",
                json={"message": "Some message"},
            )
        assert resp.status_code == 503
        assert "quota" in resp.json()["detail"].lower()

    def test_planning_chat_requires_planning_phase(self, client: TestClient) -> None:
        """Cannot chat in INTAKE phase."""
        resp = client.post("/session")
        sid = resp.json()["session_id"]
        resp = client.post(
            f"/session/{sid}/planning/message",
            json={"message": "Hi"},
        )
        assert resp.status_code == 400
        assert "PLANNING" in resp.json()["detail"]

    def test_planning_chat_unknown_session(self, client: TestClient) -> None:
        resp = client.post(
            "/session/nonexistent/planning/message",
            json={"message": "Hello"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# planning/plan
# ---------------------------------------------------------------------------


class TestGeneratePlan:
    def test_generate_plan_stores_plan(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.post(f"/session/{sid}/planning/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] is not None
        assert data["plan"]["title"] != ""
        assert len(data["plan"]["shots"]) > 0

    def test_generate_plan_sets_draft_status(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        resp = client.post(f"/session/{sid}/planning/plan")
        assert resp.status_code == 200
        assert resp.json()["plan_status"] == "draft"

    def test_generate_plan_phase_remains_planning(self, client: TestClient) -> None:
        """Generating the plan does NOT auto-approve; session stays in PLANNING."""
        sid = _create_and_brief(client)
        resp = client.post(f"/session/{sid}/planning/plan")
        assert resp.status_code == 200
        assert resp.json()["phase"] == "PLANNING"

    def test_generate_plan_calls_llm(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        client.post(f"/session/{sid}/planning/plan")
        assert agent_module.llm_client.generate_plan.called

    def test_generate_plan_returns_503_on_llm_failure(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        with patch.object(
            agent_module.llm_client,
            "generate_plan",
            side_effect=LLMGenerationError("Planner returned invalid output. Please try again."),
        ):
            resp = client.post(f"/session/{sid}/planning/plan")
        assert resp.status_code == 503
        assert "planner" in resp.json()["detail"].lower()

    def test_generate_plan_requires_planning_phase(self, client: TestClient) -> None:
        """Cannot call generate_plan in INTAKE phase."""
        resp = client.post("/session")
        sid = resp.json()["session_id"]
        resp = client.post(f"/session/{sid}/planning/plan")
        assert resp.status_code == 400

    def test_generate_plan_unknown_session(self, client: TestClient) -> None:
        resp = client.post("/session/nonexistent/planning/plan")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# planning/approve
# ---------------------------------------------------------------------------


class TestApprovePlan:
    def test_approve_plan_transitions_to_storyboard(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        client.post(f"/session/{sid}/planning/plan")
        resp = client.post(f"/session/{sid}/planning/approve")
        assert resp.status_code == 200
        assert resp.json()["phase"] == "STORYBOARD"

    def test_approve_plan_sets_approved_status(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        client.post(f"/session/{sid}/planning/plan")
        resp = client.post(f"/session/{sid}/planning/approve")
        assert resp.json()["plan_status"] == "approved"

    def test_approve_plan_creates_shots_from_plan(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        client.post(f"/session/{sid}/planning/plan")
        resp = client.post(f"/session/{sid}/planning/approve")
        data = resp.json()
        # Stub plan returns 3 shots.
        assert len(data["shots"]) == 3
        for i, shot in enumerate(data["shots"]):
            assert shot["index"] == i
            assert shot["status"] == "draft"

    def test_approve_plan_shots_carry_image_prompt(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        client.post(f"/session/{sid}/planning/plan")
        resp = client.post(f"/session/{sid}/planning/approve")
        for shot in resp.json()["shots"]:
            assert shot["image_prompt"] is not None
            assert len(shot["image_prompt"]) > 0

    def test_approve_plan_sets_current_shot_index_zero(self, client: TestClient) -> None:
        sid = _create_and_brief(client)
        client.post(f"/session/{sid}/planning/plan")
        resp = client.post(f"/session/{sid}/planning/approve")
        assert resp.json()["current_shot_index"] == 0

    def test_approve_plan_requires_draft_plan(self, client: TestClient) -> None:
        """Cannot approve when no draft plan exists."""
        sid = _create_and_brief(client)
        resp = client.post(f"/session/{sid}/planning/approve")
        assert resp.status_code == 400
        assert "draft" in resp.json()["detail"].lower()

    def test_approve_plan_requires_planning_phase(self, client: TestClient) -> None:
        """Cannot call approve in INTAKE phase."""
        resp = client.post("/session")
        sid = resp.json()["session_id"]
        resp = client.post(f"/session/{sid}/planning/approve")
        assert resp.status_code == 400

    def test_approve_plan_unknown_session(self, client: TestClient) -> None:
        resp = client.post("/session/nonexistent/planning/approve")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Shot generation gate
# ---------------------------------------------------------------------------


class TestShotGenerationGate:
    def test_shot_generate_rejected_in_intake_phase(self, client: TestClient) -> None:
        """Generate shot blocked in INTAKE (no brief submitted)."""
        resp = client.post("/session")
        sid = resp.json()["session_id"]
        resp = client.post(f"/session/{sid}/shots/0/generate")
        assert resp.status_code == 400

    def test_shot_generate_rejected_in_planning_phase(self, client: TestClient) -> None:
        """Generate shot blocked in PLANNING (plan not yet approved)."""
        sid = _create_and_brief(client)
        resp = client.post(f"/session/{sid}/shots/0/generate")
        assert resp.status_code == 400

    def test_shot_generate_rejected_after_plan_draft_not_approved(
        self, client: TestClient
    ) -> None:
        """Generate shot still blocked when plan is draft but not approved."""
        sid = _create_and_brief(client)
        client.post(f"/session/{sid}/planning/plan")
        resp = client.post(f"/session/{sid}/shots/0/generate")
        assert resp.status_code == 400

    def test_shot_generate_allowed_after_plan_approved(self, client: TestClient) -> None:
        """Generate shot succeeds once plan is approved and STORYBOARD phase reached."""
        sid = _reach_storyboard(client)
        resp = client.post(f"/session/{sid}/shots/0/generate")
        assert resp.status_code == 200
        assert resp.json()["shots"][0]["status"] == "ready"
