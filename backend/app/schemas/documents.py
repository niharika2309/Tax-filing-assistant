from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.money import Money


class W2Form(BaseModel):
    """W-2 wage and tax statement. Only fields needed for Form 1040 v1 scope."""

    document_id: str
    employer_ein: str | None = Field(default=None, description="Employer EIN (box b)")
    employer_name: str | None = Field(default=None, description="Employer name (box c)")
    employee_ssn_last4: str | None = Field(
        default=None, max_length=4, description="Last 4 of SSN only"
    )

    # Box 1 — Wages, tips, other compensation
    wages: Money
    # Box 2 — Federal income tax withheld
    federal_income_tax_withheld: Money

    # Boxes 3–6 (Social Security / Medicare) — captured but not used for 1040 line totals
    social_security_wages: Money = Field(default_factory=Money.zero)
    social_security_tax_withheld: Money = Field(default_factory=Money.zero)
    medicare_wages: Money = Field(default_factory=Money.zero)
    medicare_tax_withheld: Money = Field(default_factory=Money.zero)

    # Box 17 — state income tax (used if we expand to state returns; captured for completeness)
    state_income_tax_withheld: Money = Field(default_factory=Money.zero)

    tax_year: int


class ParsedDocument(BaseModel):
    """Wrapper for any ingested tax document with provenance."""

    document_id: str
    kind: Literal["w2", "1099", "unknown"]
    source_path: str
    parsed_at: datetime
    w2: W2Form | None = None
    ocr_used: bool
    confidence: float = Field(ge=0.0, le=1.0)


class IngestError(Exception):
    """Raised by the ingest pipeline when required fields cannot be extracted."""

    def __init__(self, message: str, missing_fields: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing_fields = missing_fields or []
