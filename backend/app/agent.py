"""
Agent orchestration layer — Pictr Storyboard Agent.

Architecture boundary:
    API layer (main.py) → Agent (this file) → Tools (tools.py) / LLM (llm_client.py) → Store (store.py)

The agent owns workflow logic:
  - Interprets the current session phase and enforces legal transitions.
  - Calls tool functions to do real work (shot card generation).
  - Calls the LLM client for planning-phase conversation and plan generation.
  - Persists results back to the store.
  - Returns the updated session to the API layer.

Phase machine:
    INTAKE  ──(submit_brief)──▶  PLANNING  ──(approve_plan)──▶  STORYBOARD
                                     ↑
                              planning_chat / generate_plan
"""

from __future__ import annotations

import logging

from backend.app.llm_client import LLMGenerationError, llm_client  # noqa: F401
from backend.app.models import Brief, ChatMessage, Session, Shot
from backend.app.store import SessionStore
from backend.app.store import store as _default_store
from backend.app.tools import generate_shot_card

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Raised when the agent cannot fulfill a request due to state constraints."""


class StoryboardAgent:
    """
    Orchestrates the storyboard generation workflow.

    One instance is typically shared for the process lifetime (stateless; all
    state is in the SessionStore).
    """

    def __init__(self, session_store: SessionStore | None = None) -> None:
        # Allow injection for testing; fall back to the module-level singleton.
        self._store = session_store or _default_store

    # ------------------------------------------------------------------
    # Phase: INTAKE
    # ------------------------------------------------------------------

    def submit_brief(self, session_id: str, brief: Brief) -> Session:
        """
        Accept the user's creative brief and transition to PLANNING phase.

        Transitions the session from INTAKE → PLANNING.  Shots are NOT created
        here — they are created later when the user approves the storyboard plan.

        Raises:
            AgentError: if the session is not in INTAKE phase.
            KeyError:   if session_id is not found in the store.
        """
        session = self._get_or_raise(session_id)

        if session.phase != "INTAKE":
            raise AgentError(
                f"Cannot submit brief: session is in phase '{session.phase}', expected 'INTAKE'."
            )

        logger.info("Session %s: submitting brief for '%s'", session_id, brief.brand_name)

        # Seed the conversation with a planner welcome message.
        welcome = ChatMessage(
            role="assistant",
            content=(
                f"Great! I've got your brief for {brief.brand_name}. "
                f"We're creating a {brief.duration_seconds}-second {brief.platform} ad "
                f"for {brief.product}, aimed at {brief.target_audience}. "
                "Let's craft the story arc together. "
                "What key emotion or moment do you want viewers to walk away with?"
            ),
        )

        session.brief = brief
        session.phase = "PLANNING"
        session.planning_messages = [welcome]
        session.touch()

        self._store.update(session)
        logger.info("Session %s: transitioned to PLANNING", session_id)
        return session

    # ------------------------------------------------------------------
    # Phase: PLANNING
    # ------------------------------------------------------------------

    def planning_chat(self, session_id: str, user_message: str) -> Session:
        """
        Process a user message in the planning conversation.

        Appends the user message, calls Gemini for a reply, and appends the
        assistant response.  Raises LLMGenerationError on upstream failure (the
        API layer maps this to 503).

        Raises:
            AgentError:          if the session is not in PLANNING phase.
            KeyError:            if session_id is not found.
            LLMGenerationError:  if the LLM call fails.
        """
        session = self._get_or_raise(session_id)
        self._require_planning_phase(session)

        # Append the user turn.
        session.planning_messages.append(ChatMessage(role="user", content=user_message))

        # Get system prompt and call the LLM.
        assert session.brief is not None
        system_prompt = self._planning_system_prompt(session.brief)
        response_text = llm_client.chat(session.planning_messages, system_prompt)

        # Append the assistant reply.
        session.planning_messages.append(ChatMessage(role="assistant", content=response_text))
        session.touch()

        self._store.update(session)
        logger.info(
            "Session %s: planning chat turn (%d messages total)",
            session_id,
            len(session.planning_messages),
        )
        return session

    def generate_plan(self, session_id: str) -> Session:
        """
        Ask the LLM to produce a full StoryboardPlan from the brief + conversation.

        Sets plan_status="draft" but does NOT create shots or transition phases —
        the user must call approve_plan() to commit the plan.

        Raises:
            AgentError:          if the session is not in PLANNING phase or brief is missing.
            KeyError:            if session_id is not found.
            LLMGenerationError:  if the LLM call fails or returns invalid output.
        """
        session = self._get_or_raise(session_id)
        self._require_planning_phase(session)

        assert session.brief is not None
        logger.info("Session %s: generating storyboard plan", session_id)

        plan = llm_client.generate_plan(session.brief, session.planning_messages)

        session.plan = plan
        session.plan_status = "draft"
        session.touch()

        self._store.update(session)
        logger.info(
            "Session %s: plan drafted with %d shots, %d beats",
            session_id,
            len(plan.shots),
            len(plan.beats),
        )
        return session

    def approve_plan(self, session_id: str) -> Session:
        """
        Approve the current draft plan and transition to STORYBOARD phase.

        Creates Shot objects from the plan's PlannedShot list, storing the
        plan-provided image_prompt on each Shot for use during generation.

        Raises:
            AgentError: if not in PLANNING phase, or no draft plan exists.
            KeyError:   if session_id is not found.
        """
        session = self._get_or_raise(session_id)
        self._require_planning_phase(session)

        if session.plan is None or session.plan_status != "draft":
            raise AgentError(
                "Cannot approve plan: no draft plan exists. "
                "Call POST /planning/plan to generate one first."
            )

        # Build shots from the plan.
        shots = [
            Shot(index=ps.index, image_prompt=ps.image_prompt)
            for ps in session.plan.shots
        ]

        session.shots = shots
        session.phase = "STORYBOARD"
        session.plan_status = "approved"
        session.current_shot_index = 0
        session.touch()

        self._store.update(session)
        logger.info(
            "Session %s: plan approved — transitioned to STORYBOARD with %d shots",
            session_id,
            len(shots),
        )
        return session

    # ------------------------------------------------------------------
    # Phase: STORYBOARD
    # ------------------------------------------------------------------

    def generate_shot(self, session_id: str, shot_index: int) -> Session:
        """
        Generate (or regenerate) the Shot Card for any shot in the sequence.

        Generatable states: draft, needs_changes, failed.
        This allows both sequential first-time generation and retroactive
        regeneration of earlier shots after they've been revised.

        Raises:
            AgentError: if phase is wrong, brief is missing, or the shot is
                        not in a generatable state (ready or approved cannot
                        be regenerated without first requesting changes).
        """
        session = self._get_or_raise(session_id)
        self._require_storyboard_phase(session)
        shot = self._get_shot_or_raise(session, shot_index)

        if shot.status not in ("draft", "needs_changes", "failed"):
            raise AgentError(
                f"Shot {shot_index} has status '{shot.status}'; "
                "it must be 'draft', 'needs_changes', or 'failed' to generate."
            )

        assert session.brief is not None  # guaranteed by submit_brief

        # Use the plan's visual description when available, else a generic label.
        description = f"Shot {shot_index + 1} of {len(session.shots)}"
        if session.plan and shot_index < len(session.plan.shots):
            description = session.plan.shots[shot_index].visual_description

        feedback = shot.user_feedback if shot.status == "needs_changes" else None

        logger.info(
            "Session %s: generating shot %d (revision %d)", session_id, shot_index, shot.revision
        )

        populated = generate_shot_card(shot, session.brief, description, feedback=feedback)
        session.shots[shot_index] = populated
        session.touch()

        self._store.update(session)
        return session

    def approve_shot(self, session_id: str, shot_index: int) -> Session:
        """
        Mark a shot as approved and advance the pointer to the next shot.

        Raises:
            AgentError: on phase/index/status violations.
        """
        session = self._get_or_raise(session_id)
        self._require_storyboard_phase(session)
        shot = self._get_shot_or_raise(session, shot_index)

        if shot.status != "ready":
            raise AgentError(
                f"Shot {shot_index} must be in status 'ready' to approve; "
                f"current status: '{shot.status}'."
            )

        shot.status = "approved"
        session.shots[shot_index] = shot

        # Advance the pointer if this was the current shot.
        if session.current_shot_index == shot_index:
            session.current_shot_index = min(shot_index + 1, len(session.shots))

        session.touch()
        self._store.update(session)
        logger.info("Session %s: shot %d approved", session_id, shot_index)
        return session

    def request_changes(
        self, session_id: str, shot_index: int, feedback: str
    ) -> Session:
        """
        Mark a shot as needing changes and attach user feedback.

        The next call to `generate_shot` will pass the feedback to the
        tool so the regeneration is informed by the user's notes.

        Raises:
            AgentError: on phase/index/status violations.
        """
        session = self._get_or_raise(session_id)
        self._require_storyboard_phase(session)
        shot = self._get_shot_or_raise(session, shot_index)

        if shot.status not in ("ready", "needs_changes", "approved"):
            raise AgentError(
                f"Shot {shot_index} must be 'ready', 'needs_changes', or 'approved' to request changes; "
                f"current status: '{shot.status}'."
            )

        shot.status = "needs_changes"
        shot.user_feedback = feedback
        # Only reset the pointer if this shot is at or ahead of the current position.
        # For retroactive edits on already-approved shots, preserve the pointer so
        # sequential approval of future shots is not disrupted.
        if shot_index >= session.current_shot_index:
            session.current_shot_index = shot_index
        session.shots[shot_index] = shot
        session.touch()

        self._store.update(session)
        logger.info("Session %s: shot %d marked needs_changes", session_id, shot_index)
        return session

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_or_raise(self, session_id: str) -> Session:
        session = self._store.get(session_id)
        if session is None:
            raise KeyError(f"Session '{session_id}' not found.")
        return session

    @staticmethod
    def _require_planning_phase(session: Session) -> None:
        if session.phase != "PLANNING":
            raise AgentError(
                f"Operation requires PLANNING phase; current phase: '{session.phase}'."
            )

    @staticmethod
    def _require_storyboard_phase(session: Session) -> None:
        if session.phase != "STORYBOARD":
            raise AgentError(
                f"Operation requires STORYBOARD phase; current phase: '{session.phase}'."
            )

    @staticmethod
    def _get_shot_or_raise(session: Session, shot_index: int) -> Shot:
        if shot_index < 0 or shot_index >= len(session.shots):
            raise AgentError(
                f"Shot index {shot_index} is out of range (session has {len(session.shots)} shots)."
            )
        return session.shots[shot_index]

    @staticmethod
    def _planning_system_prompt(brief: Brief) -> str:
        from backend.app.llm_client import _PLANNING_SYSTEM_PROMPT_TEMPLATE  # noqa: PLC0415

        return _PLANNING_SYSTEM_PROMPT_TEMPLATE.format(
            brand_name=brief.brand_name,
            product=brief.product,
            target_audience=brief.target_audience,
            tone=brief.tone,
            platform=brief.platform,
        )


# ---------------------------------------------------------------------------
# Module-level singleton — imported by API routes.
# ---------------------------------------------------------------------------

agent = StoryboardAgent()
