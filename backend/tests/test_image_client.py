"""
Unit tests for ImageClient and generate_shot_card image integration.

All tests that touch ImageClient use unittest.mock so no real Vertex AI
calls are made.  The full test suite remains fast and deterministic.

Integration tests (against real Vertex AI) are guarded by the
RUN_IMAGE_TESTS environment variable and are skipped in CI by default:

    RUN_IMAGE_TESTS=1 pytest backend/tests/test_image_client.py -k integration
"""

from __future__ import annotations

import base64
import os
from unittest.mock import MagicMock, patch

import pytest

from backend.app.image_client import ImageClient, ImageGenerationError
from backend.app.models import Brief, Shot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BRIEF = Brief(
    brand_name="Acme",
    product="Widget",
    target_audience="Everyone",
    tone="fun",
    platform="youtube",
    duration_seconds=30,
)

_SHOT = Shot(index=0)

FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # minimal fake PNG header


def _make_client(*, project: str = "") -> ImageClient:
    """
    Return an ImageClient with an isolated settings patch.

    Passing project="" produces a disabled (stub-mode) client.
    Passing a non-empty project produces an enabled client, but vertexai.init
    is also patched so no real network call happens.
    """
    with patch("backend.app.image_client.settings") as mock_settings:
        mock_settings.google_cloud_project = project
        mock_settings.google_cloud_location = "us-central1"
        mock_settings.image_model = "imagen-3.0-generate-001"

        if project:
            with patch("backend.app.image_client.vertexai", create=True):
                return ImageClient()
        return ImageClient()


# ---------------------------------------------------------------------------
# Stub mode (no GCP project configured)
# ---------------------------------------------------------------------------


class TestStubMode:
    def test_returns_picsum_url_when_disabled(self) -> None:
        client = _make_client(project="")
        url = client.generate_image("a sunny beach", _stub_seed=42)
        assert url == "https://picsum.photos/seed/42/1280/720"

    def test_stub_seed_zero_by_default(self) -> None:
        client = _make_client(project="")
        url = client.generate_image("prompt")
        assert url == "https://picsum.photos/seed/0/1280/720"

    def test_stub_never_raises(self) -> None:
        """Stub mode must NEVER raise ImageGenerationError."""
        client = _make_client(project="")
        # Should not raise even with weird input.
        url = client.generate_image("", _stub_seed=999)
        assert url.startswith("https://picsum.photos")

    def test_disabled_does_not_call_vertexai(self) -> None:
        with patch("backend.app.image_client.settings") as mock_settings:
            mock_settings.google_cloud_project = ""
            with patch("vertexai.init") as mock_init:
                ImageClient()
                mock_init.assert_not_called()


# ---------------------------------------------------------------------------
# Enabled mode — happy path (mocked Vertex AI)
# ---------------------------------------------------------------------------


class TestEnabledModeHappyPath:
    def _make_enabled_client_with_model(self, fake_bytes: bytes) -> ImageClient:
        """Return an enabled ImageClient whose model returns fake_bytes."""
        with patch("backend.app.image_client.settings") as mock_settings:
            mock_settings.google_cloud_project = "my-project"
            mock_settings.google_cloud_location = "us-central1"
            mock_settings.image_model = "imagen-3.0-generate-001"
            with patch("backend.app.image_client.vertexai", create=True):
                client = ImageClient()

        # Wire up the lazy model via _get_model patch.
        fake_image = MagicMock()
        fake_image._image_bytes = fake_bytes
        fake_model = MagicMock()
        fake_model.generate_images.return_value = [fake_image]
        client._model = fake_model  # bypass lazy init for the test
        return client

    def test_returns_base64_data_url(self) -> None:
        client = self._make_enabled_client_with_model(FAKE_PNG_BYTES)
        url = client.generate_image("a sunrise")
        assert url.startswith("data:image/png;base64,")

    def test_base64_content_matches_bytes(self) -> None:
        client = self._make_enabled_client_with_model(FAKE_PNG_BYTES)
        url = client.generate_image("a sunrise")
        b64_part = url.removeprefix("data:image/png;base64,")
        decoded = base64.b64decode(b64_part)
        assert decoded == FAKE_PNG_BYTES

    def test_prompt_is_forwarded_to_model(self) -> None:
        client = self._make_enabled_client_with_model(FAKE_PNG_BYTES)
        client.generate_image("my specific prompt")
        client._model.generate_images.assert_called_once_with(
            prompt="my specific prompt",
            number_of_images=1,
        )


# ---------------------------------------------------------------------------
# Enabled mode — error classification
# ---------------------------------------------------------------------------


class TestErrorClassification:
    def _client_that_raises(self, exc: Exception) -> ImageClient:
        with patch("backend.app.image_client.settings") as mock_settings:
            mock_settings.google_cloud_project = "my-project"
            mock_settings.google_cloud_location = "us-central1"
            mock_settings.image_model = "imagen-3.0-generate-001"
            with patch("backend.app.image_client.vertexai", create=True):
                client = ImageClient()
        fake_model = MagicMock()
        fake_model.generate_images.side_effect = exc
        client._model = fake_model
        return client

    def test_permission_denied_raises_image_generation_error(self) -> None:
        from google.api_core.exceptions import PermissionDenied

        client = self._client_that_raises(PermissionDenied("denied"))
        with pytest.raises(ImageGenerationError) as exc_info:
            client.generate_image("prompt")
        msg = exc_info.value.args[0].lower()
        assert "authorized" in msg or "service account" in msg or "vertex ai api" in msg

    def test_deadline_exceeded_raises_image_generation_error(self) -> None:
        from google.api_core.exceptions import DeadlineExceeded

        client = self._client_that_raises(DeadlineExceeded("timed out"))
        with pytest.raises(ImageGenerationError) as exc_info:
            client.generate_image("prompt")
        assert "timed out" in exc_info.value.args[0].lower()

    def test_resource_exhausted_raises_image_generation_error(self) -> None:
        from google.api_core.exceptions import ResourceExhausted

        client = self._client_that_raises(ResourceExhausted("quota"))
        with pytest.raises(ImageGenerationError) as exc_info:
            client.generate_image("prompt")
        assert "quota" in exc_info.value.args[0].lower()

    def test_generic_exception_raises_image_generation_error(self) -> None:
        client = self._client_that_raises(RuntimeError("something weird"))
        with pytest.raises(ImageGenerationError) as exc_info:
            client.generate_image("prompt")
        # Must be generic user-safe message, not the raw RuntimeError text.
        assert "RuntimeError" not in exc_info.value.args[0]
        assert "something weird" not in exc_info.value.args[0]

    def test_error_does_not_expose_internal_details(self) -> None:
        """No SDK class names or internal paths in the user-safe message."""
        client = self._client_that_raises(ValueError("internal/path/to/secret"))
        with pytest.raises(ImageGenerationError) as exc_info:
            client.generate_image("prompt")
        assert "internal" not in exc_info.value.args[0]
        assert "secret" not in exc_info.value.args[0]


# ---------------------------------------------------------------------------
# tools.generate_shot_card — image failure → shot.status="failed"
# ---------------------------------------------------------------------------


class TestShotCardImageFailure:
    def test_failed_shot_on_image_generation_error(self) -> None:
        """
        When ImageGenerationError is raised, generate_shot_card must return
        a Shot with status='failed' rather than propagating the exception.
        """
        from backend.app.tools import generate_shot_card

        with patch("backend.app.tools.image_client") as mock_client:
            mock_client.generate_image.side_effect = ImageGenerationError(
                "Image generation timed out. Please try again."
            )
            result = generate_shot_card(_SHOT, _BRIEF, "Establishing shot")

        assert result.status == "failed"
        assert "timed out" in (result.dialogue_text or "").lower()

    def test_failed_shot_does_not_populate_image_url(self) -> None:
        from backend.app.tools import generate_shot_card

        with patch("backend.app.tools.image_client") as mock_client:
            mock_client.generate_image.side_effect = ImageGenerationError("error")
            result = generate_shot_card(_SHOT, _BRIEF, "Scene")

        assert result.image_url is None

    def test_failed_shot_preserves_shot_id(self) -> None:
        from backend.app.tools import generate_shot_card

        with patch("backend.app.tools.image_client") as mock_client:
            mock_client.generate_image.side_effect = ImageGenerationError("error")
            result = generate_shot_card(_SHOT, _BRIEF, "Scene")

        assert result.shot_id == _SHOT.shot_id

    def test_successful_generation_sets_ready(self) -> None:
        from backend.app.tools import generate_shot_card

        with patch("backend.app.tools.image_client") as mock_client:
            mock_client.generate_image.return_value = "data:image/png;base64,abc"
            result = generate_shot_card(_SHOT, _BRIEF, "Scene")

        assert result.status == "ready"
        assert result.image_url == "data:image/png;base64,abc"


# ---------------------------------------------------------------------------
# Integration tests (skipped unless RUN_IMAGE_TESTS=1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_IMAGE_TESTS") != "1",
    reason="Set RUN_IMAGE_TESTS=1 to run integration tests against real Vertex AI",
)
class TestImageClientIntegration:
    def test_real_imagen_returns_base64_data_url(self) -> None:
        """
        Requires:
          - GOOGLE_CLOUD_PROJECT env var set
          - gcloud auth application-default login completed
          - Vertex AI API enabled on the project
        """
        from backend.app.image_client import image_client as real_client

        url = real_client.generate_image(
            "A professional advertisement photograph of a coffee mug on a wooden desk."
        )
        assert url.startswith("data:image/png;base64,"), f"Unexpected URL format: {url[:80]}"
        # Verify the base64 decodes without error.
        b64 = url.removeprefix("data:image/png;base64,")
        decoded = base64.b64decode(b64)
        assert len(decoded) > 1000, "Decoded image is suspiciously small"
