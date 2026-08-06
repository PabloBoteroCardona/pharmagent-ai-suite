"""Tests de `PrescriptionRecordRepository` contra un Postgres real.

Mismo mecanismo y motivación que `test_drug_repository_postgres.py` (ver su docstring):
verifica la persistencia real (columnas `JSONB`, valores por defecto) que un doble en
memoria no ejercita. Marcados `postgres`, excluidos del `pytest` por defecto.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.prescription_record_repository import (
    PrescriptionRecordRepository,
)

pytestmark = pytest.mark.postgres


class TestSave:
    @pytest.mark.asyncio
    async def test_persists_drugs_advertencias_and_safety_check(
        self, db_session: AsyncSession
    ) -> None:
        repo = PrescriptionRecordRepository(db_session)
        drugs = [{"farmaco": "Ibuprofeno", "dosificacion": "600 mg"}]
        advertencias = ["Tomar con alimentos."]
        safety_check = {"verdict": "apto", "interactions": []}

        record = await repo.save(
            drugs=drugs,
            advertencias=advertencias,
            safety_check=safety_check,
            patient_id="paciente-test-1",
        )

        assert record.id is not None
        assert record.drugs == drugs
        assert record.advertencias == advertencias
        assert record.safety_check == safety_check
        assert record.patient_id == "paciente-test-1"
        assert record.created_at is not None

    @pytest.mark.asyncio
    async def test_defaults_patient_id_to_none_when_not_given(
        self, db_session: AsyncSession
    ) -> None:
        repo = PrescriptionRecordRepository(db_session)

        record = await repo.save(drugs=[], advertencias=[], safety_check=None)

        assert record.patient_id is None
        assert record.safety_check is None

    @pytest.mark.asyncio
    async def test_each_save_creates_a_distinct_record(
        self, db_session: AsyncSession
    ) -> None:
        repo = PrescriptionRecordRepository(db_session)

        first = await repo.save(drugs=[], advertencias=[], safety_check=None)
        second = await repo.save(drugs=[], advertencias=[], safety_check=None)

        assert first.id != second.id
