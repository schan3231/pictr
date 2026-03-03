"""
Tests for the /health and /echo meta-endpoints.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_health_is_fast(self, client: TestClient) -> None:
        """Health endpoint should respond quickly (basic smoke check)."""
        import time

        start = time.monotonic()
        client.get("/health")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Health check took {elapsed:.2f}s — unexpectedly slow"


class TestEcho:
    def test_echo_returns_payload(self, client: TestClient) -> None:
        payload = {"hello": "world", "number": 42}
        response = client.post("/echo", json=payload)
        assert response.status_code == 200
        assert response.json() == payload

    def test_echo_empty_object(self, client: TestClient) -> None:
        response = client.post("/echo", json={})
        assert response.status_code == 200
        assert response.json() == {}

    def test_echo_invalid_json_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/echo",
            content=b"not-valid-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        body = response.json()
        assert "detail" in body
