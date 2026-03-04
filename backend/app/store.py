"""
In-memory session store.

Design notes:
- A plain dict protected by a threading.Lock is sufficient for a single-process
  MVP running under Uvicorn (single or multi-threaded with --workers 1).
- For multi-worker or multi-process deployments, swap this module's backend to
  Redis or a shared DB — the public interface (create / get / update / delete)
  stays the same so callers need no changes.
- `_lock` guards all mutations; reads that need a consistent snapshot also acquire
  the lock so we never hand out a partially-mutated Session.
"""

from __future__ import annotations

import threading

from backend.app.models import Session


class SessionStore:
    """Thread-safe in-memory store keyed by session_id."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create(self, session: Session) -> Session:
        """
        Persist a new session.

        Raises:
            ValueError: if a session with the same session_id already exists.
        """
        with self._lock:
            if session.session_id in self._sessions:
                raise ValueError(f"Session '{session.session_id}' already exists.")
            # Store a copy so callers cannot mutate the stored object directly.
            self._sessions[session.session_id] = session.model_copy(deep=True)
        return session

    def update(self, session: Session) -> Session:
        """
        Replace an existing session's state.

        Callers are responsible for calling `session.touch()` before passing it here
        so that `updated_at` reflects the latest mutation.

        Raises:
            KeyError: if session_id is not found.
        """
        with self._lock:
            if session.session_id not in self._sessions:
                raise KeyError(f"Session '{session.session_id}' not found.")
            self._sessions[session.session_id] = session.model_copy(deep=True)
        return session

    def delete(self, session_id: str) -> None:
        """
        Remove a session.  No-op if not found.
        """
        with self._lock:
            self._sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> Session | None:
        """
        Return a deep copy of the session, or None if not found.

        Returning a copy ensures the caller cannot accidentally mutate stored state.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return session.model_copy(deep=True)

    def count(self) -> int:
        """Return the number of live sessions (useful for monitoring / tests)."""
        with self._lock:
            return len(self._sessions)


# ---------------------------------------------------------------------------
# Module-level singleton
#
# FastAPI routers import `store` directly.  Tests can replace it with a fresh
# SessionStore() instance via dependency injection if needed.
# ---------------------------------------------------------------------------

store = SessionStore()
