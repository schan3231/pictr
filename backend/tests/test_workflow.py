"""
Integration tests for the full storyboard workflow.

Coverage targets:
- Happy path: brief → planning → approve plan → generate → approve → next shot
- Status gating: cannot approve a draft shot; cannot generate a ready/approved shot
- Retroactive editing: revise + regenerate any shot; pointer only resets for current/future shots
- Revision cycle: revise → regenerate increments revision counter
- Phase gating: cannot submit brief twice; cannot generate before plan is approved
- Input validation: empty feedback rejected; blank brief fields rejected
"""

from __future__ import annotations

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

VALID_BRIEF = {
    "brand_name": "Acme Co",
    "product": "Super Widget",
    "target_audience": "Tech-savvy millennials",
    "tone": "fun and energetic",
    "platform": "youtube",
    "duration_seconds": 30,
}


def _create_session(client: TestClient) -> str:
    """Create a session and return its session_id."""
    resp = client.post("/session")
    assert resp.status_code == 201
    return resp.json()["session_id"]


def _submit_brief(client: TestClient, session_id: str, brief: dict = VALID_BRIEF) -> dict:
    """Submit a brief (INTAKE → PLANNING) and return the updated session body."""
    resp = client.post(f"/session/{session_id}/message", json=brief)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _complete_planning(client: TestClient, session_id: str) -> dict:
    """
    Advance from PLANNING phase to STORYBOARD via plan generate + approve.

    The stub llm_client (from conftest) returns a deterministic 3-shot plan,
    so tests that call this helper always start STORYBOARD with 3 shots.
    """
    resp = client.post(f"/session/{session_id}/planning/plan")
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/session/{session_id}/planning/approve")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _generate(client: TestClient, session_id: str, shot_index: int) -> dict:
    resp = client.post(f"/session/{session_id}/shots/{shot_index}/generate")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _approve(client: TestClient, session_id: str, shot_index: int) -> dict:
    resp = client.post(f"/session/{session_id}/shots/{shot_index}/approve")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _revise(client: TestClient, session_id: str, shot_index: int, feedback: str) -> dict:
    resp = client.post(
        f"/session/{session_id}/shots/{shot_index}/revise",
        json={"feedback": feedback},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Brief submission  (INTAKE → PLANNING)
# ---------------------------------------------------------------------------


class TestSubmitBrief:
    def test_submit_brief_transitions_to_planning(self, client: TestClient) -> None:
        """Brief submission now moves to PLANNING (not directly to STORYBOARD)."""
        sid = _create_session(client)
        body = _submit_brief(client, sid)
        assert body["phase"] == "PLANNING"

    def test_submit_brief_no_shots_yet(self, client: TestClient) -> None:
        """Shots are not created until the plan is approved; PLANNING starts empty."""
        sid = _create_session(client)
        body = _submit_brief(client, sid)
        assert body["phase"] == "PLANNING"
        assert body["shots"] == []

    def test_submit_brief_adds_welcome_message(self, client: TestClient) -> None:
        """Brief submission seeds planning_messages with an assistant welcome turn."""
        sid = _create_session(client)
        body = _submit_brief(client, sid)
        assert len(body["planning_messages"]) >= 1
        assert body["planning_messages"][0]["role"] == "assistant"

    def test_submit_brief_stores_brief(self, client: TestClient) -> None:
        sid = _create_session(client)
        body = _submit_brief(client, sid)
        assert body["brief"]["brand_name"] == "Acme Co"

    def test_submit_brief_sets_current_shot_index_zero(self, client: TestClient) -> None:
        sid = _create_session(client)
        body = _submit_brief(client, sid)
        assert body["current_shot_index"] == 0

    def test_cannot_submit_brief_twice(self, client: TestClient) -> None:
        """Phase gate: submitting a second brief must return 400."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        resp = client.post(f"/session/{sid}/message", json=VALID_BRIEF)
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_submit_brief_missing_required_field(self, client: TestClient) -> None:
        sid = _create_session(client)
        bad_brief = {k: v for k, v in VALID_BRIEF.items() if k != "brand_name"}
        resp = client.post(f"/session/{sid}/message", json=bad_brief)
        assert resp.status_code == 422

    def test_submit_brief_blank_brand_name(self, client: TestClient) -> None:
        sid = _create_session(client)
        bad = {**VALID_BRIEF, "brand_name": "   "}
        resp = client.post(f"/session/{sid}/message", json=bad)
        # strip_whitespace reduces to empty string → min_length=1 fails
        assert resp.status_code == 422

    def test_submit_brief_unknown_session(self, client: TestClient) -> None:
        resp = client.post("/session/nonexistent/message", json=VALID_BRIEF)
        assert resp.status_code == 404

    def test_duration_out_of_range(self, client: TestClient) -> None:
        sid = _create_session(client)
        bad = {**VALID_BRIEF, "duration_seconds": 200}
        resp = client.post(f"/session/{sid}/message", json=bad)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Shot generation  (requires STORYBOARD phase — complete planning first)
# ---------------------------------------------------------------------------


class TestGenerateShot:
    def test_generate_shot_zero(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        body = _generate(client, sid, 0)
        assert body["shots"][0]["status"] == "ready"

    def test_generate_populates_all_card_fields(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        body = _generate(client, sid, 0)
        shot = body["shots"][0]
        assert shot["image_url"] is not None
        assert shot["dialogue_text"] is not None
        assert shot["sfx_notes"] is not None
        assert shot["camera_notes"] is not None

    def test_cannot_generate_before_brief(self, client: TestClient) -> None:
        """Phase gate: cannot generate in INTAKE phase."""
        sid = _create_session(client)
        resp = client.post(f"/session/{sid}/shots/0/generate")
        assert resp.status_code == 400

    def test_cannot_generate_before_plan_approved(self, client: TestClient) -> None:
        """Phase gate: cannot generate in PLANNING phase (plan not yet approved)."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        resp = client.post(f"/session/{sid}/shots/0/generate")
        assert resp.status_code == 400

    def test_can_generate_non_current_draft_shot_directly(self, client: TestClient) -> None:
        """Retroactive: generating a non-current shot is allowed if status permits."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        # Shot 0 is draft — generate shot 0, approve it, then revise shot 0 retroactively
        _generate(client, sid, 0)
        _approve(client, sid, 0)
        _revise(client, sid, 0, "Redo this one")
        # Shot 0 is now needs_changes; current_shot_index is still 1 (not rolled back)
        body = _generate(client, sid, 0)
        assert body["shots"][0]["status"] == "ready"

    def test_cannot_regenerate_approved_shot_without_revise(self, client: TestClient) -> None:
        """Status gate: approved shots cannot be re-generated without first revising."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        _approve(client, sid, 0)
        # Approved shot — direct generate should be rejected
        resp = client.post(f"/session/{sid}/shots/0/generate")
        assert resp.status_code == 400

    def test_cannot_generate_unknown_session(self, client: TestClient) -> None:
        resp = client.post("/session/bad-id/shots/0/generate")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Shot approval
# ---------------------------------------------------------------------------


class TestApproveShot:
    def test_approve_advances_index(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        body = _approve(client, sid, 0)
        assert body["current_shot_index"] == 1

    def test_approve_sets_status(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        body = _approve(client, sid, 0)
        assert body["shots"][0]["status"] == "approved"

    def test_cannot_approve_draft_shot(self, client: TestClient) -> None:
        """Status gate: shot must be 'ready' to approve."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        # Shot is still 'draft' — not yet generated
        resp = client.post(f"/session/{sid}/shots/0/approve")
        assert resp.status_code == 400

    def test_cannot_approve_before_generate(self, client: TestClient) -> None:
        """Same as above — ensure draft → approve is blocked with 'ready' in detail."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        resp = client.post(f"/session/{sid}/shots/0/approve")
        assert resp.status_code == 400
        assert "ready" in resp.json()["detail"].lower()

    def test_cannot_approve_out_of_range_index(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        resp = client.post(f"/session/{sid}/shots/99/approve")
        assert resp.status_code == 400

    def test_approve_unknown_session(self, client: TestClient) -> None:
        resp = client.post("/session/bad-id/shots/0/approve")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Shot revision
# ---------------------------------------------------------------------------


class TestReviseShot:
    def test_revise_sets_needs_changes(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        body = _revise(client, sid, 0, "Make it more dramatic")
        assert body["shots"][0]["status"] == "needs_changes"

    def test_revise_attaches_feedback(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        body = _revise(client, sid, 0, "More colour please")
        assert body["shots"][0]["user_feedback"] == "More colour please"

    def test_revise_keeps_current_index_when_at_current(self, client: TestClient) -> None:
        """Revising the current shot keeps current_shot_index pointing at it."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        body = _revise(client, sid, 0, "Needs work")
        # current_shot_index was 0, shot_index is 0 (≥ current), so pointer stays 0
        assert body["current_shot_index"] == 0

    def test_regenerate_after_revise_increments_revision(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        _revise(client, sid, 0, "Go again")
        body = _generate(client, sid, 0)
        assert body["shots"][0]["revision"] == 1

    def test_revise_empty_feedback_rejected(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        resp = client.post(
            f"/session/{sid}/shots/0/revise",
            json={"feedback": ""},
        )
        assert resp.status_code == 422

    def test_revise_whitespace_only_feedback_rejected(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        resp = client.post(
            f"/session/{sid}/shots/0/revise",
            json={"feedback": "   "},
        )
        assert resp.status_code == 422

    def test_revise_approved_shot_allowed(self, client: TestClient) -> None:
        """Retroactive editing: revising an approved shot is permitted."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        _approve(client, sid, 0)
        body = _revise(client, sid, 0, "Redo with warmer lighting")
        assert body["shots"][0]["status"] == "needs_changes"
        assert body["shots"][0]["user_feedback"] == "Redo with warmer lighting"

    def test_revise_past_shot_does_not_roll_back_pointer(self, client: TestClient) -> None:
        """Retroactive editing: revising a past shot must NOT reset current_shot_index."""
        sid = _create_session(client)
        # The stub plan always returns 3 shots — no need to set duration_seconds.
        _submit_brief(client, sid)
        _complete_planning(client, sid)
        _generate(client, sid, 0)
        _approve(client, sid, 0)
        _generate(client, sid, 1)
        _approve(client, sid, 1)
        # current_shot_index is now 2
        body = _revise(client, sid, 0, "Touch up shot 0")
        # Pointer must stay at 2, not roll back to 0
        assert body["current_shot_index"] == 2

    def test_revise_unknown_session(self, client: TestClient) -> None:
        resp = client.post(
            "/session/bad-id/shots/0/revise",
            json={"feedback": "fix it"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Full happy-path sequence
# ---------------------------------------------------------------------------


class TestFullWorkflow:
    def test_two_shot_complete_sequence(self, client: TestClient) -> None:
        """
        End-to-end: create → brief → complete planning
                    → generate[0] → approve[0] → generate[1] → approve[1].

        The stub plan always provides 3 shots; we run through the first two.
        """
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)

        # Shot 0
        s = _generate(client, sid, 0)
        assert s["shots"][0]["status"] == "ready"
        s = _approve(client, sid, 0)
        assert s["current_shot_index"] == 1
        assert s["shots"][0]["status"] == "approved"

        # Shot 1
        s = _generate(client, sid, 1)
        assert s["shots"][1]["status"] == "ready"
        s = _approve(client, sid, 1)
        assert s["current_shot_index"] == 2
        assert s["shots"][1]["status"] == "approved"

    def test_revise_then_continue(self, client: TestClient) -> None:
        """Revise shot 0, regenerate it, approve, then proceed to shot 1."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _complete_planning(client, sid)

        _generate(client, sid, 0)
        _revise(client, sid, 0, "Needs more energy")
        s = _generate(client, sid, 0)
        assert s["shots"][0]["revision"] == 1
        assert s["shots"][0]["status"] == "ready"

        _approve(client, sid, 0)
        s = _generate(client, sid, 1)
        assert s["shots"][1]["status"] == "ready"
