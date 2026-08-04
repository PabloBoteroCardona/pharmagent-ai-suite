"""Configuración de conexión asíncrona a PostgreSQL vía SQLAlchemy 2.0.

Expone el engine, la fábrica de sesiones y la dependencia `get_db_session`
para inyectar en FastAPI / casos de uso. Los repositorios y modelos ORM
concretos (capa `src/adapters/db/`) heredan de `Base` definida aquí.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://pharmagent:pharmagent_pass@localhost:5432/pharmagent_db"
)

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

async_engine = create_async_engine(DATABASE_URL)

AsyncSessionFactory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia asíncrona que provee una sesión de base de datos por request/caso de uso."""
    async with AsyncSessionFactory() as session:
        yield session
