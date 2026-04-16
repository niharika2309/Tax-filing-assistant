"""Pure calculation tools — no LLM, no I/O. The planner routes to these
whenever a deterministic computation is needed.
"""

from decimal import Decimal

from app.schemas.deductions import ItemizedEntry, ScheduleA
from app.schemas.enums import FilingStatus, ItemizedCategory
from app.schemas.money import Money
from app.schemas.rules import BracketEstimate, BracketHit, TaxOwed
from app.tools._data_loader import load_brackets


def compute_std_deduction(filing_status: FilingStatus, tax_year: int) -> Money:
    data = load_brackets(tax_year)
    raw = data["standard_deduction"][filing_status.value]
    return Money(raw)


_SALT_CAP_FULL = Money("10000.00")
_SALT_CAP_MFS = Money("5000.00")


def compute_itemized_deduction(
    entries: list[ItemizedEntry],
    tax_year: int,
    filing_status: FilingStatus | None = None,
) -> ScheduleA:
    """Aggregate itemized entries into a Schedule A summary.

    Applies the SALT cap ($10k / $5k MFS) to the combined state_local_tax +
    real_estate_tax bucket, since that's the one non-obvious rule worth enforcing
    at the tool layer.
    """
    buckets: dict[ItemizedCategory, Money] = {cat: Money.zero() for cat in ItemizedCategory}
    for e in entries:
        buckets[e.category] = buckets[e.category] + e.amount

    salt_raw = buckets[ItemizedCategory.STATE_LOCAL_TAX] + buckets[ItemizedCategory.REAL_ESTATE_TAX]
    cap = _SALT_CAP_MFS if filing_status == FilingStatus.MARRIED_FILING_SEPARATELY else _SALT_CAP_FULL
    if salt_raw > cap:
        # Scale each bucket down proportionally to respect the cap.
        ratio = Decimal(str(cap.amount)) / Decimal(str(salt_raw.amount))
        buckets[ItemizedCategory.STATE_LOCAL_TAX] = buckets[ItemizedCategory.STATE_LOCAL_TAX] * ratio
        buckets[ItemizedCategory.REAL_ESTATE_TAX] = buckets[ItemizedCategory.REAL_ESTATE_TAX] * ratio

    total = Money.zero()
    for v in buckets.values():
        total = total + v

    return ScheduleA(
        tax_year=tax_year,
        medical_dental=buckets[ItemizedCategory.MEDICAL_DENTAL],
        state_local_tax=buckets[ItemizedCategory.STATE_LOCAL_TAX],
        real_estate_tax=buckets[ItemizedCategory.REAL_ESTATE_TAX],
        mortgage_interest=buckets[ItemizedCategory.MORTGAGE_INTEREST],
        charitable_cash=buckets[ItemizedCategory.CHARITABLE_CASH],
        charitable_noncash=buckets[ItemizedCategory.CHARITABLE_NONCASH],
        casualty_loss=buckets[ItemizedCategory.CASUALTY_LOSS],
        other=buckets[ItemizedCategory.OTHER],
        total=total,
    )


def estimate_bracket(
    taxable_income: Money,
    filing_status: FilingStatus,
    tax_year: int,
) -> BracketEstimate:
    brackets = load_brackets(tax_year)["brackets"][filing_status.value]

    income = taxable_income.amount
    total_tax = Decimal("0")
    marginal_rate = 0.0
    breakdown: list[BracketHit] = []

    for b in brackets:
        lo = Decimal(b["from"])
        hi = Decimal(b["to"]) if b["to"] is not None else None
        rate = Decimal(str(b["rate"]))

        if income <= lo:
            break

        upper = income if (hi is None or income < hi) else hi
        taxed = upper - lo
        tax_here = taxed * rate
        total_tax += tax_here
        marginal_rate = float(rate)

        breakdown.append(
            BracketHit(
                rate=float(rate),
                from_amount=Money(lo),
                to_amount=Money(hi) if hi is not None else None,
                taxed_amount=Money(taxed),
                tax_in_bracket=Money(tax_here),
            )
        )

        if hi is None or income <= hi:
            break

    effective = float(total_tax / income) if income > 0 else 0.0

    return BracketEstimate(
        taxable_income=taxable_income,
        filing_status=filing_status,
        tax_year=tax_year,
        marginal_rate=marginal_rate,
        effective_rate=effective,
        total_tax=Money(total_tax),
        bracket_breakdown=breakdown,
    )


def compute_tax_owed(
    taxable_income: Money,
    filing_status: FilingStatus,
    tax_year: int,
    credits: Money | None = None,
) -> TaxOwed:
    credits = credits or Money.zero()
    est = estimate_bracket(taxable_income, filing_status, tax_year)
    tax_before = est.total_tax
    after = tax_before - credits
    if after < Money.zero():
        after = Money.zero()
    return TaxOwed(
        taxable_income=taxable_income,
        filing_status=filing_status,
        tax_year=tax_year,
        tax_before_credits=tax_before,
        total_credits=credits,
        tax_after_credits=after,
    )
