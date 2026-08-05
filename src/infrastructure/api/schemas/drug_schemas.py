"""Esquemas Pydantic v2 de los endpoints de farmacia (`pharmacy_router.py`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DrugSearchQuery(BaseModel):
    """Petición de búsqueda semántica de fármacos."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=50)


class DrugSearchResultItem(BaseModel):
    """Un fármaco encontrado por `POST /search`."""

    model_config = ConfigDict(strict=True)

    nregistro: str
    nombre: str
    pactivos: str | None = None
    labtitular: str | None = None


class DrugSearchResponse(BaseModel):
    """Respuesta de `POST /search`, con la procedencia de los resultados."""

    model_config = ConfigDict(strict=True)

    results: list[DrugSearchResultItem] = Field(default_factory=list)
    source: str = Field(
        description=(
            "'cache' si los resultados vinieron de la caché vectorial local; 'live' si "
            "no había nada en caché y se consultó CIMA en vivo (y se indexó para "
            "consultas futuras); 'none' si tampoco CIMA en vivo encontró nada."
        )
    )


class ConsultationRequest(BaseModel):
    """Petición de consulta en lenguaje natural al `RAGPharmAgent`."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=1)
    drug_name: str | None = Field(
        default=None,
        description=(
            "Nombre del medicamento a buscar, si se conoce. CIMA hace coincidencia por "
            "nombre, no búsqueda semántica: indicarlo mejora la probabilidad de "
            "encontrarlo en vivo cuando no está en la caché y `query` es una pregunta "
            "en lenguaje natural sin el nombre del fármaco de forma literal."
        ),
    )


class ConsultationSourceItem(BaseModel):
    """Un fármaco usado como contexto de una respuesta de `POST /consult`, con enlaces
    a su documentación oficial en CIMA (ficha técnica y prospecto) cuando está
    disponible — permite al usuario consultar la fuente original completa."""

    model_config = ConfigDict(strict=True)

    nombre: str
    ficha_tecnica_url: str | None = None
    prospecto_url: str | None = None


class ConsultationResponse(BaseModel):
    """Respuesta del `RAGPharmAgent` a una consulta."""

    model_config = ConfigDict(strict=True)

    query: str
    response: str
    sources: list[ConsultationSourceItem] = Field(default_factory=list)
    source: str = Field(
        default="none",
        description="'cache' | 'live' | 'none' — ver DrugSearchResponse.source.",
    )


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
