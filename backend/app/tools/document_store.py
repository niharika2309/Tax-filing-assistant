"""In-memory document store. Populated by the FastAPI upload handler, read by
`parse_w2_tool`. Keeping it in-memory here (with a singleton getter) makes
tests trivially injectable — just call `set_store` with a fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol


@dataclass
class StoredDocument:
    document_id: str
    session_id: str
    pdf_bytes: bytes
    source_path: str


class DocumentStore(Protocol):
    def put(self, doc: StoredDocument) -> None: ...
    def get(self, document_id: str) -> StoredDocument | None: ...
    def list_for_session(self, session_id: str) -> list[StoredDocument]: ...


@dataclass
class InMemoryDocumentStore:
    _docs: dict[str, StoredDocument] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def put(self, doc: StoredDocument) -> None:
        with self._lock:
            self._docs[doc.document_id] = doc

    def get(self, document_id: str) -> StoredDocument | None:
        with self._lock:
            return self._docs.get(document_id)

    def list_for_session(self, session_id: str) -> list[StoredDocument]:
        with self._lock:
            return [d for d in self._docs.values() if d.session_id == session_id]


_active_store: DocumentStore = InMemoryDocumentStore()


def get_store() -> DocumentStore:
    return _active_store


def set_store(store: DocumentStore) -> None:
    global _active_store
    _active_store = store
