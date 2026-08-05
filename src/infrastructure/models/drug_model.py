"""Modelo ORM SQLAlchemy 2.0 para medicamentos, con soporte de embeddings via pgvector.

Almacena la caché local (secundaria) de datos oficiales de CIMA/AEMPS — ficha técnica y
prospecto (contenido y URL pública de cada uno) — y su embedding semántico, usado por el
adaptador RAG para búsquedas vectoriales cuando la consulta en vivo a CIMA no está
disponible.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database import Base

EMBEDDING_DIMENSIONS = 768


class DrugModel(Base):
    __tablename__ = "drugs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nregistro: Mapped[str] = mapped_column(unique=True, index=True)
    nombre: Mapped[str] = mapped_column(index=True)
    pactivos: Mapped[str | None]
    labtitular: Mapped[str | None]
    cpres: Mapped[str | None]
    prospecto_html: Mapped[str | None]
    ficha_tecnica_html: Mapped[str | None]
    prospecto_url: Mapped[str | None]
    ficha_tecnica_url: Mapped[str | None]
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
