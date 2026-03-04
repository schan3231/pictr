"""
Gemini LLM client for Pictr Storyboard Agent — planning phase.

Architecture boundary:
    agent.py → llm_client.py → Vertex AI Gemini (google-genai SDK)

Design decisions:
    - Lazy initialisation: the Gemini client is created on first use so startup
      is not blocked by GCP credential checks.
    - Stub mode: when settings.google_cloud_project is empty the client raises
      LLMGenerationError rather than making network calls.  The planning phase
      endpoints return 503 in that case, which is honest (the upstream service is
      unavailable in this configuration).
    - Error handling: all SDK exceptions are mapped to LLMGenerationError with
      user-safe messages.  No raw stack traces ever reach callers.
    - JSON extraction: generate_plan() requests structured JSON from the model and
      parses it with Pydantic.  Markdown fences and surrounding prose are stripped
      before parsing so minor formatting variations do not cause failures.

Swapping providers:
    To replace Gemini with another LLM only this file needs to change.
    agent.py calls chat() and generate_plan() and is otherwise unaware of the
    underlying provider.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import TYPE_CHECKING, Any

from backend.app.config import settings

if TYPE_CHECKING:
    from backend.app.models import Brief, ChatMessage, StoryboardPlan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception — never expose SDK internals to callers
# ---------------------------------------------------------------------------


class LLMGenerationError(Exception):
    """
    Raised when LLM generation fails for any reason.

    The message is always user-safe (no credentials, paths, or stack traces).
    """


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_PLANNING_SYSTEM_PROMPT_TEMPLATE = """\
You are a creative director helping plan a 30-second commercial advertisement.

Brief:
  Brand: {brand_name}
  Product: {product}
  Target audience: {target_audience}
  Tone: {tone}
  Platform: {platform}

Your role is to brainstorm the story arc, key emotional beats, and shot-by-shot
visual intent with the user.  Ask clarifying questions, suggest concrete ideas,
and guide the conversation toward a compelling 30-second narrative.

Keep your replies concise and actionable (2-4 sentences maximum).
Do NOT generate a structured plan — just have a creative conversation.
"""

_PLAN_GENERATION_SYSTEM_PROMPT_TEMPLATE = """\
You are a creative director finalising the storyboard plan for a 30-second
commercial advertisement based on the brief and the conversation history.

Brief:
  Brand: {brand_name}
  Product: {product}
  Target audience: {target_audience}
  Tone: {tone}
  Platform: {platform}
  Duration: {duration_seconds} seconds

Generate a complete storyboard plan as a single JSON object.
The JSON MUST conform exactly to this schema (no extra keys, no missing required keys):

{{
  "title": "<string>",
  "logline": "<one-sentence narrative summary>",
  "target_audience": "<string or null>",
  "tone": "<string or null>",
  "beats": [
    {{"index": 0, "name": "<string>", "description": "<string>"}},
    ...
  ],
  "shots": [
    {{
      "index": 0,
      "short_title": "<string>",
      "purpose": "<narrative purpose>",
      "visual_description": "<what the camera sees>",
      "key_action": "<primary action or event>",
      "dialogue_hint": "<spoken words or null>",
      "sfx_hint": "<sound effects or null>",
      "camera_hint": "<camera movement or null>",
      "image_prompt": "<detailed Imagen prompt for professional advertising photography>"
    }},
    ...
  ]
}}

Requirements:
- Include 3-8 shots proportional to the {duration_seconds}-second duration.
- Each image_prompt must be a self-contained, detailed description suitable for
  an AI image generation model producing professional advertising photography.
- Output ONLY the JSON object.  No markdown fences, no prose, no explanation.
"""


# ---------------------------------------------------------------------------
# GeminiClient
# ---------------------------------------------------------------------------


class GeminiClient:
    """
    Thin wrapper around the Google Gen AI SDK for Vertex AI Gemini.

    Usage:
        from backend.app.llm_client import llm_client
        text = llm_client.chat(messages, system_prompt)
        plan = llm_client.generate_plan(brief, messages)
    """

    def __init__(self) -> None:
        self._enabled: bool = bool(settings.google_cloud_project)
        self._client: Any = None
        self._lock = threading.Lock()

        if self._enabled:
            logger.info(
                "GeminiClient configured (project=%s, location=%s, model=%s)",
                settings.google_cloud_project,
                settings.google_cloud_location,
                settings.gemini_model,
            )
        else:
            logger.info(
                "GOOGLE_CLOUD_PROJECT not set — GeminiClient running in stub mode "
                "(planning endpoints will return 503)."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
    ) -> str:
        """
        Send a conversational turn to Gemini and return the assistant reply.

        Args:
            messages:      Full conversation history so far (includes the new user
                           message appended by the agent before calling this).
            system_prompt: Instructions that frame the model's persona and task.

        Returns:
            The assistant's reply as a plain string.

        Raises:
            LLMGenerationError: if GCP is not configured or generation fails.
        """
        if not self._enabled:
            raise LLMGenerationError(
                "LLM planning is not available: GOOGLE_CLOUD_PROJECT is not set."
            )

        client = self._get_client()

        contents = self._build_contents(messages)
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config={
                    "system_instruction": system_prompt,
                    "temperature": 0.7,
                    "max_output_tokens": 512,
                },
            )
            return response.text.strip()
        except Exception as exc:
            user_message = self._classify_error(exc)
            logger.error("Gemini chat failed: %s — %s", type(exc).__name__, exc)
            raise LLMGenerationError(user_message) from exc

    def generate_plan(
        self,
        brief: Brief,
        conversation: list[ChatMessage],
    ) -> StoryboardPlan:
        """
        Ask Gemini to produce a full StoryboardPlan as structured JSON.

        Args:
            brief:        The user's creative brief.
            conversation: Planning conversation history.

        Returns:
            A validated StoryboardPlan.

        Raises:
            LLMGenerationError: if GCP is not configured, generation fails, or
                                 the model returns invalid JSON / schema.
        """
        from backend.app.models import StoryboardPlan  # noqa: PLC0415 — avoid circular

        if not self._enabled:
            raise LLMGenerationError(
                "LLM planning is not available: GOOGLE_CLOUD_PROJECT is not set."
            )

        client = self._get_client()

        system_prompt = _PLAN_GENERATION_SYSTEM_PROMPT_TEMPLATE.format(
            brand_name=brief.brand_name,
            product=brief.product,
            target_audience=brief.target_audience,
            tone=brief.tone,
            platform=brief.platform,
            duration_seconds=brief.duration_seconds,
        )

        contents = self._build_contents(conversation)
        # Append an explicit instruction as the final user turn.
        contents.append(
            {
                "role": "user",
                "parts": [{"text": "Generate the complete storyboard plan as JSON now."}],
            }
        )

        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config={
                    "system_instruction": system_prompt,
                    "temperature": 0.2,  # low temperature for structured output
                    "max_output_tokens": 4096,
                },
            )
            raw = response.text.strip()
        except Exception as exc:
            user_message = self._classify_error(exc)
            logger.error("Gemini plan generation failed: %s — %s", type(exc).__name__, exc)
            raise LLMGenerationError(user_message) from exc

        # Extract JSON from response (strip markdown fences / surrounding prose).
        json_str = self._extract_json(raw)
        if json_str is None:
            logger.error("Gemini plan response contained no JSON object: %r", raw[:200])
            raise LLMGenerationError(
                "Planner returned invalid output. Please try again."
            )

        try:
            return StoryboardPlan.model_validate_json(json_str)
        except Exception as exc:
            logger.error(
                "StoryboardPlan validation failed: %s\nRaw JSON: %r", exc, json_str[:500]
            )
            raise LLMGenerationError(
                "Planner returned invalid output. Please try again."
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Return the google-genai Client, initialising on first use."""
        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        from google import genai  # noqa: PLC0415

                        self._client = genai.Client(
                            vertexai=True,
                            project=settings.google_cloud_project,
                            location=settings.google_cloud_location,
                        )
                        logger.info("google-genai Client initialised for Vertex AI")
                    except ImportError as exc:
                        raise LLMGenerationError(
                            "google-genai SDK is not installed. "
                            "Run: pip install google-genai"
                        ) from exc
                    except Exception as exc:
                        user_message = self._classify_error(exc)
                        raise LLMGenerationError(user_message) from exc
        return self._client

    @staticmethod
    def _build_contents(messages: list[ChatMessage]) -> list[dict]:
        """Convert ChatMessage list to the google-genai contents format."""
        return [
            {"role": msg.role, "parts": [{"text": msg.content}]}
            for msg in messages
        ]

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """
        Extract the first JSON object from text that may contain markdown fences
        or surrounding prose.

        Returns the JSON string, or None if no object is found.
        """
        # Strip ```json ... ``` or ``` ... ``` fences.
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            return fenced.group(1)

        # Find the outermost { ... } in the raw text.
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        json.loads(candidate)  # validate it's actually JSON
                        return candidate
                    except json.JSONDecodeError:
                        return None
        return None

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """Map a raw SDK / auth exception to a user-safe error string."""
        try:
            from google.api_core import exceptions as gcp_exc  # noqa: PLC0415
            from google.auth.exceptions import (  # noqa: PLC0415
                DefaultCredentialsError,
                TransportError,
            )

            if isinstance(exc, gcp_exc.PermissionDenied):
                return (
                    "LLM planning not authorised. "
                    "Ensure the Vertex AI API is enabled and your service account has "
                    "the 'Vertex AI User' role."
                )
            if isinstance(exc, gcp_exc.Unauthenticated):
                return (
                    "GCP authentication failed. "
                    "Run: gcloud auth application-default login"
                )
            if isinstance(exc, gcp_exc.DeadlineExceeded):
                return "LLM request timed out. Please try again."
            if isinstance(exc, gcp_exc.ResourceExhausted):
                return "LLM quota exceeded. Please wait and try again."
            if isinstance(exc, DefaultCredentialsError):
                return (
                    "No GCP credentials found. "
                    "Run: gcloud auth application-default login"
                )
            if isinstance(exc, TransportError):
                return "Network error reaching Vertex AI. Check your connection."
        except ImportError:
            pass

        return "LLM generation failed unexpectedly. Please try again."


# ---------------------------------------------------------------------------
# Module-level singleton — imported directly by agent.py.
# ---------------------------------------------------------------------------

llm_client = GeminiClient()
