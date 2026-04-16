"""LangGraph SQLite checkpointer — async variant for FastAPI compatibility."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.settings import settings


@asynccontextmanager
async def build_checkpointer() -> AsyncIterator[AsyncSqliteSaver]:
    settings.checkpoints_db.parent.mkdir(parents=True, exist_ok=True)
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("app.schemas.return_", "TaxReturn"),
            ("app.schemas.money", "Money"),
            ("app.schemas.enums", "FilingStatus"),
            ("app.schemas.enums", "DeductionType"),
            ("app.schemas.documents", "ParsedDocument"),
            ("app.schemas.documents", "W2Form"),
            ("app.schemas.deductions", "ScheduleA"),
            ("app.schemas.deductions", "ItemizedEntry"),
            ("app.schemas.return_", "TaxpayerInfo"),
        ]
    )
    async with aiosqlite.connect(str(settings.checkpoints_db)) as conn:
        saver = AsyncSqliteSaver(conn=conn, serde=serde)
        await saver.setup()
        yield saver
