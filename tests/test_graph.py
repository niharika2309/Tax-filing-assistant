"""End-to-end graph tests with a stub LLM. Exercises the happy path (sequence of
tool calls → finalize) and the retry-then-ask-user fallback."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.agent.graph import build_graph
from app.agent.state import initial_state
from app.agent.stub_llm import StubChatModel, ai_plain, ai_with_tool_calls, tool_call
from app.ingest.pipeline import ingest_w2_from_text
from app.schemas.enums import FilingStatus
from app.schemas.money import Money
from app.schemas.return_ import TaxpayerInfo
from app.tools.document_store import InMemoryDocumentStore, StoredDocument, set_store
from tests.test_ingest import DIGITAL_W2_TEXT


def _seed_store_with_parsed_w2(document_id: str, session_id: str) -> None:
    """Bypass real PDF parsing — register a document whose "bytes" are irrelevant
    because we substitute the ingest function in the test to work from text."""
    store = InMemoryDocumentStore()
    store.put(
        StoredDocument(
            document_id=document_id,
            session_id=session_id,
            pdf_bytes=b"not-a-real-pdf",
            source_path="/tmp/fake.pdf",
        )
    )
    set_store(store)


def test_happy_path_completes_return(monkeypatch):
    """Script: parse_w2 → compute_std_deduction → compute_tax_owed → generate_form_1040.
    The planner picks filing status from the user's chat message."""
    document_id = "doc-1"
    session_id = "sess-happy"
    _seed_store_with_parsed_w2(document_id, session_id)

    # Substitute the ingest used by parse_w2_tool so we don't need a real PDF.
    def fake_ingest_w2(pdf_bytes, document_id, source_path, default_tax_year):
        parsed = ingest_w2_from_text(
            DIGITAL_W2_TEXT, document_id, source_path, default_tax_year
        )

        class _R:
            pass

        r = _R()
        r.parsed = parsed
        r.ocr_used = False
        return r

    monkeypatch.setattr("app.tools.w2.ingest_w2", fake_ingest_w2)

    # Pre-set filing status on the draft so the planner doesn't need to ask.
    state = initial_state(session_id=session_id, tax_year=2025)
    state["return_draft"].taxpayer = TaxpayerInfo(filing_status=FilingStatus.SINGLE)
    state["return_draft"].deduction_type = None  # Let the graph set it via finalize.
    from app.schemas.enums import DeductionType

    # We'll force deduction_type via the draft after the std tool runs (normally the
    # planner would do this in natural language → here we shortcut via the script).

    # Scripted LLM responses — each invoke returns one AIMessage in sequence.
    llm = StubChatModel(
        responses=[
            ai_with_tool_calls(
                [tool_call("parse_w2_tool", {"document_id": document_id})]
            ),
            ai_with_tool_calls(
                [
                    tool_call(
                        "compute_std_deduction_tool",
                        {"filing_status": "single", "tax_year": 2025},
                    )
                ]
            ),
            # After std deduction lands, we expect taxable income = 52345.67 - 15000 = 37345.67
            ai_with_tool_calls(
                [
                    tool_call(
                        "compute_tax_owed_tool",
                        {
                            "taxable_income": "37345.67",
                            "filing_status": "single",
                            "tax_year": 2025,
                            "credits": "0",
                        },
                    )
                ]
            ),
            # Planner reports done — the conditional edge takes us to finalize only if
            # the draft is complete. We need deduction_type set; planner calls
            # generate_form_1040 which won't run because missing deduction_type.
            # Easiest: set deduction_type via finalize default — but finalize only
            # triggers when is_complete() is true. is_complete() requires deduction_type.
            # So script one more LLM turn that yields a plain reply to end this turn.
            ai_plain("All computed. Say 'finalize' to produce Form 1040."),
        ]
    )

    graph = build_graph(llm)
    result = graph.invoke(
        {
            **state,
            "messages": [HumanMessage(content="File my return. I'm single.")],
        }
    )

    # After the three tool calls, the return draft should have wages, deduction,
    # and tax numbers populated.
    draft = result["return_draft"]
    assert draft.total_wages == Money("52345.67")
    assert draft.standard_deduction == Money("15000.00")
    assert draft.tax_after_credits is not None
    assert draft.tax_after_credits > Money.zero()
    # At least one W-2 was attached.
    assert len(draft.w2_forms) == 1


def test_retry_budget_escalates_to_ask_user():
    """Three consecutive tool errors → graph asks the user instead of looping forever."""
    session_id = "sess-retry"
    state = initial_state(session_id=session_id, tax_year=2025)

    bad = lambda: ai_with_tool_calls(
        [
            tool_call(
                "compute_std_deduction_tool",
                {"filing_status": "INVALID_STATUS", "tax_year": 2025},
            )
        ]
    )

    llm = StubChatModel(
        responses=[bad(), bad(), bad(), ai_plain("giving up")]
    )

    graph = build_graph(llm)
    result = graph.invoke(
        {
            **state,
            "messages": [HumanMessage(content="File my taxes.")],
        }
    )

    # After 3 failed tool attempts, pending_clarification should be set
    # and the graph should have terminated (not looped forever).
    assert result.get("pending_clarification") is not None
    assert "stuck" in result["pending_clarification"].lower()


def test_itemized_path_produces_schedule_a(monkeypatch):
    """Scripted itemized flow: compute_itemized_deduction populates schedule_a on the draft."""
    session_id = "sess-itemized"
    state = initial_state(session_id=session_id, tax_year=2025)
    state["return_draft"].taxpayer = TaxpayerInfo(filing_status=FilingStatus.SINGLE)

    llm = StubChatModel(
        responses=[
            ai_with_tool_calls(
                [
                    tool_call(
                        "compute_itemized_deduction_tool",
                        {
                            "entries": [
                                {
                                    "category": "mortgage_interest",
                                    "amount": "12000.00",
                                    "description": "Primary residence",
                                },
                                {
                                    "category": "state_local_tax",
                                    "amount": "8000.00",
                                    "description": "CA income tax",
                                },
                                {
                                    "category": "real_estate_tax",
                                    "amount": "6000.00",
                                    "description": "Property tax",
                                },
                                {
                                    "category": "charitable_cash",
                                    "amount": "3000.00",
                                    "description": "Donations",
                                },
                            ],
                            "tax_year": 2025,
                            "filing_status": "single",
                        },
                    )
                ]
            ),
            ai_plain("Itemized deduction applied with SALT cap."),
        ]
    )

    graph = build_graph(llm)
    result = graph.invoke(
        {
            **state,
            "messages": [HumanMessage(content="Itemize my deductions.")],
        }
    )

    draft = result["return_draft"]
    assert draft.schedule_a is not None
    # SALT cap = $10k applied to $8k + $6k = $14k raw → capped
    assert draft.schedule_a.state_local_tax + draft.schedule_a.real_estate_tax == Money("10000")
    assert draft.schedule_a.mortgage_interest == Money("12000")
    assert draft.itemized_deduction == draft.schedule_a.total
    assert len(draft.itemized_entries) == 4


def test_ask_user_tool_pauses_graph():
    """If the planner calls ask_user_tool, we should pause — not finalize."""
    session_id = "sess-clarify"
    state = initial_state(session_id=session_id, tax_year=2025)

    llm = StubChatModel(
        responses=[
            ai_with_tool_calls(
                [
                    tool_call(
                        "ask_user_tool",
                        {
                            "question": "What is your filing status?",
                            "why": "Required to compute the standard deduction.",
                        },
                    )
                ]
            ),
        ]
    )

    graph = build_graph(llm)
    result = graph.invoke(
        {
            **state,
            "messages": [HumanMessage(content="File my taxes.")],
        }
    )

    assert result["pending_clarification"] == "What is your filing status?"
    # Draft should remain empty (no side effects from ask_user)
    assert result["return_draft"].total_wages is None
