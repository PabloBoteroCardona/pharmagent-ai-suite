"""Repositorio de acceso a datos para `DrugModel`.

Capa de infraestructura: encapsula las consultas SQLAlchemy (upsert por
`nregistro`, lectura y búsqueda semántica vía pgvector) que alimentan la
caché local de fármacos.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.models import DrugModel

NON_UPDATABLE_FIELDS = {"id", "nregistro", "created_at"}

# `pgvector` siempre devuelve los `limit` vecinos más cercanos, aunque ninguno sea
# realmente relevante — sin un umbral, una búsqueda de un fármaco no cacheado nunca
# devolvería "vacío", impidiendo el respaldo a CIMA en vivo de `DrugService`.
#
# Se usa distancia coseno, no L2: se comprobó empíricamente (contra la caché real del
# proyecto, `nomic-embed-text` 768 dim) que L2 es sensible a la longitud del texto
# comparado, no solo a su contenido semántico — una consulta corta de una palabra
# ("metformina") queda artificialmente lejos (L2≈16.6) incluso del propio fármaco que
# describe, mientras que consultas más largas del mismo fármaco quedan mucho más cerca
# (L2≈5.4-9.9) sin ser más relevantes. La distancia coseno, al normalizar por magnitud,
# no tiene ese problema: en las mismas pruebas, consultas relevantes midieron
# coseno ≈ 0.24-0.33 y consultas irrelevantes ≈ 0.38-0.48, con una separación estable
# independiente de la longitud de la consulta.
#
# Es una heurística, no una garantía: el modelo (no especializado en farmacia) no
# siempre distingue fármacos relacionados por mecanismo — p. ej. "omeprazol" quedó a
# coseno≈0.40 de "esomeprazol" ya cacheado, tan lejos como de fármacos no relacionados,
# así que ese caso concreto cae al respaldo de CIMA en vivo en vez de a un cache hit
# (comportamiento aceptable: solo implica una consulta extra a CIMA, no una respuesta
# incorrecta). Umbral específico de este modelo de embedding — recalibrar si se cambia.
MAX_RELEVANT_COSINE_DISTANCE = 0.35


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
        """Devuelve los fármacos cacheados relevantes para `embedding` (distancia
        coseno por debajo de `MAX_RELEVANT_COSINE_DISTANCE`, ver constante del módulo).
        Puede devolver una lista vacía si ningún fármaco cacheado es suficientemente
        similar — eso es intencional: permite a `DrugService` distinguir "no hay nada
        relevante en caché" (y recurrir a CIMA en vivo) de "sí hay algo, aunque no sea
        un match perfecto"."""
        distance = DrugModel.embedding.cosine_distance(embedding)
        result = await self._session.execute(
            select(DrugModel)
            .where(DrugModel.embedding.is_not(None))
            .where(distance <= MAX_RELEVANT_COSINE_DISTANCE)
            .order_by(distance)
            .limit(limit)
        )
        return list(result.scalars().all())
