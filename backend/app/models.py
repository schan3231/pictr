"""
Domain models for Pictr Storyboard Agent.

Design notes:
- All models use Pydantic v2 for validation and serialisation.
- `Session` is the top-level aggregate; the store holds one Session per session_id.
- `Brief` captures the user's creative brief from the INTAKE phase.
- `Shot` represents a single shot card produced during the STORYBOARD phase.
- Timestamps are stored as ISO-8601 strings so they serialise trivially to JSON.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Brief
# ---------------------------------------------------------------------------


class Brief(BaseModel):
    """Creative brief supplied by the user during INTAKE phase."""

    brand_name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Brand or company name.",
    )
    product: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Product or service being advertised.",
    )
    target_audience: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Who the ad is aimed at.",
    )
    tone: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Desired tone (e.g. 'fun and energetic', 'premium and calm').",
    )
    platform: Literal["youtube", "tv"] = Field(
        default="youtube",
        description="Distribution platform.",
    )
    duration_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Desired commercial duration in seconds (5–120).",
    )

    @field_validator("brand_name", "product", "target_audience", "tone", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        """Strip leading/trailing whitespace from string fields."""
        if isinstance(v, str):
            return v.strip()
        return v


# ---------------------------------------------------------------------------
# Shot
# ---------------------------------------------------------------------------

ShotStatus = Literal[
    "draft",          # initial placeholder before generation
    "generating",     # image/text generation in progress
    "ready",          # generation complete, awaiting user review
    "approved",       # user accepted this shot
    "needs_changes",  # user requested revisions
    "failed",         # generation error
]


class Shot(BaseModel):
    """A single shot card in the storyboard."""

    shot_id: str = Field(default_factory=lambda: str(uuid4()))
    index: int = Field(..., ge=0, description="Zero-based position in the shot list.")
    status: ShotStatus = Field(default="draft")
    revision: int = Field(default=0, ge=0, description="Number of regeneration attempts.")

    # Generated content — all optional until the shot is generated.
    image_url: str | None = Field(default=None, description="URL of the generated image.")
    dialogue_text: str | None = Field(default=None, description="Example voiceover / dialogue.")
    sfx_notes: str | None = Field(default=None, description="Sound-effects guidance.")
    camera_notes: str | None = Field(default=None, description="Camera motion / angle notes.")

    # User feedback attached when they request changes.
    user_feedback: str | None = Field(
        default=None,
        max_length=1000,
        description="Feedback from the user when requesting changes.",
    )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

PhaseType = Literal["INTAKE", "STORYBOARD"]


def _utcnow_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


class Session(BaseModel):
    """
    Top-level session aggregate.

    Lifecycle:
    1. Created in INTAKE phase — brief is None until the user submits one.
    2. Transitions to STORYBOARD after the agent builds a shot list from the brief.
    3. Shots are generated sequentially; progression gates on each shot being approved.
    """

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    phase: PhaseType = Field(default="INTAKE")

    brief: Brief | None = Field(default=None)
    shots: list[Shot] = Field(default_factory=list)

    # Pointer to the shot currently being worked on.
    current_shot_index: int = Field(default=0, ge=0)

    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)

    def touch(self) -> None:
        """Update `updated_at` to now (call after any mutation)."""
        self.updated_at = _utcnow_iso()


# ---------------------------------------------------------------------------
# Request / Response schemas for the API layer
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """Body for POST /session. Currently empty — reserved for future metadata."""

    pass


class ReviseRequest(BaseModel):
    """Body for POST /session/{id}/shots/{index}/revise."""

    feedback: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User feedback describing the required changes.",
    )

    @field_validator("feedback", mode="before")
    @classmethod
    def strip_feedback(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class ErrorResponse(BaseModel):
    """
    Consistent error payload shape returned by all HTTPException handlers.

    Clients can reliably check `detail` for a human-readable message.
    """

    detail: str
