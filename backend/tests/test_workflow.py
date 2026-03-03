"""
Integration tests for the full storyboard workflow.

Coverage targets:
- Happy path: brief → shot list → generate → approve → next shot
- Sequential gating: cannot skip ahead to a non-current shot
- Status gating: cannot approve a draft shot; cannot generate an approved shot
- Revision cycle: revise → regenerate increments revision counter
- Phase gating: cannot submit brief twice; cannot generate in INTAKE phase
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
    """Submit a brief and return the updated session body."""
    resp = client.post(f"/session/{session_id}/message", json=brief)
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
# Brief submission
# ---------------------------------------------------------------------------


class TestSubmitBrief:
    def test_submit_brief_transitions_to_storyboard(self, client: TestClient) -> None:
        sid = _create_session(client)
        body = _submit_brief(client, sid)
        assert body["phase"] == "STORYBOARD"

    def test_submit_brief_creates_shots(self, client: TestClient) -> None:
        sid = _create_session(client)
        body = _submit_brief(client, sid)
        # 30s ÷ 5 = 6 shots (capped between 3 and 8)
        assert len(body["shots"]) == 6

    def test_submit_brief_shots_are_draft(self, client: TestClient) -> None:
        sid = _create_session(client)
        body = _submit_brief(client, sid)
        for shot in body["shots"]:
            assert shot["status"] == "draft"

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
# Shot generation
# ---------------------------------------------------------------------------


class TestGenerateShot:
    def test_generate_shot_zero(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        body = _generate(client, sid, 0)
        assert body["shots"][0]["status"] == "ready"

    def test_generate_populates_all_card_fields(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
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

    def test_cannot_skip_ahead_to_shot_1(self, client: TestClient) -> None:
        """Sequential gate: must generate shot 0 before shot 1."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        resp = client.post(f"/session/{sid}/shots/1/generate")
        assert resp.status_code == 400
        assert "current shot" in resp.json()["detail"].lower() or "0" in resp.json()["detail"]

    def test_cannot_regenerate_approved_shot(self, client: TestClient) -> None:
        """Status gate: approved shots cannot be re-generated."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _generate(client, sid, 0)
        _approve(client, sid, 0)
        # After approval, current_shot_index == 1; trying to generate 0 should fail
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
        _generate(client, sid, 0)
        body = _approve(client, sid, 0)
        assert body["current_shot_index"] == 1

    def test_approve_sets_status(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _generate(client, sid, 0)
        body = _approve(client, sid, 0)
        assert body["shots"][0]["status"] == "approved"

    def test_cannot_approve_draft_shot(self, client: TestClient) -> None:
        """Status gate: shot must be 'ready' to approve."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        # Shot is still 'draft' — not yet generated
        resp = client.post(f"/session/{sid}/shots/0/approve")
        assert resp.status_code == 400

    def test_cannot_approve_before_generate(self, client: TestClient) -> None:
        """Same as above — ensure draft → approve is blocked."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        resp = client.post(f"/session/{sid}/shots/0/approve")
        assert resp.status_code == 400
        assert "ready" in resp.json()["detail"].lower()

    def test_cannot_approve_out_of_range_index(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
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
        _generate(client, sid, 0)
        body = _revise(client, sid, 0, "Make it more dramatic")
        assert body["shots"][0]["status"] == "needs_changes"

    def test_revise_attaches_feedback(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _generate(client, sid, 0)
        body = _revise(client, sid, 0, "More colour please")
        assert body["shots"][0]["user_feedback"] == "More colour please"

    def test_revise_resets_current_index(self, client: TestClient) -> None:
        """Revision must reset the pointer back to the revised shot."""
        sid = _create_session(client)
        _submit_brief(client, sid)
        _generate(client, sid, 0)
        body = _revise(client, sid, 0, "Needs work")
        assert body["current_shot_index"] == 0

    def test_regenerate_after_revise_increments_revision(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _generate(client, sid, 0)
        _revise(client, sid, 0, "Go again")
        body = _generate(client, sid, 0)
        assert body["shots"][0]["revision"] == 1

    def test_revise_empty_feedback_rejected(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _generate(client, sid, 0)
        resp = client.post(
            f"/session/{sid}/shots/0/revise",
            json={"feedback": ""},
        )
        assert resp.status_code == 422

    def test_revise_whitespace_only_feedback_rejected(self, client: TestClient) -> None:
        sid = _create_session(client)
        _submit_brief(client, sid)
        _generate(client, sid, 0)
        resp = client.post(
            f"/session/{sid}/shots/0/revise",
            json={"feedback": "   "},
        )
        assert resp.status_code == 422

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
        End-to-end: create → brief → generate[0] → approve[0]
                    → generate[1] → approve[1].

        Uses a 10-second brief so we get exactly 2 shots (10 ÷ 5 = 2,
        but capped at min 3 by plan_shot_list).  Use 15s to get 3 shots
        and only run through the first two to keep the test concise.
        """
        sid = _create_session(client)
        brief = {**VALID_BRIEF, "duration_seconds": 15}  # 3 shots
        _submit_brief(client, sid, brief)

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

        _generate(client, sid, 0)
        _revise(client, sid, 0, "Needs more energy")
        s = _generate(client, sid, 0)
        assert s["shots"][0]["revision"] == 1
        assert s["shots"][0]["status"] == "ready"

        _approve(client, sid, 0)
        s = _generate(client, sid, 1)
        assert s["shots"][1]["status"] == "ready"
