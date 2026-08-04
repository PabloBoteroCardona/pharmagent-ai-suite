"""Script de inicialización de la base de datos.

Habilita la extensión `pgvector` y crea todas las tablas definidas en los
modelos ORM (`Base.metadata`). Uso: python -m src.infrastructure.init_db
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.infrastructure.database import Base
from src.infrastructure.database import async_engine as engine
from src.infrastructure.models import (
    DrugModel,  # noqa: F401 — registra el modelo en Base.metadata
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    try:
        asyncio.run(init_db())
    except Exception as exc:
        print(f"Error al inicializar la base de datos: {exc}")
        raise
    else:
        print(
            "Base de datos inicializada correctamente: extensión pgvector habilitada y tablas creadas."
        )
