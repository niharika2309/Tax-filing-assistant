from pydantic import BaseModel, Field

from app.schemas.enums import FilingStatus
from app.schemas.money import Money


class IRSRule(BaseModel):
    """A single IRS rule entry retrieved from the static knowledge base."""

    topic: str = Field(description="e.g. 'standard_deduction', 'eitc_thresholds'")
    tax_year: int
    title: str
    summary: str
    citation: str = Field(description="e.g. 'Pub. 17, 2025' or 'Rev. Proc. 2024-40'")
    values: dict[str, str] = Field(
        default_factory=dict,
        description="Topic-specific key/value facts (amounts, rates, thresholds)",
    )


class BracketHit(BaseModel):
    """One bracket segment crossed by a taxable-income value."""

    rate: float = Field(ge=0.0, le=1.0)
    from_amount: Money
    to_amount: Money | None
    taxed_amount: Money
    tax_in_bracket: Money


class BracketEstimate(BaseModel):
    taxable_income: Money
    filing_status: FilingStatus
    tax_year: int
    marginal_rate: float = Field(ge=0.0, le=1.0)
    effective_rate: float = Field(ge=0.0, le=1.0)
    total_tax: Money
    bracket_breakdown: list[BracketHit]


class TaxOwed(BaseModel):
    taxable_income: Money
    filing_status: FilingStatus
    tax_year: int
    tax_before_credits: Money
    total_credits: Money
    tax_after_credits: Money
