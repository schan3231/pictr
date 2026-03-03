"""
Deterministic tool functions called by the agent.

Design notes:
- Tools are pure functions: given inputs → return outputs.  No side-effects on
  the session store; the agent is responsible for persisting results.
- Each tool has a clear, typed interface so it can be registered with ADK's
  function-calling mechanism with minimal glue.
- The image generation tool is a STUB that returns a placeholder URL.  The
  function signature and return type are intentionally final so swapping in a
  real provider (e.g. Gemini Imagen, DALL-E) requires only the body.
"""

from __future__ import annotations

import math
from typing import Optional

from backend.app.models import Brief, Shot


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
        f"Social proof — happy users or testimonial moment.",
        f"Brand integration — logo + tagline introduced naturally.",
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
    feedback: Optional[str] = None,
) -> Shot:
    """
    Populate a Shot with generated content.

    STUB IMPLEMENTATION:
        Returns deterministic placeholder content so the rest of the pipeline
        can be built and tested without a live image API.

    Production replacement:
        Replace `_stub_image_url` and the text fields with calls to:
        - Gemini Imagen / DALL-E / Stability for images
        - Gemini / Claude for narrative text
        The function signature must NOT change.

    Args:
        shot:        The Shot to populate (not mutated — a new Shot is returned).
        brief:       The session's brief (used to contextualise copy).
        description: High-level description for this shot from the shot plan.
        feedback:    Optional revision feedback from the user.

    Returns:
        A new Shot with status="ready" and all content fields populated.
    """
    revision_note = f" [Revision {shot.revision + 1} — feedback: {feedback}]" if feedback else ""

    populated = shot.model_copy(
        update={
            "status": "ready",
            "revision": shot.revision + (1 if feedback else 0),
            "image_url": _stub_image_url(shot.index, shot.revision),
            "dialogue_text": (
                f"[{brief.brand_name}] {description}{revision_note} "
                f"— crafted for {brief.target_audience} with a {brief.tone} feel."
            ),
            "sfx_notes": _stub_sfx(shot.index),
            "camera_notes": _stub_camera(shot.index),
            "user_feedback": feedback,
        }
    )
    return populated


# ---------------------------------------------------------------------------
# Private stub helpers
# ---------------------------------------------------------------------------


def _stub_image_url(index: int, revision: int) -> str:
    """
    Return a stable placeholder image URL.

    Uses picsum.photos with a deterministic seed so the same shot always
    returns the same placeholder, and revisions return a different one.
    """
    seed = index * 100 + revision
    return f"https://picsum.photos/seed/{seed}/1280/720"


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
