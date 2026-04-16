from sqlmodel import Session, SQLModel, create_engine

from app.persistence import models  # noqa: F401 — register tables
from app.settings import settings

_engine = create_engine(f"sqlite:///{settings.app_db}", echo=False)


def init_db() -> None:
    settings.app_db.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(_engine)


def get_session() -> Session:
    return Session(_engine)
