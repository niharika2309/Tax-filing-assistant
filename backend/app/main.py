"""FastAPI entry point — chat endpoint streams LangGraph events as SSE."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from app.agent.checkpointer import build_checkpointer
from app.agent.graph import build_graph
from app.agent.llm import build_llm
from app.agent.state import initial_state
from app.persistence import models as db_models
from app.persistence.db import get_session as get_db_session, init_db
from app.settings import settings
from app.tools.document_store import StoredDocument, get_store


logger = logging.getLogger("uvicorn.error")


# ---- Lifecycle ---------------------------------------------------------------


class _AppState:
    graph: Any = None
    llm: Any = None


_state = _AppState()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "lifecycle.startup model=%s lm_studio_base_url=%s storage_dir=%s",
        settings.model_name,
        settings.lm_studio_base_url,
        settings.storage_dir,
    )
    _state.llm = build_llm()
    async with build_checkpointer() as checkpointer:
        _state.graph = build_graph(_state.llm, checkpointer=checkpointer)
        yield


app = FastAPI(title="Tax Filing Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Pydantic request/response models ----------------------------------------


class CreateSessionResponse(BaseModel):
    session_id: str
    tax_year: int


class ChatRequest(BaseModel):
    message: str


class DocumentResponse(BaseModel):
    document_id: str
    filename: str


class SessionDocumentsResponse(BaseModel):
    documents: list[DocumentResponse]


# ---- Sessions ----------------------------------------------------------------


@app.post("/sessions", response_model=CreateSessionResponse)
def create_session() -> CreateSessionResponse:
    session_id = uuid.uuid4().hex
    with get_db_session() as s:
        s.add(db_models.Session(id=session_id, tax_year=settings.tax_year))
        s.commit()
    (settings.storage_dir / session_id).mkdir(parents=True, exist_ok=True)
    return CreateSessionResponse(session_id=session_id, tax_year=settings.tax_year)


@app.get("/sessions/{session_id}/return")
async def get_return(session_id: str) -> dict:
    """Return the current TaxReturn draft JSON (reads latest checkpoint)."""
    snapshot = await _state.graph.aget_state(_thread_config(session_id))
    if not snapshot or not snapshot.values:
        # No turns yet — return an empty draft.
        st = initial_state(session_id=session_id, tax_year=settings.tax_year)
        return {"return_draft": st["return_draft"].model_dump(mode="json"), "finalized": False}
    draft = snapshot.values.get("return_draft")
    return {
        "return_draft": draft.model_dump(mode="json") if draft else None,
        "finalized": bool(snapshot.values.get("finalized")),
        "pending_clarification": snapshot.values.get("pending_clarification"),
    }


# ---- Document upload ---------------------------------------------------------


@app.post("/sessions/{session_id}/documents", response_model=DocumentResponse)
async def upload_document(
    session_id: str,
    file: UploadFile = File(...),
    kind: str = Form(default="w2"),
) -> DocumentResponse:
    if not _session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads accepted")

    document_id = uuid.uuid4().hex
    dest = settings.storage_dir / session_id / f"{document_id}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = await file.read()
    dest.write_bytes(pdf_bytes)

    get_store().put(
        StoredDocument(
            document_id=document_id,
            session_id=session_id,
            pdf_bytes=pdf_bytes,
            source_path=str(dest),
        )
    )

    with get_db_session() as s:
        s.add(
            db_models.Document(
                id=document_id,
                session_id=session_id,
                filename=file.filename,
                source_path=str(dest),
            )
        )
        s.commit()

    return DocumentResponse(document_id=document_id, filename=file.filename)


@app.get("/sessions/{session_id}/documents", response_model=SessionDocumentsResponse)
def list_documents(session_id: str) -> SessionDocumentsResponse:
    with get_db_session() as s:
        rows = s.exec(
            select(db_models.Document).where(db_models.Document.session_id == session_id)
        ).all()
    return SessionDocumentsResponse(
        documents=[DocumentResponse(document_id=r.id, filename=r.filename) for r in rows]
    )


# ---- Chat (SSE) --------------------------------------------------------------


@app.post("/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatRequest):
    if not _session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    trace_id = uuid.uuid4().hex[:10]
    logger.info(
        "chat.request.started trace_id=%s session_id=%s message_chars=%d",
        trace_id,
        session_id,
        len(body.message),
    )

    return EventSourceResponse(
        _stream_chat(session_id, body.message, trace_id=trace_id),
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "X-Trace-Id": trace_id,
        },
    )


async def _stream_chat(
    session_id: str, user_message: str, trace_id: str
) -> AsyncIterator[dict]:
    """Stream LangGraph events to the client as typed SSE messages."""
    started = time.perf_counter()
    stage = "prepare_config"
    event_count = 0
    token_count = 0
    tool_call_count = 0

    config = _thread_config(session_id)

    try:
        stage = "load_checkpoint_state"
        snapshot = await _state.graph.aget_state(config)
        if snapshot is None or not snapshot.values:
            logger.info(
                "chat.stage.ok trace_id=%s session_id=%s stage=%s state=initial",
                trace_id,
                session_id,
                stage,
            )
            base = initial_state(session_id=session_id, tax_year=settings.tax_year)
        else:
            logger.info(
                "chat.stage.ok trace_id=%s session_id=%s stage=%s state=restored",
                trace_id,
                session_id,
                stage,
            )
            base = dict(snapshot.values)
        base["messages"] = [HumanMessage(content=user_message)]

        # Always refresh uploaded_document_ids from DB so agent sees newly uploaded files.
        stage = "load_uploaded_documents"
        with get_db_session() as s:
            doc_rows = s.exec(
                select(db_models.Document).where(db_models.Document.session_id == session_id)
            ).all()
        base["uploaded_document_ids"] = [r.id for r in doc_rows]
        logger.info(
            "chat.stage.ok trace_id=%s session_id=%s stage=%s uploaded_docs=%d",
            trace_id,
            session_id,
            stage,
            len(doc_rows),
        )

        # Reload all this session's documents into the in-memory store (stateless API).
        stage = "rehydrate_document_store"
        rehydrated, missing_files = _rehydrate_store(session_id)
        logger.info(
            "chat.stage.ok trace_id=%s session_id=%s stage=%s rehydrated=%d missing_files=%d",
            trace_id,
            session_id,
            stage,
            rehydrated,
            missing_files,
        )

        stage = "graph_stream"
        async for event in _state.graph.astream_events(base, config=config, version="v2"):
            event_count += 1
            name = str(event.get("event", ""))

            if name == "on_chat_model_start":
                logger.info(
                    "chat.event trace_id=%s session_id=%s event=%s model=%s",
                    trace_id,
                    session_id,
                    name,
                    event.get("name"),
                )
            elif name == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                text = getattr(chunk, "content", "") if chunk else ""
                token_count += len(text) if isinstance(text, str) else 0
            elif name == "on_chat_model_end":
                logger.info(
                    "chat.event trace_id=%s session_id=%s event=%s streamed_chars=%d",
                    trace_id,
                    session_id,
                    name,
                    token_count,
                )
            elif name == "on_tool_start":
                tool_call_count += 1
                logger.info(
                    "chat.event trace_id=%s session_id=%s event=%s tool=%s",
                    trace_id,
                    session_id,
                    name,
                    event.get("name"),
                )
            elif name == "on_tool_end":
                logger.info(
                    "chat.event trace_id=%s session_id=%s event=%s tool=%s",
                    trace_id,
                    session_id,
                    name,
                    event.get("name"),
                )

            if name.endswith("_error"):
                logger.error(
                    "chat.event.error trace_id=%s session_id=%s event=%s payload=%s",
                    trace_id,
                    session_id,
                    name,
                    event.get("data"),
                )

            msg = _event_to_sse(event)
            if msg is not None:
                yield msg
                await asyncio.sleep(0)  # cooperative yield
    except Exception as e:  # noqa: BLE001 — surface any agent error to the UI
        logger.exception(
            "chat.stream.failed trace_id=%s session_id=%s stage=%s error=%s",
            trace_id,
            session_id,
            stage,
            str(e),
        )
        yield {"event": "error", "data": json.dumps({"message": str(e)})}
    finally:
        try:
            stage = "final_state_snapshot"
            final = await _state.graph.aget_state(config)
            if final and final.values:
                yield {
                    "event": "return_updated",
                    "data": json.dumps(
                        {
                            "return_draft": final.values["return_draft"].model_dump(mode="json"),
                            "finalized": bool(final.values.get("finalized")),
                            "pending_clarification": final.values.get("pending_clarification"),
                        }
                    ),
                }
                logger.info(
                    "chat.stage.ok trace_id=%s session_id=%s stage=%s finalized=%s",
                    trace_id,
                    session_id,
                    stage,
                    bool(final.values.get("finalized")),
                )
            else:
                logger.warning(
                    "chat.stage.empty trace_id=%s session_id=%s stage=%s",
                    trace_id,
                    session_id,
                    stage,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "chat.finalize.failed trace_id=%s session_id=%s stage=%s error=%s",
                trace_id,
                session_id,
                stage,
                str(e),
            )
            yield {
                "event": "error",
                "data": json.dumps({"message": "Failed to finalize return state"}),
            }
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "chat.request.completed trace_id=%s session_id=%s elapsed_ms=%d events=%d token_chars=%d tools=%d",
                trace_id,
                session_id,
                elapsed_ms,
                event_count,
                token_count,
                tool_call_count,
            )
            yield {"event": "done", "data": "{}"}


def _event_to_sse(event: dict) -> dict | None:
    """Map LangGraph's astream_events payloads to UI-friendly SSE events.

    We only surface:
      - on_chat_model_stream   → token-level text deltas (assistant reply)
      - on_tool_start/end      → tool-call timeline entries
    """
    name = event.get("event")

    if name == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        text = getattr(chunk, "content", "") if chunk else ""
        if text:
            return {"event": "token", "data": json.dumps({"text": text})}

    elif name == "on_tool_start":
        return {
            "event": "tool_call_start",
            "data": json.dumps(
                {"tool": event.get("name"), "args": event.get("data", {}).get("input", {})}
            ),
        }

    elif name == "on_tool_end":
        output = event.get("data", {}).get("output")
        try:
            parsed = json.loads(output) if isinstance(output, str) else output
        except (ValueError, TypeError):
            parsed = {"raw": str(output)}
        return {
            "event": "tool_call_end",
            "data": json.dumps({"tool": event.get("name"), "output": parsed}),
        }

    return None


# ---- helpers -----------------------------------------------------------------


def _thread_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _session_exists(session_id: str) -> bool:
    with get_db_session() as s:
        return s.get(db_models.Session, session_id) is not None


def _rehydrate_store(session_id: str) -> tuple[int, int]:
    """When the server restarts, the in-memory document store is empty. Re-read
    PDFs for this session from disk so parse_w2_tool can find them."""
    with get_db_session() as s:
        rows = s.exec(
            select(db_models.Document).where(db_models.Document.session_id == session_id)
        ).all()
    store = get_store()
    rehydrated = 0
    missing_files = 0
    for r in rows:
        if store.get(r.id) is not None:
            continue
        p = Path(r.source_path)
        if not p.exists():
            missing_files += 1
            logger.warning(
                "document.rehydrate.missing_file session_id=%s document_id=%s source_path=%s",
                session_id,
                r.id,
                r.source_path,
            )
            continue
        store.put(
            StoredDocument(
                document_id=r.id,
                session_id=session_id,
                pdf_bytes=p.read_bytes(),
                source_path=r.source_path,
            )
        )
        rehydrated += 1
    return rehydrated, missing_files
