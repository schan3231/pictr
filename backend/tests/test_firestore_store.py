"""
Unit tests for FirestoreSessionStore.

Firestore client is fully mocked — no network calls are made.
Patch target: backend.app.store.firestore
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.models import Session
from backend.app.store import FirestoreSessionStore


@pytest.fixture()
def fs_store() -> tuple[FirestoreSessionStore, MagicMock]:
    """
    Return a (FirestoreSessionStore, mock_firestore_client) pair.

    The Firestore module is patched so no real client is created.
    """
    with patch("backend.app.store.firestore") as mock_firestore_module:
        mock_client = MagicMock()
        mock_firestore_module.Client.return_value = mock_client

        store = FirestoreSessionStore(
            project="test-project",
            database="test-db",
            collection="sessions",
        )
        yield store, mock_client


def _doc_ref(mock_client: MagicMock) -> MagicMock:
    """Convenience: return the mock document reference from the client chain."""
    return mock_client.collection.return_value.document.return_value


class TestFirestoreSessionStoreCreate:
    def test_create_calls_set_with_serialized_session(
        self, fs_store: tuple[FirestoreSessionStore, MagicMock]
    ) -> None:
        store, client = fs_store
        session = Session()

        result = store.create(session)

        doc_ref = _doc_ref(client)
        doc_ref.set.assert_called_once_with(session.model_dump(mode="json"))
        assert result is session

    def test_create_uses_session_id_as_document_id(
        self, fs_store: tuple[FirestoreSessionStore, MagicMock]
    ) -> None:
        store, client = fs_store
        session = Session()

        store.create(session)

        client.collection.return_value.document.assert_called_once_with(
            session.session_id
        )


class TestFirestoreSessionStoreGet:
    def test_get_existing_returns_session(
        self, fs_store: tuple[FirestoreSessionStore, MagicMock]
    ) -> None:
        store, client = fs_store
        session = Session()

        snap = MagicMock()
        snap.exists = True
        snap.to_dict.return_value = session.model_dump(mode="json")
        _doc_ref(client).get.return_value = snap

        result = store.get(session.session_id)

        assert result is not None
        assert result.session_id == session.session_id
        assert result.phase == session.phase

    def test_get_missing_returns_none(
        self, fs_store: tuple[FirestoreSessionStore, MagicMock]
    ) -> None:
        store, client = fs_store

        snap = MagicMock()
        snap.exists = False
        _doc_ref(client).get.return_value = snap

        assert store.get("no-such-id") is None


class TestFirestoreSessionStoreUpdate:
    def test_update_existing_calls_set(
        self, fs_store: tuple[FirestoreSessionStore, MagicMock]
    ) -> None:
        store, client = fs_store
        session = Session()

        snap = MagicMock()
        snap.exists = True
        _doc_ref(client).get.return_value = snap

        result = store.update(session)

        _doc_ref(client).set.assert_called_once_with(session.model_dump(mode="json"))
        assert result is session

    def test_update_missing_raises_key_error(
        self, fs_store: tuple[FirestoreSessionStore, MagicMock]
    ) -> None:
        store, client = fs_store
        session = Session()

        snap = MagicMock()
        snap.exists = False
        _doc_ref(client).get.return_value = snap

        with pytest.raises(KeyError, match=session.session_id):
            store.update(session)
