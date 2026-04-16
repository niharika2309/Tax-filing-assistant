from pydantic import BaseModel, Field

from app.schemas.enums import ItemizedCategory
from app.schemas.money import Money


class ItemizedEntry(BaseModel):
    category: ItemizedCategory
    amount: Money
    description: str = Field(default="", max_length=200)


class ScheduleA(BaseModel):
    """Schedule A — Itemized Deductions (2025 layout, simplified)."""

    tax_year: int
    medical_dental: Money = Field(default_factory=Money.zero)
    state_local_tax: Money = Field(default_factory=Money.zero)
    real_estate_tax: Money = Field(default_factory=Money.zero)
    mortgage_interest: Money = Field(default_factory=Money.zero)
    charitable_cash: Money = Field(default_factory=Money.zero)
    charitable_noncash: Money = Field(default_factory=Money.zero)
    casualty_loss: Money = Field(default_factory=Money.zero)
    other: Money = Field(default_factory=Money.zero)
    total: Money
