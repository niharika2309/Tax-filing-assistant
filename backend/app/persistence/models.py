from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Session(SQLModel, table=True):
    id: str = Field(primary_key=True)
    tax_year: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Document(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    filename: str
    source_path: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # OCR metadata, filled in after first parse
    ocr_used: Optional[bool] = None
    confidence: Optional[float] = None
