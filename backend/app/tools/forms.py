"""Form generation tools — deterministic mapping from TaxReturn state to IRS
line-numbered structures.
"""

from app.schemas.enums import DeductionType
from app.schemas.money import Money
from app.schemas.return_ import Form1040, TaxReturn


class IncompleteReturnError(ValueError):
    """Raised when `generate_form_1040` is invoked before the return draft is ready."""


def generate_form_1040(return_draft: TaxReturn) -> Form1040:
    missing = []
    if not return_draft.taxpayer.filing_status:
        missing.append("filing_status")
    if return_draft.total_wages is None:
        missing.append("total_wages")
    if return_draft.total_federal_withholding is None:
        missing.append("total_federal_withholding")
    if return_draft.deduction_type is None:
        missing.append("deduction_type")
    if return_draft.tax_after_credits is None:
        missing.append("tax_after_credits")
    if missing:
        raise IncompleteReturnError(
            f"Cannot generate Form 1040 — missing fields: {', '.join(missing)}"
        )

    deduction = (
        return_draft.standard_deduction
        if return_draft.deduction_type == DeductionType.STANDARD
        else return_draft.itemized_deduction
    )
    assert deduction is not None  # guaranteed by missing-field check above

    agi = return_draft.adjusted_gross_income or return_draft.total_wages
    taxable = return_draft.taxable_income or (agi - deduction if agi >= deduction else Money.zero())
    total_tax = return_draft.tax_after_credits
    withholding = return_draft.total_federal_withholding

    refund = Money.zero()
    owed = Money.zero()
    if withholding > total_tax:
        refund = withholding - total_tax
    else:
        owed = total_tax - withholding

    return Form1040(
        session_id=return_draft.session_id,
        tax_year=return_draft.tax_year,
        taxpayer=return_draft.taxpayer,
        line_1a_wages=return_draft.total_wages,
        line_9_total_income=return_draft.total_wages,
        line_11_agi=agi,
        line_12_deduction=deduction,
        line_12_deduction_type=return_draft.deduction_type,
        line_15_taxable_income=taxable,
        line_16_tax=return_draft.tax_before_credits or total_tax,
        line_21_total_credits=return_draft.total_credits,
        line_24_total_tax=total_tax,
        line_25a_withholding=withholding,
        line_34_refund=refund,
        line_37_amount_owed=owed,
        schedule_a=(
            return_draft.schedule_a
            if return_draft.deduction_type == DeductionType.ITEMIZED
            else None
        ),
    )
