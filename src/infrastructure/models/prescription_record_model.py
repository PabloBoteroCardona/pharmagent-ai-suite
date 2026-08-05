"""Modelo ORM SQLAlchemy 2.0 para el registro auditable de recetas procesadas.

Persiste el resultado de `ProcessPrescriptionUseCase` (extracción de
`PrescriptionAgent` + verificación de `SafetyCheckAgent`, si se ejecutó) como un
registro de auditoría — no es un mapeo 1:1 de la entidad de dominio
`Prescription`/`PrescribedDrug` ([prescription.py](../../domain/models/prescription.py)).

Decisión deliberada: `PrescribedDrug` exige campos tipados y estrictos
(`frequency_hours: int`, `duration_days: int`), pero `GeminiClient` extrae texto libre no
normalizado (p. ej. `frecuencia: "cada 8 horas"`, `duracion: "5 días"`). Forzar ese texto a
enteros mediante heurísticas de parseo introduciría un riesgo real de error silencioso en un
dominio de datos de salud — mejor persistir la extracción tal como la devolvió el agente
(JSON crudo) que inventar una conversión no verificada. La normalización a `PrescribedDrug`
queda como trabajo futuro, cuando `PrescriptionAgent` devuelva campos ya estructurados.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database import Base


class PrescriptionRecordModel(Base):
    """Registro auditable de una receta procesada por `ProcessPrescriptionUseCase`."""

    __tablename__ = "prescription_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    drugs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    advertencias: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    safety_check: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
