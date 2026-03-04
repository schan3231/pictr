"""
Session store implementations.

InMemorySessionStore (SessionStore): thread-safe dict.  Default — no GCP needed.
FirestoreSessionStore: persists to a named Google Cloud Firestore database.
  Enable with USE_FIRESTORE=true.

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

from google.cloud import firestore

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


class FirestoreSessionStore(SessionStore):
    """
    Firestore-backed session store.

    Inherits SessionStore's interface so it can be used anywhere a SessionStore
    is expected (e.g. StoryboardAgent) without type-annotation changes.

    All session data is serialized via Pydantic's model_dump(mode='json') and
    deserialized via Session.model_validate(), so nested models round-trip cleanly.
    """

    def __init__(self, project: str, database: str, collection: str) -> None:
        # Do NOT call super().__init__() — the in-memory dict/lock are not used.
        self._client: firestore.Client = firestore.Client(
            project=project, database=database
        )
        self._collection = self._client.collection(collection)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create(self, session: Session) -> Session:
        self._collection.document(session.session_id).set(
            session.model_dump(mode="json")
        )
        return session

    def update(self, session: Session) -> Session:
        doc_ref = self._collection.document(session.session_id)
        if not doc_ref.get().exists:
            raise KeyError(f"Session '{session.session_id}' not found.")
        doc_ref.set(session.model_dump(mode="json"))
        return session

    def delete(self, session_id: str) -> None:
        self._collection.document(session_id).delete()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> Session | None:
        snap = self._collection.document(session_id).get()
        if not snap.exists:
            return None
        return Session.model_validate(snap.to_dict())

    def count(self) -> int:
        # Firestore does not offer a cheap in-process count.
        # Returns 0 — this field is used for monitoring/tests only.
        return 0


# ---------------------------------------------------------------------------
# Module-level singleton
#
# FastAPI routers import `store` directly.  Tests replace it with a fresh
# SessionStore() instance via conftest.py monkey-patching.
# ---------------------------------------------------------------------------


def _make_store() -> SessionStore:
    from backend.app.config import settings  # local import avoids circular dependency

    if settings.use_firestore:
        return FirestoreSessionStore(
            project=settings.google_cloud_project,
            database=settings.firestore_database,
            collection=settings.firestore_collection,
        )
    return SessionStore()


store = _make_store()
