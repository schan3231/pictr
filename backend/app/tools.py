"""
Deterministic tool functions called by the agent.

Design notes:
- Tools are pure functions: given inputs → return outputs.  No side-effects on
  the session store; the agent is responsible for persisting results.
- Each tool has a clear, typed interface so it can be registered with ADK's
  function-calling mechanism with minimal glue.
- Image generation is delegated to ImageClient (image_client.py).  When the
  client is in stub mode (no GCP configured) it returns a picsum placeholder.
  When GCP is configured it returns a base64 data URL from Vertex AI Imagen.
  tools.py is unaware of which mode is active.
"""

from __future__ import annotations

import logging
import math

from backend.app.image_client import ImageGenerationError, image_client
from backend.app.models import Brief, Shot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shot-list planning
# ---------------------------------------------------------------------------


def plan_shot_list(brief: Brief) -> list[dict[str, str | int]]:
    """
    Produce a structured shot list plan given a brief.

    Returns a list of dicts with keys:
        index (int), description (str), duration_seconds (int)

    The number of shots is derived from duration: roughly one shot per 5 seconds,
    capped between 3 and 8 shots.

    This is a rule-based stub; the ADK agent will eventually call an LLM here.
    """
    shots_count = max(3, min(8, math.floor(brief.duration_seconds / 5)))

    # Evenly distribute seconds; last shot absorbs the remainder.
    base_duration = brief.duration_seconds // shots_count
    remainder = brief.duration_seconds % shots_count

    descriptions = _default_descriptions(brief, shots_count)

    plan: list[dict[str, str | int]] = []
    for i in range(shots_count):
        dur = base_duration + (remainder if i == shots_count - 1 else 0)
        plan.append(
            {
                "index": i,
                "description": descriptions[i],
                "duration_seconds": dur,
            }
        )
    return plan


def _default_descriptions(brief: Brief, count: int) -> list[str]:
    """Generate placeholder shot descriptions based on the brief."""
    templates = [
        f"Establishing shot — sets the scene for {brief.brand_name}.",
        f"Product reveal — {brief.product} showcased in ideal setting.",
        f"Benefit demo — audience sees key value delivered to {brief.target_audience}.",
        f"Emotional beat — tone ({brief.tone}) reinforced through character reaction.",
        "Social proof — happy users or testimonial moment.",
        "Brand integration — logo + tagline introduced naturally.",
        f"Call-to-action — clear directive tailored to {brief.platform} viewer.",
        f"Closing logo card — {brief.brand_name} branding with endcard.",
    ]
    # Cycle through templates if count > len(templates).
    return [templates[i % len(templates)] for i in range(count)]


# ---------------------------------------------------------------------------
# Shot card generation
# ---------------------------------------------------------------------------


def generate_shot_card(
    shot: Shot,
    brief: Brief,
    description: str,
    *,
    feedback: str | None = None,
) -> Shot:
    """
    Populate a Shot with generated content.

    Image generation:
        Delegates to ``image_client.generate_image()``.  In stub mode (no GCP
        project configured) a deterministic picsum.photos URL is returned and
        no network call is made.  With GCP configured, a real Vertex AI Imagen
        call is made and the result is encoded as a base64 data URL.

    Failure handling:
        If image generation fails (ImageGenerationError), the Shot is returned
        with status="failed" so the UI can surface the error and offer a retry.
        The remaining text fields are *not* populated on failure to avoid a
        misleading partial result.

    Args:
        shot:        The Shot to populate (not mutated — a new Shot is returned).
        brief:       The session's brief (used to contextualise copy and image).
        description: High-level description for this shot from the shot plan.
        feedback:    Optional revision feedback from the user.

    Returns:
        A new Shot with status="ready" and all content fields populated,
        or status="failed" with dialogue_text containing the error message.
    """
    revision_note = f" [Revision {shot.revision + 1} — feedback: {feedback}]" if feedback else ""
    new_revision = shot.revision + (1 if feedback else 0)

    # Build a rich, structured Imagen prompt from the brief + shot context.
    image_prompt = _build_image_prompt(brief, description, feedback)

    # Pass a deterministic seed so stub mode returns the same placeholder per
    # shot/revision combination.  The seed is ignored by real Imagen.
    stub_seed = shot.index * 100 + shot.revision

    try:
        image_url = image_client.generate_image(image_prompt, _stub_seed=stub_seed)
    except ImageGenerationError as exc:
        # Log the full context server-side; return a clean failure to the caller.
        logger.error(
            "Image generation failed for shot %d (revision %d): %s",
            shot.index,
            shot.revision,
            exc,
        )
        return shot.model_copy(
            update={
                "status": "failed",
                "revision": new_revision,
                "dialogue_text": str(exc),
                "user_feedback": feedback,
            }
        )

    return shot.model_copy(
        update={
            "status": "ready",
            "revision": new_revision,
            "image_url": image_url,
            "dialogue_text": (
                f"[{brief.brand_name}] {description}{revision_note} "
                f"— crafted for {brief.target_audience} with a {brief.tone} feel."
            ),
            "sfx_notes": _stub_sfx(shot.index),
            "camera_notes": _stub_camera(shot.index),
            "user_feedback": feedback,
        }
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_image_prompt(brief: Brief, description: str, feedback: str | None) -> str:
    """
    Construct a detailed Imagen prompt from the brief and shot description.

    The prompt is structured to produce professional advertising imagery.
    The "no text or logos" instruction avoids Imagen's tendency to render
    unreadable placeholder text in image content.
    """
    parts = [
        f"A professional commercial advertisement photograph for {brief.brand_name},",
        f"showcasing {brief.product}.",
        f"Scene: {description}",
        f"Tone and mood: {brief.tone}.",
        f"Target audience: {brief.target_audience}.",
        "Style: cinematic, high-quality advertising photography, clean composition.",
        "No text, logos, or watermarks in the image.",
    ]
    if feedback:
        parts.append(f"Additional direction: {feedback}.")
    return " ".join(parts)


def _stub_sfx(index: int) -> str:
    templates = [
        "Gentle ambient music fades in.",
        "Upbeat product jingle begins.",
        "Crowd cheering in the background.",
        "Soft emotional piano.",
        "Narrator voiceover continues over subtle beat.",
        "Brand sonic logo plays.",
        "Action sound effect; music swells.",
        "Silence → then brand sting.",
    ]
    return templates[index % len(templates)]


def _stub_camera(index: int) -> str:
    templates = [
        "Wide establishing shot, slow push-in.",
        "Medium close-up, product at hero angle.",
        "Over-shoulder POV on talent.",
        "Tight close-up on face; rack focus.",
        "Steadicam follow shot.",
        "Static frame — logo centred.",
        "Drone pull-back reveal.",
        "Freeze frame → title card.",
    ]
    return templates[index % len(templates)]
