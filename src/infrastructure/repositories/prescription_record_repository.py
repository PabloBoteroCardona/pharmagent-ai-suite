"""Repositorio de acceso a datos para `PrescriptionRecordModel`.

Capa de infraestructura: persiste el resultado de `ProcessPrescriptionUseCase` como
registro auditable. Ver [prescription_record_model.py](../models/prescription_record_model.py)
para la decisión de no mapear directamente a la entidad de dominio `Prescription`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.models import PrescriptionRecordModel


class PrescriptionRecordRepository:
    """Repositorio de `PrescriptionRecordModel`, operando sobre una `AsyncSession` inyectada."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        drugs: list[dict],
        advertencias: list[str],
        safety_check: dict | None,
        patient_id: str | None = None,
    ) -> PrescriptionRecordModel:
        """Persiste un nuevo registro de receta procesada."""
        record = PrescriptionRecordModel(
            patient_id=patient_id,
            drugs=drugs,
            advertencias=advertencias,
            safety_check=safety_check,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return record
