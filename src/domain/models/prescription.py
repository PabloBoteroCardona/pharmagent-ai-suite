"""Entidad de dominio: receta médica y sus líneas de fármaco prescrito.

Capa de dominio pura: no importa nada fuera de la librería estándar de Python
y Pydantic. No debe depender de SQLAlchemy, FastAPI, Google ADK ni de ningún
detalle de infraestructura.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import UUID4, BaseModel, ConfigDict, Field


class PrescribedDrug(BaseModel):
    """Un fármaco prescrito dentro de una receta, con su pauta posológica."""

    model_config = ConfigDict(strict=True, frozen=True)

    drug_name: str = Field(
        ...,
        min_length=1,
        description="Nombre o principio activo del fármaco prescrito.",
    )
    dosage: str = Field(
        ..., min_length=1, description="Dosis prescrita, p. ej. '500 mg'."
    )
    frequency_hours: int = Field(
        ..., gt=0, description="Frecuencia de administración, en horas entre tomas."
    )
    duration_days: int = Field(
        ..., gt=0, description="Duración del tratamiento, en días."
    )
    notes: str | None = Field(
        default=None,
        description="Observaciones adicionales, p. ej. 'tomar con alimentos'.",
    )


class Prescription(BaseModel):
    """Receta médica: agregado raíz del dominio de prescripción."""

    model_config = ConfigDict(strict=True, frozen=True)

    id: UUID4 = Field(default_factory=uuid4)
    patient_id: str = Field(
        ..., min_length=1, description="Identificador anonimizado del paciente."
    )
    raw_text: str | None = Field(
        default=None, description="Texto bruto de la receta, si procede de OCR."
    )
    prescribed_drugs: list[PrescribedDrug] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
