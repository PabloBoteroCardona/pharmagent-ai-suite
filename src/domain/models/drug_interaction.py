"""Entidad de dominio: interacción conocida entre dos fármacos.

Capa de dominio pura: no importa nada fuera de la librería estándar de Python
y Pydantic. No debe depender de SQLAlchemy, FastAPI, Google ADK ni de ningún
detalle de infraestructura.
"""

from __future__ import annotations

from enum import Enum
from uuid import uuid4

from pydantic import UUID4, BaseModel, ConfigDict, Field


class InteractionSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class DrugInteraction(BaseModel):
    """Interacción conocida entre dos fármacos, con su recomendación clínica."""

    model_config = ConfigDict(strict=True, frozen=True)

    id: UUID4 = Field(default_factory=uuid4)
    primary_drug: str = Field(
        ..., min_length=1, description="Principio activo primario de la interacción."
    )
    secondary_drug: str = Field(
        ..., min_length=1, description="Principio activo secundario de la interacción."
    )
    severity: InteractionSeverity
    description: str = Field(
        ...,
        min_length=1,
        description="Descripción del mecanismo farmacológico de la interacción.",
    )
    clinical_recommendation: str = Field(
        ...,
        min_length=1,
        description="Recomendación clínica ante la presencia de esta interacción.",
    )
