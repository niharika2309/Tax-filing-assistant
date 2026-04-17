from decimal import Decimal

import pytest

from app.schemas.deductions import ItemizedEntry
from app.schemas.enums import FilingStatus, ItemizedCategory
from app.schemas.money import Money
from app.tools.calculations import (
    compute_itemized_deduction,
    compute_std_deduction,
    compute_tax_owed,
    estimate_bracket,
)


# ---- standard deduction -------------------------------------------------------


@pytest.mark.parametrize(
    "status, expected",
    [
        (FilingStatus.SINGLE, Money("15000")),
        (FilingStatus.MARRIED_FILING_JOINTLY, Money("30000")),
        (FilingStatus.HEAD_OF_HOUSEHOLD, Money("22500")),
        (FilingStatus.MARRIED_FILING_SEPARATELY, Money("15000")),
    ],
)
def test_std_deduction_2025(status: FilingStatus, expected: Money) -> None:
    assert compute_std_deduction(status, 2025) == expected


# ---- bracket estimate ---------------------------------------------------------


def test_bracket_estimate_single_below_first_bracket_boundary():
    # $50k single, 2025 standard deduction = $15k → taxable $35k
    est = estimate_bracket(Money("35000"), FilingStatus.SINGLE, 2025)
    # 10% on first $11,925 + 12% on ($35k - $11,925) = $11,925*0.10 + $23,075*0.12
    expected = Decimal("11925") * Decimal("0.10") + Decimal("23075") * Decimal("0.12")
    assert est.total_tax.amount == expected.quantize(Decimal("0.01"))
    assert est.marginal_rate == 0.12
    assert len(est.bracket_breakdown) == 2


def test_bracket_estimate_zero_income():
    est = estimate_bracket(Money("0"), FilingStatus.SINGLE, 2025)
    assert est.total_tax == Money.zero()
    assert est.effective_rate == 0.0
    assert est.bracket_breakdown == []


def test_bracket_estimate_high_income_mfj():
    # $1M MFJ hits all 7 brackets
    est = estimate_bracket(Money("1000000"), FilingStatus.MARRIED_FILING_JOINTLY, 2025)
    assert len(est.bracket_breakdown) == 7
    assert est.marginal_rate == 0.37


# ---- tax owed ----------------------------------------------------------------


def test_compute_tax_owed_applies_credits_without_going_negative():
    owed = compute_tax_owed(
        taxable_income=Money("35000"),
        filing_status=FilingStatus.SINGLE,
        tax_year=2025,
        credits=Money("100000"),
    )
    assert owed.tax_after_credits == Money.zero()


def test_compute_tax_owed_matches_bracket_estimate():
    taxable = Money("75000")
    est = estimate_bracket(taxable, FilingStatus.SINGLE, 2025)
    owed = compute_tax_owed(taxable, FilingStatus.SINGLE, 2025)
    assert owed.tax_before_credits == est.total_tax
    assert owed.tax_after_credits == est.total_tax


# ---- itemized -----------------------------------------------------------------


def test_itemized_sum_below_salt_cap():
    entries = [
        ItemizedEntry(category=ItemizedCategory.MORTGAGE_INTEREST, amount=Money("8000")),
        ItemizedEntry(category=ItemizedCategory.STATE_LOCAL_TAX, amount=Money("4000")),
        ItemizedEntry(category=ItemizedCategory.REAL_ESTATE_TAX, amount=Money("3000")),
        ItemizedEntry(category=ItemizedCategory.CHARITABLE_CASH, amount=Money("2000")),
    ]
    sched = compute_itemized_deduction(entries, 2025, FilingStatus.SINGLE)
    assert sched.mortgage_interest == Money("8000")
    assert sched.state_local_tax == Money("4000")
    assert sched.real_estate_tax == Money("3000")
    assert sched.charitable_cash == Money("2000")
    assert sched.total == Money("17000")


def test_itemized_applies_salt_cap():
    # $8k SALT + $9k real estate = $17k → cap at $10k, scaled proportionally
    entries = [
        ItemizedEntry(category=ItemizedCategory.STATE_LOCAL_TAX, amount=Money("8000")),
        ItemizedEntry(category=ItemizedCategory.REAL_ESTATE_TAX, amount=Money("9000")),
        ItemizedEntry(category=ItemizedCategory.MORTGAGE_INTEREST, amount=Money("5000")),
    ]
    sched = compute_itemized_deduction(entries, 2025, FilingStatus.SINGLE)
    capped_total_salt = sched.state_local_tax + sched.real_estate_tax
    assert capped_total_salt == Money("10000")
    # Mortgage interest untouched
    assert sched.mortgage_interest == Money("5000")
    # Proportional scaling: 8/17 and 9/17 of $10k
    assert sched.state_local_tax.amount == (Decimal("10000") * Decimal("8") / Decimal("17")).quantize(Decimal("0.01"))


def test_itemized_mfs_cap_is_5k():
    entries = [
        ItemizedEntry(category=ItemizedCategory.STATE_LOCAL_TAX, amount=Money("6000")),
        ItemizedEntry(category=ItemizedCategory.REAL_ESTATE_TAX, amount=Money("4000")),
    ]
    sched = compute_itemized_deduction(entries, 2025, FilingStatus.MARRIED_FILING_SEPARATELY)
    assert sched.state_local_tax + sched.real_estate_tax == Money("5000")
