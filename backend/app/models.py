"""
Domain models for Pictr Storyboard Agent.

Design notes:
- All models use Pydantic v2 for validation and serialisation.
- `Session` is the top-level aggregate; the store holds one Session per session_id.
- `Brief` captures the user's creative brief from the INTAKE phase.
- `ChatMessage` / `StoryboardPlan` are produced during the PLANNING phase.
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
# Planning phase models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single turn in the planning conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class Beat(BaseModel):
    """A narrative beat in the storyboard arc."""

    index: int = Field(..., ge=0)
    name: str
    description: str


class PlannedShot(BaseModel):
    """AI-generated intent for a single shot, produced during PLANNING phase."""

    index: int = Field(..., ge=0, description="Zero-based position in the shot list.")
    short_title: str = Field(..., description="Concise title for this shot.")
    purpose: str = Field(..., description="Narrative purpose within the overall arc.")
    visual_description: str = Field(..., description="What the camera sees.")
    key_action: str = Field(..., description="Primary action or event in the shot.")
    dialogue_hint: str | None = Field(default=None, description="Suggested spoken words.")
    sfx_hint: str | None = Field(default=None, description="Suggested sound effects.")
    camera_hint: str | None = Field(default=None, description="Camera movement guidance.")
    image_prompt: str = Field(
        ...,
        description="Detailed Imagen prompt for this shot; used verbatim for image generation.",
    )


class StoryboardPlan(BaseModel):
    """Full AI-generated storyboard plan produced at the end of PLANNING phase."""

    title: str = Field(..., description="Title of this commercial.")
    logline: str = Field(..., description="One-sentence summary of the ad narrative.")
    target_audience: str | None = Field(default=None)
    tone: str | None = Field(default=None)
    beats: list[Beat] = Field(default_factory=list, description="Narrative beats.")
    shots: list[PlannedShot] = Field(..., description="Per-shot plan, in order.")


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

    # Plan-provided Imagen prompt (set when plan is approved; used by tools.py).
    image_prompt: str | None = Field(
        default=None,
        description="Detailed Imagen prompt from the storyboard plan.",
    )

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

PhaseType = Literal["INTAKE", "PLANNING", "STORYBOARD"]


def _utcnow_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


class Session(BaseModel):
    """
    Top-level session aggregate.

    Lifecycle:
    1. Created in INTAKE phase — brief is None until the user submits one.
    2. Transitions to PLANNING after brief submitted — user chats with AI planner.
    3. Transitions to STORYBOARD after plan is approved — shots created from plan.
    4. Shots are generated sequentially; progression gates on each shot being approved.
    """

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    phase: PhaseType = Field(default="INTAKE")

    brief: Brief | None = Field(default=None)

    # PLANNING phase state.
    planning_messages: list[ChatMessage] = Field(default_factory=list)
    plan: StoryboardPlan | None = Field(default=None)
    plan_status: Literal["none", "draft", "approved"] = Field(default="none")

    # STORYBOARD phase state.
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


class PlanningChatRequest(BaseModel):
    """Body for POST /session/{id}/planning/message."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User message to the AI planner.",
    )

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


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
