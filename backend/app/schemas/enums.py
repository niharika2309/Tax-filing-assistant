from enum import StrEnum


class FilingStatus(StrEnum):
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"
    QUALIFYING_SURVIVING_SPOUSE = "qualifying_surviving_spouse"


class DeductionType(StrEnum):
    STANDARD = "standard"
    ITEMIZED = "itemized"


class ItemizedCategory(StrEnum):
    """Schedule A line categories (simplified)."""

    MEDICAL_DENTAL = "medical_dental"
    STATE_LOCAL_TAX = "state_local_tax"
    REAL_ESTATE_TAX = "real_estate_tax"
    MORTGAGE_INTEREST = "mortgage_interest"
    CHARITABLE_CASH = "charitable_cash"
    CHARITABLE_NONCASH = "charitable_noncash"
    CASUALTY_LOSS = "casualty_loss"
    OTHER = "other"
