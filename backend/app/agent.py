"""
Agent orchestration layer — Pictr Storyboard Agent.

Architecture boundary:
    API layer (main.py) → Agent (this file) → Tools (tools.py) → Store (store.py)

The agent owns workflow logic:
  - Interprets the current session phase and enforces legal transitions.
  - Calls tool functions to do real work (shot planning, card generation).
  - Persists results back to the store.
  - Returns the updated session to the API layer.

ADK integration note:
  This module currently contains a hand-rolled orchestrator that mirrors the
  logic an ADK agent would implement.  When the ADK integration is wired in
  (next milestone), replace `StoryboardAgent.run_turn()` with the ADK runner
  and register `plan_shot_list` / `generate_shot_card` as ADK tool functions.
  The rest of the codebase (API, store, models) does not need to change.
"""

from __future__ import annotations

import logging

from backend.app.models import Brief, Session, Shot
from backend.app.store import SessionStore
from backend.app.store import store as _default_store
from backend.app.tools import generate_shot_card, plan_shot_list

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
        Accept the user's creative brief and build the initial shot list.

        Transitions the session from INTAKE → STORYBOARD.

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

        # Plan shot list (stub / rule-based for now).
        plan = plan_shot_list(brief)

        # Build Shot stubs — content will be filled in during STORYBOARD phase.
        shots = [
            Shot(index=item["index"])  # type: ignore[arg-type]
            for item in plan
        ]

        # Transition to STORYBOARD.
        session.brief = brief
        session.shots = shots
        session.phase = "STORYBOARD"
        session.current_shot_index = 0
        session.touch()

        self._store.update(session)
        logger.info(
            "Session %s: transitioned to STORYBOARD with %d shots", session_id, len(shots)
        )
        return session

    # ------------------------------------------------------------------
    # Phase: STORYBOARD
    # ------------------------------------------------------------------

    def generate_current_shot(self, session_id: str) -> Session:
        """
        Generate the Shot Card for the current shot in the sequence.

        Sequential gating: the agent will not generate shot N+1 until shot N
        is in status="approved".

        Raises:
            AgentError: if phase is wrong, brief is missing, or the current shot
                        is not in a generatable state.
        """
        session = self._get_or_raise(session_id)
        self._require_storyboard_phase(session)

        idx = session.current_shot_index
        if idx >= len(session.shots):
            raise AgentError("All shots have already been generated.")

        shot = session.shots[idx]

        # Only generate if the shot is in a generatable state.
        if shot.status not in ("draft", "needs_changes"):
            raise AgentError(
                f"Shot {idx} has status '{shot.status}'; "
                "it must be 'draft' or 'needs_changes' to generate."
            )

        assert session.brief is not None  # guaranteed by submit_brief
        # Retrieve the planned description (stored in the shot's dialogue as a
        # placeholder until generation; for now derive from index).
        description = f"Shot {idx + 1} of {len(session.shots)}"

        feedback = shot.user_feedback if shot.status == "needs_changes" else None

        logger.info("Session %s: generating shot %d (revision %d)", session_id, idx, shot.revision)

        populated = generate_shot_card(shot, session.brief, description, feedback=feedback)
        session.shots[idx] = populated
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

        The next call to `generate_current_shot` will pass the feedback to the
        tool so the regeneration is informed by the user's notes.

        Raises:
            AgentError: on phase/index/status violations.
        """
        session = self._get_or_raise(session_id)
        self._require_storyboard_phase(session)
        shot = self._get_shot_or_raise(session, shot_index)

        if shot.status not in ("ready", "needs_changes"):
            raise AgentError(
                f"Shot {shot_index} must be 'ready' or 'needs_changes' to request changes; "
                f"current status: '{shot.status}'."
            )

        shot.status = "needs_changes"
        shot.user_feedback = feedback
        # Reset pointer back to this shot so `generate_current_shot` targets it.
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


# ---------------------------------------------------------------------------
# Module-level singleton — imported by API routes.
# ---------------------------------------------------------------------------

agent = StoryboardAgent()
