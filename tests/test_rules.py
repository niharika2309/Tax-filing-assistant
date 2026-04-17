import pytest

from app.tools.rules import RuleNotFoundError, lookup_irs_rule


def test_lookup_standard_deduction_rule():
    rule = lookup_irs_rule("standard_deduction", 2025)
    assert rule.topic == "standard_deduction"
    assert rule.values["single"] == "15000.00"
    assert "Rev. Proc." in rule.citation


def test_lookup_salt_cap():
    rule = lookup_irs_rule("itemized_salt_cap", 2025)
    assert rule.values["cap_mfj_single_hoh"] == "10000.00"
    assert rule.values["cap_mfs"] == "5000.00"


def test_lookup_is_case_insensitive_and_trims():
    assert lookup_irs_rule("  Standard_Deduction ", 2025).topic == "standard_deduction"


def test_lookup_unknown_topic_raises():
    with pytest.raises(RuleNotFoundError) as exc:
        lookup_irs_rule("nonsense_topic", 2025)
    # error message lists available topics so the agent can self-correct
    assert "standard_deduction" in str(exc.value)
