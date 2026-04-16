from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.schemas.documents import ParsedDocument
from app.schemas.return_ import TaxReturn


class AgentState(TypedDict, total=False):
    session_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    return_draft: TaxReturn
    documents: dict[str, ParsedDocument]
    uploaded_document_ids: list[str]
    retry_count: int
    last_error: str | None
    pending_clarification: str | None
    finalized: bool


def initial_state(session_id: str, tax_year: int) -> AgentState:
    return {
        "session_id": session_id,
        "messages": [],
        "return_draft": TaxReturn(session_id=session_id, tax_year=tax_year),
        "documents": {},
        "uploaded_document_ids": [],
        "retry_count": 0,
        "last_error": None,
        "pending_clarification": None,
        "finalized": False,
    }
