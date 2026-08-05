"""Puertos (interfaces) de dominio para las dependencias externas de `DrugService`/`RAGPharmAgent`.

Definidos como `typing.Protocol` (tipado estructural): las implementaciones concretas en
`src/infrastructure/` NO heredan de estas clases ni las importan — simplemente coinciden en
firma. Esto invierte la dependencia (Dependency Inversion Principle): `src/application/`
depende de estas interfaces, nunca de las clases concretas de infraestructura
(`CimaAPIClient`, `OllamaClient`, `DrugRepository`).

Limitación conocida y aceptada: `DrugRepositoryPort` referencia `DrugModel`, que es un
modelo ORM de `src/infrastructure/models/`. Estrictamente, un puerto de dominio no debería
conocer un tipo de infraestructura (SQLAlchemy); se importa aquí solo bajo `TYPE_CHECKING`
para no introducir una dependencia real en tiempo de ejecución. La solución completa sería
una entidad de dominio `Drug` independiente del ORM, mapeada en el repositorio concreto —
fuera de alcance de este bloque de refactorización.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.infrastructure.models import DrugModel, PrescriptionRecordModel


@runtime_checkable
class CimaDataSourcePort(Protocol):
    """Fuente de datos oficiales de medicamentos (CIMA/AEMPS en vivo)."""

    async def search_medicamentos(self, nombre: str) -> list[dict]: ...

    async def get_medicamento_by_nregistro(self, nregistro: str) -> dict | None: ...

    async def get_ficha_tecnica_html(self, nregistro: str) -> str | None: ...

    async def get_prospecto_html(self, nregistro: str) -> str | None: ...


@runtime_checkable
class LanguageModelPort(Protocol):
    """Modelo de lenguaje local: embeddings y generación de texto."""

    async def generate_embedding(self, text: str) -> list[float]: ...

    async def generate_completion(self, prompt: str, system: str = "") -> str: ...


@runtime_checkable
class DrugRepositoryPort(Protocol):
    """Persistencia / caché semántica de fármacos."""

    async def save_drug(self, drug_data: dict) -> DrugModel: ...

    async def get_by_nregistro(self, nregistro: str) -> DrugModel | None: ...

    async def search_similar_by_vector(
        self, embedding: list[float], limit: int = 5
    ) -> list[DrugModel]: ...


@runtime_checkable
class PrescriptionVisionPort(Protocol):
    """Comprensión multimodal de imágenes de recetas médicas (visión + lenguaje)."""

    async def analyze_prescription_image(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> dict: ...


@runtime_checkable
class PrescriptionRecordRepositoryPort(Protocol):
    """Persistencia auditable del resultado de `ProcessPrescriptionUseCase`."""

    async def save(
        self,
        drugs: list[dict],
        advertencias: list[str],
        safety_check: dict | None,
        patient_id: str | None = None,
    ) -> PrescriptionRecordModel: ...
