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
