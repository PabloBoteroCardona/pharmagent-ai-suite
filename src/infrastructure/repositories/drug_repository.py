"""Repositorio de acceso a datos para `DrugModel`.

Capa de infraestructura: encapsula las consultas SQLAlchemy (upsert por
`nregistro`, lectura y búsqueda semántica vía pgvector) que alimentan la
caché local descrita en [DECISIONS.md](../../../.memory/DECISIONS.md).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.models import DrugModel

NON_UPDATABLE_FIELDS = {"id", "nregistro", "created_at"}


class DrugRepository:
    """Repositorio de `DrugModel`, operando sobre una `AsyncSession` inyectada."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_drug(self, drug_data: dict) -> DrugModel:
        """Crea o actualiza (upsert) un fármaco por su `nregistro`."""
        drug = await self.get_by_nregistro(drug_data["nregistro"])

        if drug is None:
            drug = DrugModel(**drug_data)
            self._session.add(drug)
        else:
            for field, value in drug_data.items():
                if field not in NON_UPDATABLE_FIELDS:
                    setattr(drug, field, value)

        await self._session.commit()
        await self._session.refresh(drug)
        return drug

    async def get_by_nregistro(self, nregistro: str) -> DrugModel | None:
        """Consulta un fármaco por su número de registro AEMPS."""
        result = await self._session.execute(
            select(DrugModel).where(DrugModel.nregistro == nregistro)
        )
        return result.scalar_one_or_none()

    async def search_similar_by_vector(
        self, embedding: list[float], limit: int = 5
    ) -> list[DrugModel]:
        """Devuelve los fármacos más cercanos a `embedding` por distancia L2 (pgvector)."""
        result = await self._session.execute(
            select(DrugModel)
            .where(DrugModel.embedding.is_not(None))
            .order_by(DrugModel.embedding.l2_distance(embedding))
            .limit(limit)
        )
        return list(result.scalars().all())
