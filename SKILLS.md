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

**Trigger**: invocar cuando la entrada del usuario sea una imagen (`mime-type: image/*`),
un PDF, o una solicitud explícita de digitalización de un documento físico (p. ej. "sube
una foto de tu receta", "escanea este documento").

**Guardrail / Filtro**: no invocar si el usuario ya envía la pauta en texto plano
estructurado (fármaco, dosis y posología ya legibles como texto) — en ese caso el flujo
pasa directamente a `check_drug_interactions` sin pasar por extracción de imagen.

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

**Trigger**: invocar cuando se identifiquen 2 o más principios activos en la consulta del
usuario, o inmediatamente tras una extracción de receta (`Prescription` /
`PrescriptionExtractionResult`) que resulte en 2 o más fármacos.

**Guardrail / Filtro**: no invocar si solo hay un medicamento involucrado — sin un segundo
fármaco con el que interactuar, la herramienta no aporta información y debe omitirse (no
existe interacción posible con un único principio activo).

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

## 3. `search_cima_official_data`

Usada por **RAGPharmAgent** ([AGENTS.md](AGENTS.md#3-ragpharmagent)).

Sustituye a la antigua `search_cima_vector_db`, ahora únicamente vector-first, por una
estrategia de **dos fuentes**:

- **Fuente primaria — CIMA en vivo**: consulta directamente los endpoints oficiales REST de
  la AEMPS (`https://cima.aemps.es/cima/rest/...`) vía
  [`CimaAPIClient`](src/infrastructure/external/cima_client.py) para obtener ficha técnica,
  prospecto, composición y condiciones de prescripción en tiempo real. Es la fuente de
  verdad: si responde, su resultado prevalece sobre la caché.
- **Fuente secundaria / caché — `pgvector`**: cada prospecto/ficha técnica obtenido en vivo
  se indexa de forma asíncrona en la base vectorial local (`src/adapters/rag/`) para permitir
  búsquedas semánticas (RAG) rápidas sobre apartados específicos en consultas futuras, y para
  servir de *fallback* si `cima.aemps.es` no responde (timeout, error 5xx, mantenimiento).

**Trigger**: invocar cuando:
- el usuario realice una consulta sobre posología, contraindicaciones, excipientes,
  interacciones específicas o condiciones de conservación de un fármaco concreto;
- tras identificar un medicamento en una receta extraída (`PrescriptionExtractionResult`)
  que requiera verificación contra su ficha técnica oficial.

**Guardrail / Filtro**:
- no invocar ante saludos, consultas no farmacéuticas o administrativas (p. ej. estado de un
  pedido, datos de contacto), ni cuando el contexto de la conversación ya incluye la ficha
  técnica oficial requerida para responder — evita llamadas y recuperaciones redundantes;
- la búsqueda queda restringida exclusivamente al dominio oficial `cima.aemps.es`: el cliente
  HTTP nunca acepta una base URL distinta en tiempo de ejecución (`CIMA_BASE_URL` está fijada
  en el adaptador, no es parametrizable desde la entrada de la tool), y todo `source_url`
  devuelto se valida contra ese dominio antes de exponerse al agente.

```python
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

CIMA_OFFICIAL_DOMAIN = "https://cima.aemps.es/"


class CimaDataSource(str, Enum):
    CIMA_LIVE = "cima_live"
    VECTOR_CACHE = "vector_cache"


class SearchCimaOfficialDataInput(BaseModel):
    """Entrada de la tool: consulta sobre datos oficiales de un medicamento."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=3, description="Pregunta o término de búsqueda en lenguaje natural.")
    drug_name: str | None = Field(
        default=None, description="Nombre del medicamento para acotar la búsqueda, si se conoce."
    )
    nregistro: str | None = Field(
        default=None, description="Número de registro CIMA, si ya se conoce (evita una búsqueda previa por nombre)."
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Fragmentos máximos a devolver desde la caché vectorial.")
    min_similarity: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Umbral mínimo de similitud coseno para un fragmento cacheado."
    )


class CimaFragment(BaseModel):
    """Un fragmento de información oficial sobre un medicamento, en vivo o cacheado."""

    model_config = ConfigDict(strict=True)

    drug_name: str
    cima_code: str = Field(..., description="Número de registro / código CIMA del medicamento.")
    section: str = Field(..., description="Sección de la ficha técnica o prospecto, p. ej. '4.3 Contraindicaciones'.")
    text: str
    source: CimaDataSource
    source_url: str = Field(..., description="URL del endpoint oficial de cima.aemps.es del que procede el fragmento.")
    similarity: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Similitud coseno; solo se informa para fragmentos de VECTOR_CACHE."
    )

    @field_validator("source_url")
    @classmethod
    def restrict_to_aemps_domain(cls, v: str) -> str:
        if not v.startswith(CIMA_OFFICIAL_DOMAIN):
            raise ValueError(f"source_url debe pertenecer al dominio oficial {CIMA_OFFICIAL_DOMAIN}")
        return v


class SearchCimaOfficialDataResult(BaseModel):
    """Salida de la tool: fragmentos oficiales recuperados, en vivo o desde caché."""

    model_config = ConfigDict(strict=True)

    fragments: list[CimaFragment] = Field(default_factory=list)
    primary_source_available: bool = Field(
        ..., description="True si cima.aemps.es respondió con éxito; False si se recurrió a la caché vectorial."
    )


class RAGAnswer(BaseModel):
    """Respuesta final del RAGPharmAgent, tras generación fundamentada en `fragments`."""

    model_config = ConfigDict(strict=True)

    answer: str
    sources: list[CimaFragment] = Field(default_factory=list)
    grounded: bool = Field(
        ..., description="False si ni CIMA en vivo ni la caché vectorial aportaron fragmentos para fundamentar la respuesta."
    )
```

**Reglas de negocio**:
- si la consulta en vivo a `cima.aemps.es` falla (`httpx.HTTPError`, capturado en
  [`CimaAPIClient`](src/infrastructure/external/cima_client.py), que devuelve `[]`/`None` en
  lugar de propagar la excepción), la tool recurre automáticamente a la caché vectorial y
  marca `primary_source_available = False`, sin interrumpir el flujo del agente;
- si `SearchCimaOfficialDataResult.fragments` queda vacío (ni CIMA en vivo ni la caché
  devolvieron nada, o los resultados cacheados quedan por debajo de `min_similarity`), el
  agente debe devolver `RAGAnswer.grounded = False` y una respuesta que indique
  explícitamente la ausencia de información verificada, en lugar de generar contenido no
  respaldado por recuperación;
- toda respuesta obtenida de `CIMA_LIVE` con éxito dispara, de forma asíncrona y no
  bloqueante para la respuesta al usuario, la indexación del fragmento en `pgvector`
  (mantenimiento de la caché descrito arriba).

---

## Ubicación en el código

| Tool | Adaptador ADK | Puerto de dominio | Fuentes |
|---|---|---|---|
| `extract_prescription_from_image` | `src/adapters/adk/tools/prescription_tool.py` | `src/domain/services/prescription_extraction_service.py` | — |
| `check_drug_interactions` | `src/adapters/adk/tools/safety_tool.py` | `src/domain/services/drug_safety_service.py` | — |
| `search_cima_official_data` | `src/adapters/adk/tools/rag_tool.py` | `src/domain/services/pharma_knowledge_service.py` | `src/infrastructure/external/cima_client.py` (primaria, en vivo) + `src/adapters/rag/` (`pgvector`, secundaria/caché) |

Los modelos de este documento se implementan como código real en
`src/domain/models/` (los que representan conceptos de dominio, p. ej. `DrugInteractionReport`)
o directamente en el módulo del adaptador (los que son puramente esquema de I/O de la tool,
p. ej. `*Input`), evitando duplicar la definición del dominio dentro de la capa de adaptadores.
