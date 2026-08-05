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
    source: str = Field(
        default="curated",
        description=(
            "'curated' si procede de la base curada interna (autoritativa); 'llm' si "
            "procede del razonamiento del modelo de lenguaje local para una combinación "
            "no cubierta por la base curada — ver AGENTS.md."
        ),
    )


class InteractionCheckResponse(BaseModel):
    """Respuesta del `SafetyCheckAgent` a una verificación de interacciones."""

    model_config = ConfigDict(strict=True)

    interactions: list[InteractionResult] = Field(default_factory=list)
    verdict: str


class ProcessPrescriptionResponse(BaseModel):
    """Respuesta del flujo completo receta → extracción → interacciones
    (`ProcessPrescriptionUseCase`)."""

    model_config = ConfigDict(strict=True)

    prescription: PrescriptionAnalysisResponse
    safety_check: InteractionCheckResponse | None = Field(
        default=None,
        description=(
            "None si la extracción no identificó al menos 2 fármacos — sin un segundo "
            "fármaco no hay interacción posible que verificar."
        ),
    )
