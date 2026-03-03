"""
Tests for session lifecycle endpoints:
  POST /session  — create
  GET  /session/{id}  — read
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


class TestCreateSession:
    def test_create_returns_201(self, client: TestClient) -> None:
        response = client.post("/session")
        assert response.status_code == 201

    def test_create_returns_valid_session_id(self, client: TestClient) -> None:
        body = client.post("/session").json()
        session_id = body.get("session_id")
        # Must be a valid UUID4.
        parsed = uuid.UUID(session_id, version=4)
        assert str(parsed) == session_id

    def test_create_phase_is_intake(self, client: TestClient) -> None:
        body = client.post("/session").json()
        assert body["phase"] == "INTAKE"

    def test_create_initial_shots_empty(self, client: TestClient) -> None:
        body = client.post("/session").json()
        assert body["shots"] == []

    def test_create_current_shot_index_zero(self, client: TestClient) -> None:
        body = client.post("/session").json()
        assert body["current_shot_index"] == 0

    def test_create_has_timestamps(self, client: TestClient) -> None:
        body = client.post("/session").json()
        assert "created_at" in body
        assert "updated_at" in body

    def test_each_session_has_unique_id(self, client: TestClient) -> None:
        id_a = client.post("/session").json()["session_id"]
        id_b = client.post("/session").json()["session_id"]
        assert id_a != id_b


class TestGetSession:
    def test_get_existing_session(self, client: TestClient) -> None:
        created = client.post("/session").json()
        session_id = created["session_id"]

        response = client.get(f"/session/{session_id}")
        assert response.status_code == 200
        assert response.json()["session_id"] == session_id

    def test_get_returns_same_state(self, client: TestClient) -> None:
        created = client.post("/session").json()
        fetched = client.get(f"/session/{created['session_id']}").json()
        # Core fields must match.
        assert fetched["session_id"] == created["session_id"]
        assert fetched["phase"] == created["phase"]
        assert fetched["shots"] == created["shots"]

    def test_get_missing_session_returns_404(self, client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        response = client.get(f"/session/{fake_id}")
        assert response.status_code == 404

    def test_get_missing_session_error_shape(self, client: TestClient) -> None:
        """Error payload must have a 'detail' key (consistent error shape)."""
        response = client.get(f"/session/{uuid.uuid4()}")
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)


class TestSessionStore:
    """Low-level tests against the store directly (unit tests, not integration)."""

    def test_store_count_increases_on_create(self, client: TestClient) -> None:
        from backend.app import main as m

        before = m.store.count()
        client.post("/session")
        after = m.store.count()
        assert after == before + 1

    def test_store_get_returns_none_for_unknown(self) -> None:
        from backend.app.store import SessionStore

        s = SessionStore()
        assert s.get("nonexistent") is None

    def test_store_create_and_retrieve(self) -> None:
        from backend.app.models import Session
        from backend.app.store import SessionStore

        s = SessionStore()
        session = Session()
        s.create(session)
        retrieved = s.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_store_returns_deep_copy(self) -> None:
        """Mutating a retrieved session must not corrupt stored state."""
        from backend.app.models import Session
        from backend.app.store import SessionStore

        s = SessionStore()
        session = Session()
        s.create(session)

        copy = s.get(session.session_id)
        assert copy is not None
        copy.phase = "STORYBOARD"  # mutate the copy

        # Original in store should still be INTAKE.
        stored = s.get(session.session_id)
        assert stored is not None
        assert stored.phase == "INTAKE"
