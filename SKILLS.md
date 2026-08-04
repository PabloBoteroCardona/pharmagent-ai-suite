# SKILLS.md — Herramientas (Tools) de los agentes

Este documento define, con **Pydantic v2**, los esquemas de entrada/salida de las
herramientas invocadas por los agentes descritos en [AGENTS.md](AGENTS.md). Estos esquemas
son el contrato entre el dominio (`src/domain`) y los adaptadores ADK
(`src/adapters/adk`) — el dominio depende únicamente de estas interfaces, nunca de
detalles de Google ADK o de un proveedor de modelo concreto.

Convenciones:
- Todos los modelos heredan de `pydantic.BaseModel` y usan `model_config = ConfigDict(strict=True)`
  salvo que se indique lo contrario, para evitar coerciones silenciosas de tipo.
- Los campos opcionales usan `X | None = None` explícito, nunca valores por defecto implícitos.
- Los `Enum` se definen con `str, Enum` para serializar de forma legible en JSON/logs.
- La función Python que implementa cada *tool* vive junto al adaptador ADK correspondiente
  (`src/adapters/adk/tools/`) y se registra en el agente con `function_calling` de ADK.

---

## 1. `extract_prescription_from_image`

Usada por **PrescriptionAgent** ([AGENTS.md](AGENTS.md#1-prescriptionagent)).

```python
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImageMediaType(str, Enum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    PDF = "application/pdf"


class ExtractPrescriptionFromImageInput(BaseModel):
    """Entrada de la tool: imagen de la receta a procesar."""

    model_config = ConfigDict(strict=True)

    image_bytes: bytes = Field(..., description="Contenido binario de la imagen o PDF de la receta.")
    media_type: ImageMediaType
    patient_id: str | None = Field(
        default=None, description="Identificador interno del paciente, si ya está registrado."
    )

    @field_validator("image_bytes")
    @classmethod
    def not_empty(cls, v: bytes) -> bytes:
        if not v:
            raise ValueError("image_bytes no puede estar vacío")
        return v


class ExtractedDrugLine(BaseModel):
    """Una línea de fármaco dentro de la receta."""

    model_config = ConfigDict(strict=True)

    raw_text: str = Field(..., description="Texto tal como aparece en la receta, sin normalizar.")
    active_ingredient: str | None = Field(
        default=None, description="Principio activo normalizado, si se identifica con confianza suficiente."
    )
    dose: str | None = Field(default=None, description="Dosis, p. ej. '500 mg'.")
    frequency: str | None = Field(default=None, description="Posología, p. ej. 'cada 8 horas'.")
    duration_days: int | None = Field(default=None, ge=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class PrescriptionExtractionResult(BaseModel):
    """Salida de la tool: datos estructurados de la receta."""

    model_config = ConfigDict(strict=True)

    prescriber_name: str | None = None
    prescriber_license_number: str | None = None
    patient_name: str | None = None
    issue_date: date | None = None
    drugs: list[ExtractedDrugLine] = Field(default_factory=list)
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    requires_manual_review: bool = Field(
        ..., description="True si overall_confidence o algún campo crítico está por debajo del umbral configurado."
    )
```

**Umbral de revisión manual**: `PRESCRIPTION_MIN_CONFIDENCE` (`.env`), aplicado en
`src/use_cases/process_prescription.py`, no dentro de la tool.

---

## 2. `check_drug_interactions`

Usada por **SafetyCheckAgent** ([AGENTS.md](AGENTS.md#2-safetycheckagent)).

```python
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    MILD = "leve"
    MODERATE = "moderada"
    SEVERE = "grave"
    CONTRAINDICATED = "contraindicada"


class Verdict(str, Enum):
    FIT = "apto"
    FIT_WITH_CAUTION = "apto_con_precaucion"
    REQUIRES_MEDICAL_REVIEW = "requiere_revision_medica"


class PatientContext(BaseModel):
    """Contexto clínico opcional del paciente, usado para afinar el chequeo."""

    model_config = ConfigDict(strict=True)

    age_years: int | None = Field(default=None, ge=0, le=130)
    known_allergies: list[str] = Field(default_factory=list)
    chronic_medications: list[str] = Field(default_factory=list)
    is_pregnant_or_lactating: bool | None = None


class CheckDrugInteractionsInput(BaseModel):
    """Entrada de la tool: fármacos a evaluar."""

    model_config = ConfigDict(strict=True)

    active_ingredients: list[str] = Field(..., min_length=1)
    patient_context: PatientContext | None = None


class DrugInteraction(BaseModel):
    """Una interacción concreta detectada entre dos o más fármacos."""

    model_config = ConfigDict(strict=True)

    involved_drugs: list[str] = Field(..., min_length=2)
    severity: Severity
    mechanism: str = Field(..., description="Explicación farmacológica del mecanismo de interacción.")
    recommendation: str = Field(..., description="Recomendación clínica concreta, p. ej. 'espaciar tomas 4 horas'.")
    source: str = Field(..., description="Fuente de la interacción, p. ej. referencia AEMPS/CIMA o base curada.")


class DrugInteractionReport(BaseModel):
    """Salida de la tool: informe de seguridad farmacológica."""

    model_config = ConfigDict(strict=True)

    interactions: list[DrugInteraction] = Field(default_factory=list)
    verdict: Verdict
    verdict_justification: str = Field(
        ..., description="Justificación textual del veredicto, citando las interacciones detectadas."
    )
```

**Regla de negocio**: si `interactions` contiene alguna con `severity in {SEVERE, CONTRAINDICATED}`,
o si `patient_context` es `None` y hay medicación crónica desconocida, el `verdict` no puede ser
`FIT` (validado en `src/domain/services/drug_safety_service.py`, no confiado únicamente al LLM).

---

## 3. `search_cima_vector_db`

Usada por **RAGPharmAgent** ([AGENTS.md](AGENTS.md#3-ragpharmagent)).

```python
from pydantic import BaseModel, ConfigDict, Field


class SearchCimaVectorDbInput(BaseModel):
    """Entrada de la tool: consulta a recuperar de la base vectorial de fichas técnicas."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=3, description="Pregunta o término de búsqueda en lenguaje natural.")
    drug_name: str | None = Field(
        default=None, description="Nombre del medicamento para acotar la búsqueda, si se conoce."
    )
    top_k: int = Field(default=5, ge=1, le=20)
    min_similarity: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Umbral mínimo de similitud coseno para incluir un fragmento."
    )


class CimaChunk(BaseModel):
    """Un fragmento recuperado de una ficha técnica AEMPS/CIMA."""

    model_config = ConfigDict(strict=True)

    drug_name: str
    cima_code: str = Field(..., description="Código nacional / código CIMA del medicamento.")
    section: str = Field(..., description="Sección de la ficha técnica, p. ej. '4.3 Contraindicaciones'.")
    text: str
    similarity: float = Field(..., ge=0.0, le=1.0)


class SearchCimaVectorDbResult(BaseModel):
    """Salida de la tool: fragmentos recuperados."""

    model_config = ConfigDict(strict=True)

    chunks: list[CimaChunk] = Field(default_factory=list)


class RAGAnswer(BaseModel):
    """Respuesta final del RAGPharmAgent, tras generación fundamentada en `chunks`."""

    model_config = ConfigDict(strict=True)

    answer: str
    sources: list[CimaChunk] = Field(default_factory=list)
    grounded: bool = Field(
        ..., description="False si no se encontraron fragmentos con similitud suficiente para fundamentar la respuesta."
    )
```

**Regla de negocio**: si `SearchCimaVectorDbResult.chunks` está vacío o todos sus elementos
quedan por debajo de `min_similarity`, el agente debe devolver `RAGAnswer.grounded = False`
y una respuesta que indique explícitamente la ausencia de información verificada, en lugar de
generar contenido no respaldado por recuperación.

---

## Ubicación en el código

| Tool | Adaptador ADK | Puerto de dominio |
|---|---|---|
| `extract_prescription_from_image` | `src/adapters/adk/tools/prescription_tool.py` | `src/domain/services/prescription_extraction_service.py` |
| `check_drug_interactions` | `src/adapters/adk/tools/safety_tool.py` | `src/domain/services/drug_safety_service.py` |
| `search_cima_vector_db` | `src/adapters/adk/tools/rag_tool.py` | `src/domain/services/pharma_knowledge_service.py` |

Los modelos de este documento se implementan como código real en
`src/domain/models/` (los que representan conceptos de dominio, p. ej. `DrugInteractionReport`)
o directamente en el módulo del adaptador (los que son puramente esquema de I/O de la tool,
p. ej. `*Input`), evitando duplicar la definición del dominio dentro de la capa de adaptadores.
