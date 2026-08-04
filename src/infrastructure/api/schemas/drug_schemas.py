"""Esquemas Pydantic v2 de los endpoints de farmacia (`pharmacy_router.py`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DrugSearchQuery(BaseModel):
    """Petición de búsqueda semántica de fármacos."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=50)


class ConsultationRequest(BaseModel):
    """Petición de consulta en lenguaje natural al `RAGPharmAgent`."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=1)


class ConsultationResponse(BaseModel):
    """Respuesta del `RAGPharmAgent` a una consulta."""

    model_config = ConfigDict(strict=True)

    query: str
    response: str
    sources: list[str] = Field(default_factory=list)


class ExtractedDrugItem(BaseModel):
    """Un fármaco extraído de una imagen de receta por `PrescriptionAgent`."""

    model_config = ConfigDict(strict=True)

    farmaco: str
    dosificacion: str | None = None
    frecuencia: str | None = None
    duracion: str | None = None


class PrescriptionAnalysisResponse(BaseModel):
    """Respuesta del `PrescriptionAgent` al análisis multimodal de una receta."""

    model_config = ConfigDict(strict=True)

    drugs: list[ExtractedDrugItem] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)


class InteractionCheckRequest(BaseModel):
    """Petición de verificación de interacciones entre fármacos."""

    model_config = ConfigDict(strict=True)

    drugs: list[str] = Field(..., min_length=2)


class InteractionResult(BaseModel):
    """Una interacción concreta detectada por `SafetyCheckAgent`."""

    model_config = ConfigDict(strict=True)

    primary_drug: str
    secondary_drug: str
    severity: str
    description: str
    clinical_recommendation: str


class InteractionCheckResponse(BaseModel):
    """Respuesta del `SafetyCheckAgent` a una verificación de interacciones."""

    model_config = ConfigDict(strict=True)

    interactions: list[InteractionResult] = Field(default_factory=list)
    verdict: str
