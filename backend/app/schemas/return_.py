from pydantic import BaseModel, Field

from app.schemas.deductions import ItemizedEntry, ScheduleA
from app.schemas.documents import W2Form
from app.schemas.enums import DeductionType, FilingStatus
from app.schemas.money import Money


class TaxpayerInfo(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    ssn_last4: str | None = Field(default=None, max_length=4)
    filing_status: FilingStatus | None = None
    dependents: int = Field(default=0, ge=0)


class TaxReturn(BaseModel):
    """The running draft state of the user's return.

    Nullability is intentional — fields fill in as tools execute. `is_complete()`
    gates the transition to the `finalize` node.
    """

    session_id: str
    tax_year: int
    taxpayer: TaxpayerInfo = Field(default_factory=TaxpayerInfo)
    w2_forms: list[W2Form] = Field(default_factory=list)

    deduction_type: DeductionType | None = None
    standard_deduction: Money | None = None
    itemized_entries: list[ItemizedEntry] = Field(default_factory=list)
    itemized_deduction: Money | None = None
    schedule_a: ScheduleA | None = None

    total_wages: Money | None = None
    total_federal_withholding: Money | None = None
    adjusted_gross_income: Money | None = None
    taxable_income: Money | None = None
    tax_before_credits: Money | None = None
    total_credits: Money = Field(default_factory=Money.zero)
    tax_after_credits: Money | None = None
    refund_or_owed: Money | None = None

    def is_complete(self) -> bool:
        return all(
            v is not None
            for v in (
                self.taxpayer.filing_status,
                self.deduction_type,
                self.total_wages,
                self.total_federal_withholding,
                self.taxable_income,
                self.tax_after_credits,
                self.refund_or_owed,
            )
        ) and len(self.w2_forms) > 0


class Form1040(BaseModel):
    """Form 1040 as a line-numbered structure. Values mirror the IRS 2025 layout."""

    session_id: str
    tax_year: int
    taxpayer: TaxpayerInfo
    # Income
    line_1a_wages: Money
    line_9_total_income: Money
    line_10_adjustments: Money = Field(default_factory=Money.zero)
    line_11_agi: Money
    # Deduction
    line_12_deduction: Money
    line_12_deduction_type: DeductionType
    line_15_taxable_income: Money
    # Tax
    line_16_tax: Money
    line_21_total_credits: Money
    line_24_total_tax: Money
    # Payments
    line_25a_withholding: Money
    # Refund / owed
    line_34_refund: Money = Field(default_factory=Money.zero)
    line_37_amount_owed: Money = Field(default_factory=Money.zero)

    schedule_a: ScheduleA | None = None
