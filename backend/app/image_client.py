"""
Vertex AI Imagen client for Pictr Storyboard Agent.

Architecture boundary:
  tools.py → image_client.py → Vertex AI (google-cloud-aiplatform SDK)

Design decisions:
  - ImageClient is a lazy singleton: vertexai.init() is called at construction
    time (config only, no network), but the model object is created on the
    first generate_image() call to avoid slowing down startup.
  - Thread safety: a threading.Lock guards model initialisation using
    double-checked locking, so concurrent requests don't race.
  - Stub mode: when settings.google_cloud_project is empty the client returns
    a deterministic picsum.photos placeholder URL instead of raising.  This
    keeps the full pipeline runnable in development without GCP credentials.
  - Error handling: all Vertex SDK exceptions are mapped to ImageGenerationError
    with user-safe messages.  No raw stack traces ever reach callers.

Swapping providers:
  To replace Vertex AI with another image API (DALL-E, Stability, etc.) only
  this file needs to change.  tools.py calls generate_image(prompt) and is
  otherwise unaware of the underlying provider.
"""

from __future__ import annotations

import base64
import logging
import threading
from typing import TYPE_CHECKING, Any

from backend.app.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception — never expose SDK internals to callers
# ---------------------------------------------------------------------------


class ImageGenerationError(Exception):
    """
    Raised when image generation fails for any reason.

    The message is always user-safe (no credentials, paths, or stack traces).
    """


# ---------------------------------------------------------------------------
# ImageClient
# ---------------------------------------------------------------------------


class ImageClient:
    """
    Thin wrapper around Vertex AI Imagen.

    Usage:
        from backend.app.image_client import image_client
        url = image_client.generate_image("a sunny beach")
    """

    def __init__(self) -> None:
        self._enabled: bool = bool(settings.google_cloud_project)
        self._model: Any = None
        self._lock = threading.Lock()

        if self._enabled:
            # vertexai.init() only writes configuration — no network call.
            # If it fails (e.g. SDK not installed), disable gracefully.
            try:
                import vertexai  # noqa: PLC0415

                vertexai.init(
                    project=settings.google_cloud_project,
                    location=settings.google_cloud_location,
                )
                logger.info(
                    "Vertex AI initialised (project=%s, location=%s, model=%s)",
                    settings.google_cloud_project,
                    settings.google_cloud_location,
                    settings.image_model,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "Vertex AI init failed (%s) — falling back to stub images.", exc
                )
                self._enabled = False
        else:
            logger.info(
                "GOOGLE_CLOUD_PROJECT not set — image generation running in stub mode."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_image(self, prompt: str, _stub_seed: int = 0) -> str:
        """
        Generate an image from a text prompt and return it as a URL or data URL.

        Args:
            prompt:      Text description of the desired image.
            _stub_seed:  Seed used for the deterministic placeholder in stub
                         mode (not used when real generation is enabled).

        Returns:
            - Stub mode (no GCP project): ``https://picsum.photos/seed/{seed}/1280/720``
            - Real mode (GCP configured): ``data:image/png;base64,<encoded>``

        Raises:
            ImageGenerationError: if GCP is configured but generation fails.
                                  Never raised in stub mode.
        """
        if not self._enabled:
            return f"https://picsum.photos/seed/{_stub_seed}/1280/720"

        model = self._get_model()

        try:
            response = model.generate_images(
                prompt=prompt,
                number_of_images=1,
                # aspect_ratio="16:9" is available in newer SDK versions;
                # omit here to stay compatible with 1.50+.
            )
            image_bytes: bytes = response[0]._image_bytes  # SDK internal attribute
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            return f"data:image/png;base64,{b64}"

        except Exception as exc:
            # Map all SDK exceptions to user-safe ImageGenerationError.
            # The original exception is logged server-side for debugging.
            user_message = self._classify_error(exc)
            logger.error("Imagen generation failed: %s — %s", type(exc).__name__, exc)
            raise ImageGenerationError(user_message) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_model(self) -> Any:
        """
        Return the ImageGenerationModel, initialising it on first use.

        Uses double-checked locking so concurrent requests don't race during
        the first initialisation.
        """
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        from vertexai.preview.vision_models import (  # noqa: PLC0415
                            ImageGenerationModel,
                        )

                        self._model = ImageGenerationModel.from_pretrained(
                            settings.image_model
                        )
                        logger.info("Loaded Imagen model: %s", settings.image_model)
                    except Exception as exc:
                        raise ImageGenerationError(
                            f"Failed to load image model '{settings.image_model}'. "
                            "Check that the Vertex AI API is enabled and the model name is correct."
                        ) from exc
        return self._model

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """
        Map a raw SDK exception to a user-safe error string.

        Import google.api_core lazily so the module loads fine even if
        google-cloud-aiplatform is not installed (stub-only deployments).
        """
        try:
            from google.api_core import exceptions as gcp_exc  # noqa: PLC0415
            from google.auth.exceptions import (  # noqa: PLC0415
                DefaultCredentialsError,
                TransportError,
            )

            if isinstance(exc, gcp_exc.PermissionDenied):
                return (
                    "Image generation not authorized. "
                    "Ensure the Vertex AI API is enabled and your service account has "
                    "the 'Vertex AI User' role."
                )
            if isinstance(exc, gcp_exc.Unauthenticated):
                return (
                    "GCP authentication failed. "
                    "Run: gcloud auth application-default login"
                )
            if isinstance(exc, gcp_exc.DeadlineExceeded):
                return "Image generation timed out. Please try again."
            if isinstance(exc, gcp_exc.ResourceExhausted):
                return "Image generation quota exceeded. Please wait and try again."
            if isinstance(exc, DefaultCredentialsError):
                return (
                    "No GCP credentials found. "
                    "Run: gcloud auth application-default login"
                )
            if isinstance(exc, TransportError):
                return "Network error reaching Vertex AI. Check your connection."
        except ImportError:
            pass  # google-cloud-aiplatform not installed — fall through to generic

        return "Image generation failed unexpectedly. Please try again."


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly in tools.py.
# ---------------------------------------------------------------------------

image_client = ImageClient()
