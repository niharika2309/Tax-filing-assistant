"""Pydantic input/output schemas for every tool the agent can invoke.

Kept separate from domain models so the tool surface is stable and self-describing
— the LLM sees these schemas (via `bind_tools`) to decide when and how to call.
"""

from pydantic import BaseModel, Field

from app.schemas.deductions import ItemizedEntry, ScheduleA
from app.schemas.documents import W2Form
from app.schemas.enums import FilingStatus
from app.schemas.money import Money
from app.schemas.return_ import Form1040, TaxReturn
from app.schemas.rules import BracketEstimate, IRSRule, TaxOwed


# ---- parse_w2 -----------------------------------------------------------------


class ParseW2Input(BaseModel):
    document_id: str = Field(description="ID of the uploaded W-2 PDF document to parse.")


class ParseW2Output(BaseModel):
    w2: W2Form


# ---- lookup_irs_rule ----------------------------------------------------------


class LookupIRSRuleInput(BaseModel):
    topic: str = Field(
        description=(
            "Topic key. One of: 'standard_deduction', 'tax_brackets', 'filing_status_rules',"
            " 'itemized_salt_cap', 'eitc_thresholds', 'child_tax_credit'."
        )
    )
    tax_year: int = Field(ge=2020, le=2030)


class LookupIRSRuleOutput(BaseModel):
    rule: IRSRule


# ---- compute_std_deduction ----------------------------------------------------


class ComputeStdDeductionInput(BaseModel):
    filing_status: FilingStatus
    tax_year: int = Field(ge=2020, le=2030)


class ComputeStdDeductionOutput(BaseModel):
    standard_deduction: Money
    filing_status: FilingStatus
    tax_year: int


# ---- compute_itemized_deduction ----------------------------------------------


class ComputeItemizedDeductionInput(BaseModel):
    entries: list[ItemizedEntry]
    tax_year: int = Field(ge=2020, le=2030)


class ComputeItemizedDeductionOutput(BaseModel):
    schedule_a: ScheduleA


# ---- estimate_bracket ---------------------------------------------------------


class EstimateBracketInput(BaseModel):
    taxable_income: Money
    filing_status: FilingStatus
    tax_year: int = Field(ge=2020, le=2030)


class EstimateBracketOutput(BaseModel):
    estimate: BracketEstimate


# ---- compute_tax_owed ---------------------------------------------------------


class ComputeTaxOwedInput(BaseModel):
    taxable_income: Money
    filing_status: FilingStatus
    tax_year: int = Field(ge=2020, le=2030)
    credits: Money = Field(default_factory=Money.zero)


class ComputeTaxOwedOutput(BaseModel):
    tax_owed: TaxOwed


# ---- generate_form_1040 -------------------------------------------------------


class GenerateForm1040Input(BaseModel):
    return_draft: TaxReturn


class GenerateForm1040Output(BaseModel):
    form_1040: Form1040


# ---- ask_user (fallback) ------------------------------------------------------


class AskUserInput(BaseModel):
    question: str = Field(
        description="Plain-English question the agent needs answered to proceed."
    )
    why: str = Field(
        default="",
        description="Optional context explaining why this question blocks progress.",
    )


class AskUserOutput(BaseModel):
    """Not actually returned to the agent — consumed by the UI as a pause signal."""

    question: str
    why: str
