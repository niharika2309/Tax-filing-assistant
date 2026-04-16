"""Scripted stub LLM for deterministic graph tests.

Feed it a list of responses (AIMessage or a dict → AIMessage). Each call to
.invoke() consumes the next response. This lets us exercise the graph's
routing logic without spinning up LM Studio.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def tool_call(name: str, args: dict[str, Any], call_id: str | None = None) -> dict:
    return {"name": name, "args": args, "id": call_id or f"call_{uuid.uuid4().hex[:8]}"}


def ai_with_tool_calls(calls: list[dict]) -> AIMessage:
    return AIMessage(content="", tool_calls=calls)


def ai_plain(text: str) -> AIMessage:
    return AIMessage(content=text)


class StubChatModel(BaseChatModel):
    """Returns responses from a pre-loaded script."""

    responses: list[AIMessage]
    call_log: list[list[BaseMessage]] = []
    cursor: int = 0

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, responses: list[AIMessage], **kwargs):
        super().__init__(responses=responses, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs
    ) -> ChatResult:
        if self.cursor >= len(self.responses):
            # Ran off the script — default to a plain "done" reply so the graph terminates.
            msg = ai_plain("(stub exhausted)")
        else:
            msg = self.responses[self.cursor]
            self.cursor += 1
        self.call_log.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools: list[Any], **kwargs) -> "StubChatModel":
        # Tools are ignored by the stub — it emits whatever the script says.
        return self

    def __iter__(self) -> Iterator[AIMessage]:
        return iter(self.responses)
