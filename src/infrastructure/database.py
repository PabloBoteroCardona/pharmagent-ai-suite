"""Configuración de conexión asíncrona a PostgreSQL vía SQLAlchemy 2.0.

Expone el engine, la fábrica de sesiones y la dependencia `get_db_session`
para inyectar en FastAPI / casos de uso. Los repositorios y modelos ORM
concretos (`src/infrastructure/repositories/`, `src/infrastructure/models/`)
heredan de `Base` definida aquí.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.infrastructure.config.settings import settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# `settings.database_ssl` (por defecto `False`): el Postgres de docker-compose.yml no ofrece
# SSL, así que hay que desactivarlo explícitamente (asyncpg lo exige explícito, no asume). Un
# Postgres gestionado en un proveedor de despliegue normalmente sí lo exige — con
# `DATABASE_SSL=true` se omite `connect_args` por completo y asyncpg negocia SSL por defecto.
connect_args: dict[str, object] = {} if settings.database_ssl else {"ssl": False}
async_engine = create_async_engine(settings.database_url, connect_args=connect_args)

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
