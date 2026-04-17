"""Verify SqliteSaver checkpointing lets a session resume across graph rebuilds."""

import tempfile
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.graph import build_graph
from app.agent.state import initial_state
from app.agent.stub_llm import StubChatModel, ai_plain, ai_with_tool_calls, tool_call
from app.schemas.enums import FilingStatus
from app.schemas.money import Money
from app.schemas.return_ import TaxpayerInfo


def test_session_resumes_from_checkpoint(tmp_path: Path):
    db_path = tmp_path / "checkpoints.db"
    config = {"configurable": {"thread_id": "resume-1"}}

    # First turn: run a compute_std_deduction call and checkpoint.
    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        llm_1 = StubChatModel(
            responses=[
                ai_with_tool_calls(
                    [
                        tool_call(
                            "compute_std_deduction_tool",
                            {"filing_status": "single", "tax_year": 2025},
                        )
                    ]
                ),
                ai_plain("Standard deduction computed."),
            ]
        )
        graph_1 = build_graph(llm_1, checkpointer=saver)
        state_1 = initial_state(session_id="resume-1", tax_year=2025)
        state_1["return_draft"].taxpayer = TaxpayerInfo(filing_status=FilingStatus.SINGLE)
        state_1["messages"] = [HumanMessage(content="What's my standard deduction?")]
        result_1 = graph_1.invoke(state_1, config=config)
        assert result_1["return_draft"].standard_deduction == Money("15000")

    # Second turn: fresh process, fresh graph, fresh LLM. Checkpoint must persist
    # the standard_deduction computed in turn 1.
    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        llm_2 = StubChatModel(responses=[ai_plain("Resumed session.")])
        graph_2 = build_graph(llm_2, checkpointer=saver)

        snapshot = graph_2.get_state(config)
        assert snapshot is not None and snapshot.values
        resumed_draft = snapshot.values["return_draft"]
        assert resumed_draft.standard_deduction == Money("15000")
        assert resumed_draft.taxpayer.filing_status == FilingStatus.SINGLE
