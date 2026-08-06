"""Tests de `DrugRepository` contra un Postgres real (pgvector incluido).

A diferencia de `tests/unit/test_drug_service.py` (dobles en memoria, sin SQL real), estos
tests ejercitan las consultas SQLAlchemy/pgvector reales — upsert, distancia coseno — que
un doble no puede verificar por construcción. Requieren un Postgres accesible en
`settings.database_url` con las migraciones aplicadas (`alembic upgrade head`); están
marcados `postgres` y excluidos del `pytest` por defecto (ver `pytest.ini`). En CI corren en
el job `migrations`, que ya levanta un servicio Postgres para las migraciones. En local:

    docker compose up -d postgres   # o el Postgres que ya use el proyecto
    alembic upgrade head
    pytest -m postgres tests/integration/test_drug_repository_postgres.py
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.drug_repository import DrugRepository

pytestmark = pytest.mark.postgres

EMBEDDING_DIMENSIONS = 768


def _embedding(value_at_index_0: float) -> list[float]:
    """Vector unitario en la primera dimensión, cero en el resto — dos vectores con
    `value_at_index_0=1.0` son idénticos (distancia coseno 0); uno con `1.0` y otro con
    `-1.0` son opuestos (distancia coseno 2, muy por encima de `MAX_RELEVANT_COSINE_DISTANCE`)."""
    return [value_at_index_0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


def _drug_data(nregistro: str, **overrides: object) -> dict:
    data = {
        "nregistro": nregistro,
        "nombre": "Fármaco de test",
        "pactivos": "principio activo de test",
        "labtitular": "Laboratorio de test",
        "cpres": None,
        "prospecto_html": None,
        "ficha_tecnica_html": None,
        "prospecto_url": None,
        "ficha_tecnica_url": None,
        "embedding": None,
    }
    data.update(overrides)
    return data


class TestSaveDrug:
    @pytest.mark.asyncio
    async def test_creates_a_new_drug_when_nregistro_is_unknown(
        self, db_session: AsyncSession
    ) -> None:
        repo = DrugRepository(db_session)

        drug = await repo.save_drug(
            _drug_data("TEST-CREATE-1", nombre="Ibuprofeno test")
        )

        assert drug.nregistro == "TEST-CREATE-1"
        assert drug.nombre == "Ibuprofeno test"
        assert drug.id is not None

    @pytest.mark.asyncio
    async def test_upserts_by_nregistro_instead_of_duplicating(
        self, db_session: AsyncSession
    ) -> None:
        repo = DrugRepository(db_session)
        original = await repo.save_drug(
            _drug_data("TEST-UPSERT-1", nombre="Nombre original")
        )

        updated = await repo.save_drug(
            _drug_data("TEST-UPSERT-1", nombre="Nombre actualizado")
        )

        assert updated.id == original.id
        assert updated.nombre == "Nombre actualizado"

    @pytest.mark.asyncio
    async def test_does_not_overwrite_nregistro_or_created_at_on_update(
        self, db_session: AsyncSession
    ) -> None:
        repo = DrugRepository(db_session)
        original = await repo.save_drug(_drug_data("TEST-UPSERT-2"))

        updated = await repo.save_drug(
            _drug_data("TEST-UPSERT-2", nombre="Nombre distinto")
        )

        assert updated.nregistro == "TEST-UPSERT-2"
        assert updated.created_at == original.created_at


class TestGetByNregistro:
    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_nregistro(
        self, db_session: AsyncSession
    ) -> None:
        repo = DrugRepository(db_session)

        result = await repo.get_by_nregistro("TEST-NO-EXISTE")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_the_saved_drug(self, db_session: AsyncSession) -> None:
        repo = DrugRepository(db_session)
        await repo.save_drug(_drug_data("TEST-GET-1", nombre="Paracetamol test"))

        result = await repo.get_by_nregistro("TEST-GET-1")

        assert result is not None
        assert result.nombre == "Paracetamol test"


class TestSearchSimilarByVector:
    @pytest.mark.asyncio
    async def test_returns_drugs_within_the_cosine_distance_threshold(
        self, db_session: AsyncSession
    ) -> None:
        repo = DrugRepository(db_session)
        await repo.save_drug(
            _drug_data(
                "TEST-VECTOR-NEAR",
                nombre="Fármaco cercano",
                embedding=_embedding(1.0),
            )
        )

        results = await repo.search_similar_by_vector(_embedding(1.0), limit=5)

        assert any(drug.nregistro == "TEST-VECTOR-NEAR" for drug in results)

    @pytest.mark.asyncio
    async def test_excludes_drugs_beyond_the_cosine_distance_threshold(
        self, db_session: AsyncSession
    ) -> None:
        repo = DrugRepository(db_session)
        await repo.save_drug(
            _drug_data(
                "TEST-VECTOR-FAR",
                nombre="Fármaco lejano",
                embedding=_embedding(-1.0),
            )
        )

        results = await repo.search_similar_by_vector(_embedding(1.0), limit=5)

        assert all(drug.nregistro != "TEST-VECTOR-FAR" for drug in results)

    @pytest.mark.asyncio
    async def test_excludes_drugs_without_an_embedding(
        self, db_session: AsyncSession
    ) -> None:
        repo = DrugRepository(db_session)
        await repo.save_drug(_drug_data("TEST-VECTOR-NULL", embedding=None))

        results = await repo.search_similar_by_vector(_embedding(1.0), limit=5)

        assert all(drug.nregistro != "TEST-VECTOR-NULL" for drug in results)
