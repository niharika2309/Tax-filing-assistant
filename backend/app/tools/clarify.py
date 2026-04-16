"""`ask_user` is not a "tool" in the usual sense — it's a signal to the graph
that the agent cannot proceed and needs input from the user. The graph's
router pauses execution when it sees this tool called and surfaces the question
to the UI layer.
"""

from pydantic import BaseModel, Field


class ClarificationRequest(BaseModel):
    question: str = Field(description="Plain-English question to ask the user.")
    why: str = Field(default="", description="Optional context explaining the ask.")
