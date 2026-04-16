"""Graph nodes. The control flow (router decisions, retry budget) lives here;
the actual tool logic lives in `app/tools/`.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.prompts import RETRY_PROMPT, SYSTEM_PROMPT
from app.agent.state import AgentState
from app.schemas.deductions import ItemizedEntry, ScheduleA
from app.schemas.documents import ParsedDocument
from app.schemas.enums import DeductionType, ItemizedCategory
from app.schemas.money import Money
from app.schemas.return_ import TaxReturn
from app.settings import settings
from app.tools.registry import TOOLS_BY_NAME


def _system_message(state: AgentState) -> SystemMessage:
    draft = state["return_draft"]
    parsed_ids = list(state.get("documents", {}).keys())
    uploaded_ids = state.get("uploaded_document_ids", [])
    unparsed_ids = [d for d in uploaded_ids if d not in parsed_ids]
    all_ids = parsed_ids + unparsed_ids
    return SystemMessage(
        content=SYSTEM_PROMPT.format(
            tax_year=draft.tax_year,
            return_draft=draft.model_dump_json(indent=2),
            document_ids=all_ids if all_ids else "[none]",
        )
    )


def make_planner(llm: BaseChatModel):
    """Build the planner node bound to a specific LLM. The LLM is injected so
    tests can pass a stub and production can pass ChatOpenAI→LM Studio."""

    def planner(state: AgentState) -> dict[str, Any]:
        messages = [_system_message(state), *state["messages"]]
        response = llm.invoke(messages)
        # Reset per-call clarification signal; the planner re-sets it if needed.
        return {"messages": [response], "pending_clarification": None}

    return planner


def tool_exec(state: AgentState) -> dict[str, Any]:
    """Execute every tool call in the latest AIMessage. Returns ToolMessages
    and applies side effects (e.g. updating return_draft from parsed W-2)."""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {}

    tool_messages: list[ToolMessage] = []
    updates: dict[str, Any] = {}
    documents = dict(state.get("documents", {}))
    draft = state["return_draft"].model_copy(deep=True)
    pending_clarification: str | None = None

    for call in last.tool_calls:
        name = call["name"]
        args = call["args"]
        call_id = call["id"]

        tool = TOOLS_BY_NAME.get(name)
        if tool is None:
            tool_messages.append(
                ToolMessage(
                    content=json.dumps(
                        {"ok": False, "error": {"code": "unknown_tool", "message": name}}
                    ),
                    tool_call_id=call_id,
                    name=name,
                )
            )
            continue

        try:
            result = tool.invoke(args)
        except Exception as e:
            result = {
                "ok": False,
                "error": {"code": "tool_exception", "message": str(e)},
            }

        # Apply state side effects for tools that mutate the return draft.
        if isinstance(result, dict) and result.get("ok"):
            _apply_side_effects(name, args, result["data"], draft, documents)
            if name == "ask_user_tool":
                pending_clarification = result["data"].get("question")

        tool_messages.append(
            ToolMessage(
                content=json.dumps(result, default=str),
                tool_call_id=call_id,
                name=name,
            )
        )

    updates["messages"] = tool_messages
    updates["return_draft"] = draft
    updates["documents"] = documents
    if pending_clarification is not None:
        updates["pending_clarification"] = pending_clarification
    return updates


def _apply_side_effects(
    tool_name: str,
    args: dict,
    data: Any,
    draft: TaxReturn,
    documents: dict[str, ParsedDocument],
) -> None:
    """Merge tool outputs into the running TaxReturn draft.

    Keeping this in one place (instead of each tool writing state) means the
    agent loop remains functional and the graph checkpointer sees one atomic
    update per step.
    """
    if tool_name == "parse_w2_tool":
        parsed = ParsedDocument.model_validate(data)
        documents[parsed.document_id] = parsed
        if parsed.w2 and parsed.w2 not in draft.w2_forms:
            draft.w2_forms.append(parsed.w2)
            total_wages = Money.zero()
            total_wh = Money.zero()
            for w2 in draft.w2_forms:
                total_wages = total_wages + w2.wages
                total_wh = total_wh + w2.federal_income_tax_withheld
            draft.total_wages = total_wages
            draft.total_federal_withholding = total_wh
            draft.adjusted_gross_income = total_wages

    elif tool_name == "compute_std_deduction_tool":
        draft.standard_deduction = Money(data["standard_deduction"])
        draft.deduction_type = DeductionType.STANDARD
        fs = args.get("filing_status")
        if fs and draft.taxpayer.filing_status is None:
            draft.taxpayer.filing_status = FilingStatus(fs)

    elif tool_name == "compute_itemized_deduction_tool":
        sched = ScheduleA.model_validate(data)
        draft.schedule_a = sched
        draft.itemized_deduction = sched.total
        # Also stash the raw entries the agent provided, so Form 1040's Schedule A
        # has the underlying categories available for display.
        draft.itemized_entries = [
            ItemizedEntry(
                category=ItemizedCategory(e["category"]),
                amount=Money(e["amount"]),
                description=e.get("description", ""),
            )
            for e in (args.get("entries") or [])
        ]

    elif tool_name == "compute_tax_owed_tool":
        draft.tax_before_credits = Money(data["tax_before_credits"])
        draft.total_credits = Money(data["total_credits"])
        draft.tax_after_credits = Money(data["tax_after_credits"])
        ti = args.get("taxable_income")
        if ti is not None:
            draft.taxable_income = Money(ti)
        if draft.total_federal_withholding is not None:
            diff = draft.total_federal_withholding - draft.tax_after_credits
            draft.refund_or_owed = diff

    elif tool_name == "estimate_bracket_tool":
        # Treat a bracket estimate without credits as the tentative tax.
        draft.tax_before_credits = Money(data["total_tax"])


def validator(state: AgentState) -> dict[str, Any]:
    """Detect tool errors in the most recent batch and prepare retry context.

    LangGraph already routed us here after tool_exec. We only need to decide
    whether any tool call failed, and if so whether we've exhausted retries.
    """
    # The most recent N messages are the ToolMessages from tool_exec.
    errors: list[str] = []
    for m in reversed(state["messages"]):
        if not isinstance(m, ToolMessage):
            break
        try:
            payload = json.loads(m.content)
        except (ValueError, TypeError):
            errors.append(f"{m.name}: non-JSON tool result")
            continue
        if isinstance(payload, dict) and payload.get("ok") is False:
            err = payload.get("error", {})
            errors.append(f"{m.name}: {err.get('message', 'unknown error')}")

    if not errors:
        return {"retry_count": 0, "last_error": None}

    joined = "; ".join(errors)
    retry = state.get("retry_count", 0) + 1
    return {
        "retry_count": retry,
        "last_error": joined,
        "messages": [HumanMessage(content=RETRY_PROMPT.format(error=joined))],
    }


def finalize(state: AgentState) -> dict[str, Any]:
    """Terminal node when the return is complete. Sets deduction_type if the
    agent chose one but never set it explicitly."""
    draft = state["return_draft"].model_copy(deep=True)
    if draft.deduction_type is None:
        # Default preference: whichever is larger.
        if draft.itemized_deduction and draft.standard_deduction:
            draft.deduction_type = (
                DeductionType.ITEMIZED
                if draft.itemized_deduction > draft.standard_deduction
                else DeductionType.STANDARD
            )
        elif draft.standard_deduction is not None:
            draft.deduction_type = DeductionType.STANDARD
    return {"return_draft": draft, "finalized": True}


def route_after_planner(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tool_exec"
    # Planner produced a natural-language reply with no tool calls → end this turn.
    return "end"


def route_after_validator(state: AgentState) -> str:
    if state.get("pending_clarification"):
        return "end"  # ask_user was called — pause for user input
    if state.get("last_error"):
        if state["retry_count"] >= settings.tool_retry_budget:
            return "ask_user_exhausted"
        return "planner"
    # No errors. Decide whether to finalize.
    if state["return_draft"].is_complete():
        return "finalize"
    return "planner"


def ask_user_exhausted(state: AgentState) -> dict[str, Any]:
    """Graceful fallback: retry budget blown. Ask the user to intervene."""
    err = state.get("last_error", "I ran into repeated tool errors.")
    question = (
        "I'm stuck after several attempts. "
        f"The blocker was: {err}. Can you give me more detail about what you want me to do?"
    )
    return {"pending_clarification": question, "retry_count": 0, "last_error": None}
