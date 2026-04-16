"""LangChain @tool wrappers around every pure tool.

Each wrapper:
- Uses simple, JSON-friendly argument types that a small local model can produce.
- Catches exceptions and returns a structured error dict — so validation
  failures become normal tool-message content the agent can learn from.

The tool return type is always a dict (JSON-serializable). The planner/validator
in the graph re-parses these into the richer Pydantic types from tool_io.py.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from app.schemas.deductions import ItemizedEntry
from app.schemas.enums import FilingStatus, ItemizedCategory
from app.schemas.money import Money
from app.schemas.return_ import TaxReturn
from app.settings import settings
from app.tools.calculations import (
    compute_itemized_deduction,
    compute_std_deduction,
    compute_tax_owed,
    estimate_bracket,
)
from app.tools.forms import IncompleteReturnError, generate_form_1040
from app.tools.rules import RuleNotFoundError, lookup_irs_rule
from app.tools.w2 import DocumentNotFoundError, parse_w2


def _ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def _err(code: str, message: str, **extra: Any) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


# ---- parse_w2 -----------------------------------------------------------------


@tool
def parse_w2_tool(document_id: str) -> dict:
    """Parse an uploaded W-2 PDF into structured fields (wages, withholding, etc.).

    Args:
        document_id: The ID returned when the user uploaded a W-2 document.
    """
    try:
        parsed = parse_w2(document_id=document_id, default_tax_year=settings.tax_year)
        return _ok(parsed.model_dump(mode="json"))
    except DocumentNotFoundError as e:
        return _err("document_not_found", str(e))
    except Exception as e:
        return _err("ingest_failed", str(e))


# ---- lookup_irs_rule ----------------------------------------------------------


@tool
def lookup_irs_rule_tool(topic: str, tax_year: int) -> dict:
    """Retrieve a specific IRS rule by topic (e.g. 'standard_deduction', 'itemized_salt_cap').

    Args:
        topic: Topic key. One of: standard_deduction, tax_brackets, filing_status_rules,
            itemized_salt_cap, eitc_thresholds, child_tax_credit.
        tax_year: Tax year (e.g. 2025).
    """
    try:
        rule = lookup_irs_rule(topic=topic, tax_year=tax_year)
        return _ok(rule.model_dump(mode="json"))
    except RuleNotFoundError as e:
        return _err("rule_not_found", str(e))


# ---- compute_std_deduction ----------------------------------------------------


@tool
def compute_std_deduction_tool(filing_status: str, tax_year: int) -> dict:
    """Return the standard deduction amount for a filing status and tax year.

    Args:
        filing_status: One of: single, married_filing_jointly, married_filing_separately,
            head_of_household, qualifying_surviving_spouse.
        tax_year: Tax year (e.g. 2025).
    """
    try:
        fs = FilingStatus(filing_status)
        amt = compute_std_deduction(fs, tax_year)
        return _ok({"standard_deduction": str(amt.amount), "filing_status": fs.value, "tax_year": tax_year})
    except ValueError as e:
        return _err("invalid_filing_status", str(e))


# ---- compute_itemized_deduction ----------------------------------------------


@tool
def compute_itemized_deduction_tool(
    entries: list[dict], tax_year: int, filing_status: str
) -> dict:
    """Sum itemized Schedule A entries (applies SALT cap automatically).

    Args:
        entries: List of {category, amount, description?} entries. Category must be one of:
            medical_dental, state_local_tax, real_estate_tax, mortgage_interest,
            charitable_cash, charitable_noncash, casualty_loss, other.
        tax_year: Tax year.
        filing_status: Filing status (affects SALT cap).
    """
    try:
        fs = FilingStatus(filing_status)
        items = [
            ItemizedEntry(
                category=ItemizedCategory(e["category"]),
                amount=Money(e["amount"]),
                description=e.get("description", ""),
            )
            for e in entries
        ]
        sched = compute_itemized_deduction(items, tax_year, fs)
        return _ok(sched.model_dump(mode="json"))
    except (ValueError, KeyError) as e:
        return _err("invalid_itemized_input", str(e))


# ---- estimate_bracket ---------------------------------------------------------


@tool
def estimate_bracket_tool(
    taxable_income: str, filing_status: str, tax_year: int
) -> dict:
    """Compute marginal rate, effective rate, and total tax for a given taxable income.

    Args:
        taxable_income: Dollar amount as a decimal string, e.g. "45000.00".
        filing_status: Filing status string.
        tax_year: Tax year.
    """
    try:
        fs = FilingStatus(filing_status)
        est = estimate_bracket(Money(taxable_income), fs, tax_year)
        return _ok(est.model_dump(mode="json"))
    except ValueError as e:
        return _err("invalid_input", str(e))


# ---- compute_tax_owed ---------------------------------------------------------


@tool
def compute_tax_owed_tool(
    taxable_income: str,
    filing_status: str,
    tax_year: int,
    credits: str = "0",
) -> dict:
    """Compute tax before and after credits.

    Args:
        taxable_income: Taxable income as a decimal string.
        filing_status: Filing status string.
        tax_year: Tax year.
        credits: Total nonrefundable credits as a decimal string. Default "0".
    """
    try:
        fs = FilingStatus(filing_status)
        owed = compute_tax_owed(Money(taxable_income), fs, tax_year, Money(credits))
        return _ok(owed.model_dump(mode="json"))
    except ValueError as e:
        return _err("invalid_input", str(e))


# ---- generate_form_1040 -------------------------------------------------------


@tool
def generate_form_1040_tool(return_draft: dict) -> dict:
    """Generate a fully-populated Form 1040 from the current TaxReturn draft.

    Args:
        return_draft: The current TaxReturn as a JSON object.
    """
    try:
        draft = TaxReturn.model_validate(return_draft)
        form = generate_form_1040(draft)
        return _ok(form.model_dump(mode="json"))
    except IncompleteReturnError as e:
        return _err("incomplete_return", str(e))
    except Exception as e:
        return _err("generate_failed", str(e))


# ---- ask_user (fallback) ------------------------------------------------------


@tool
def ask_user_tool(question: str, why: str = "") -> dict:
    """Ask the user a clarifying question. Use this ONLY when you cannot proceed
    without more input (e.g., filing status unknown, ambiguous deduction choice).

    Args:
        question: The question to ask the user in plain English.
        why: Optional context explaining why the question blocks progress.
    """
    return _ok({"question": question, "why": why})


# Registry exposed to the graph
TOOLS = [
    parse_w2_tool,
    lookup_irs_rule_tool,
    compute_std_deduction_tool,
    compute_itemized_deduction_tool,
    estimate_bracket_tool,
    compute_tax_owed_tool,
    generate_form_1040_tool,
    ask_user_tool,
]

TOOLS_BY_NAME: dict[str, Any] = {t.name: t for t in TOOLS}
