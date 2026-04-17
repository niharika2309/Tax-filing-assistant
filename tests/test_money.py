from decimal import Decimal

from pydantic import BaseModel

from app.schemas.money import Money


def test_money_rounds_to_cents():
    assert Money("1.005").amount == Decimal("1.01")     # round half up
    assert Money("1.004").amount == Decimal("1.00")
    assert Money(0.1).amount == Decimal("0.10")


def test_money_arithmetic():
    assert (Money("10") + Money("5")).amount == Decimal("15.00")
    assert (Money("10") - Money("3.50")).amount == Decimal("6.50")
    assert (Money("100") * Decimal("0.1")).amount == Decimal("10.00")


def test_money_comparisons():
    assert Money("5") < Money("10")
    assert Money("10") == Money("10.00")
    assert Money("10") >= Money("10")


def test_money_in_pydantic_model_roundtrips():
    class M(BaseModel):
        amt: Money

    # From string
    m = M.model_validate({"amt": "42.50"})
    assert m.amt == Money("42.50")
    # Serializes as string
    assert m.model_dump()["amt"] == "42.50"
    # Re-validates from its own dump
    assert M.model_validate(m.model_dump()).amt == m.amt


def test_money_json_schema_pattern():
    class M(BaseModel):
        amt: Money

    schema = M.model_json_schema()
    assert "pattern" in schema["properties"]["amt"]
