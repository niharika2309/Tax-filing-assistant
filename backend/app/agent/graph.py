"""LangGraph wiring. The LLM is injected so prod uses LM Studio and tests use a stub."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    ask_user_exhausted,
    finalize,
    make_planner,
    route_after_planner,
    route_after_validator,
    tool_exec,
    validator,
)
from app.agent.state import AgentState
from app.tools.registry import TOOLS


def build_graph(llm: BaseChatModel, checkpointer=None):
    """Compile the agent graph. `checkpointer` is optional — None for tests,
    SqliteSaver in production.
    """
    llm_with_tools = llm.bind_tools(TOOLS)
    planner = make_planner(llm_with_tools)

    builder = StateGraph(AgentState)
    builder.add_node("planner", planner)
    builder.add_node("tool_exec", tool_exec)
    builder.add_node("validator", validator)
    builder.add_node("finalize", finalize)
    builder.add_node("ask_user_exhausted", ask_user_exhausted)

    builder.add_edge(START, "planner")

    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "tool_exec": "tool_exec",
            "end": END,
        },
    )

    builder.add_edge("tool_exec", "validator")

    builder.add_conditional_edges(
        "validator",
        route_after_validator,
        {
            "planner": "planner",
            "finalize": "finalize",
            "ask_user_exhausted": "ask_user_exhausted",
            "end": END,
        },
    )

    builder.add_edge("ask_user_exhausted", END)
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)
