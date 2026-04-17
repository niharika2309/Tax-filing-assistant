import pytest

from app.schemas.documents import W2Form
from app.schemas.enums import DeductionType, FilingStatus
from app.schemas.money import Money
from app.schemas.return_ import TaxReturn, TaxpayerInfo
from app.tools.forms import IncompleteReturnError, generate_form_1040


def _complete_return(refund: bool = True) -> TaxReturn:
    wages = Money("50000")
    withholding = Money("6000") if refund else Money("2000")
    deduction = Money("15000")
    taxable = Money("35000")
    tax = Money("4006.00")  # computed from 2025 single brackets elsewhere
    w2 = W2Form(
        document_id="doc-1",
        wages=wages,
        federal_income_tax_withheld=withholding,
        tax_year=2025,
    )
    return TaxReturn(
        session_id="sess-1",
        tax_year=2025,
        taxpayer=TaxpayerInfo(filing_status=FilingStatus.SINGLE),
        w2_forms=[w2],
        deduction_type=DeductionType.STANDARD,
        standard_deduction=deduction,
        total_wages=wages,
        total_federal_withholding=withholding,
        adjusted_gross_income=wages,
        taxable_income=taxable,
        tax_before_credits=tax,
        tax_after_credits=tax,
        refund_or_owed=(withholding - tax) if refund else (tax - withholding),
    )


def test_generate_form_1040_refund_case():
    f = generate_form_1040(_complete_return(refund=True))
    assert f.line_1a_wages == Money("50000")
    assert f.line_12_deduction == Money("15000")
    assert f.line_12_deduction_type == DeductionType.STANDARD
    assert f.line_15_taxable_income == Money("35000")
    assert f.line_34_refund > Money.zero()
    assert f.line_37_amount_owed == Money.zero()


def test_generate_form_1040_owed_case():
    f = generate_form_1040(_complete_return(refund=False))
    assert f.line_37_amount_owed > Money.zero()
    assert f.line_34_refund == Money.zero()


def test_generate_form_1040_incomplete_raises():
    partial = TaxReturn(session_id="sess-1", tax_year=2025)
    with pytest.raises(IncompleteReturnError) as exc:
        generate_form_1040(partial)
    msg = str(exc.value)
    assert "filing_status" in msg
    assert "total_wages" in msg
