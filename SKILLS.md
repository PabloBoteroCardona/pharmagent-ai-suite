# SKILLS.md — Herramientas (Tools) de los agentes

Este documento define, con **Pydantic v2**, los esquemas de entrada/salida **objetivo** de
las herramientas conceptuales invocadas por los agentes descritos en [AGENTS.md](AGENTS.md).

**Estado real de la implementación**: estos esquemas documentan el diseño original de un
posible futuro tool-calling declarativo (Google ADK). La implementación actual no usa ADK ni
`src/adapters/adk/` (eliminado por estar vacío y redundante con `src/infrastructure/`)
— cada agente es invocado directamente como método `async` de una clase Python desde su
endpoint REST correspondiente, con un contrato de entrada/salida más simple definido en
[drug_schemas.py](src/infrastructure/api/schemas/drug_schemas.py). Cada sección de este
documento incluye una nota "Estado real" señalando las diferencias concretas con lo
implementado.

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

    image_bytes: bytes = Field(
        ..., description="Contenido binario de la imagen o PDF de la receta."
    )
    media_type: ImageMediaType
    patient_id: str | None = Field(
        default=None,
        description="Identificador interno del paciente, si ya está registrado.",
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

    raw_text: str = Field(
        ..., description="Texto tal como aparece en la receta, sin normalizar."
    )
    active_ingredient: str | None = Field(
        default=None,
        description="Principio activo normalizado, si se identifica con confianza suficiente.",
    )
    dose: str | None = Field(default=None, description="Dosis, p. ej. '500 mg'.")
    frequency: str | None = Field(
        default=None, description="Posología, p. ej. 'cada 8 horas'."
    )
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
        ...,
        description="True si overall_confidence o algún campo crítico está por debajo del umbral configurado.",
    )
```

**Umbral de revisión manual**: `PRESCRIPTION_MIN_CONFIDENCE` (`.env`) es diseño objetivo, no
implementado (ver "Estado real" abajo) — el nombre de archivo `process_prescription.py` que
sugiere este apartado del diseño original coincide por casualidad con
[`src/use_cases/process_prescription.py`](src/use_cases/process_prescription.py), creado en
BLOQUE D con un propósito distinto (orquestar `PrescriptionAgent` → `SafetyCheckAgent`, sin
ningún umbral de confianza): ver la nota de "Estado real" de esta tool.

**Estado real**: implementado en
[`GeminiClient.analyze_prescription_image`](src/infrastructure/external/gemini_client.py)
(modelo `gemini-flash-latest` — `gemini-1.5-pro`, usado originalmente, fue retirado por
Google; ver [EVALUATION.md](EVALUATION.md)) con un contrato más simple: entrada
`image_bytes: bytes` + `mime_type: str`; salida `{"drugs": [{"farmaco", "dosificacion",
"frecuencia", "duracion"}], "advertencias": [str]}` (`PrescriptionAnalysisResponse` en
[drug_schemas.py](src/infrastructure/api/schemas/drug_schemas.py)). No hay `confidence_score`
por campo, `requires_manual_review`, `prescriber_name`/`patient_name`/`issue_date`, ni el
umbral `PRESCRIPTION_MIN_CONFIDENCE` — todo eso es diseño objetivo, no implementado. El
guardrail de "nunca inventar datos ilegibles" sí se aplica, vía instrucción explícita en el
prompt de sistema de `GeminiClient` (verificado con una imagen real sin contenido de receta:
Gemini devolvió `drugs: []` en vez de alucinar un fármaco; y con recall=1.0 sobre 3 imágenes
sintéticas en [EVALUATION.md](EVALUATION.md)). Desde BLOQUE D, esta tool se puede encadenar
automáticamente con `check_drug_interactions` vía `POST /process-prescription`
(`ProcessPrescriptionUseCase`) — ver sección 2 y [AGENTS.md](AGENTS.md#1-prescriptionagent).

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
    mechanism: str = Field(
        ..., description="Explicación farmacológica del mecanismo de interacción."
    )
    recommendation: str = Field(
        ...,
        description="Recomendación clínica concreta, p. ej. 'espaciar tomas 4 horas'.",
    )
    source: str = Field(
        ...,
        description="Fuente de la interacción, p. ej. referencia AEMPS/CIMA o base curada.",
    )


class DrugInteractionReport(BaseModel):
    """Salida de la tool: informe de seguridad farmacológica."""

    model_config = ConfigDict(strict=True)

    interactions: list[DrugInteraction] = Field(default_factory=list)
    verdict: Verdict
    verdict_justification: str = Field(
        ...,
        description="Justificación textual del veredicto, citando las interacciones detectadas.",
    )
```

**Regla de negocio**: si `interactions` contiene alguna con `severity in {SEVERE, CONTRAINDICATED}`,
o si `patient_context` es `None` y hay medicación crónica desconocida, el `verdict` no puede ser
`FIT` (validado en `src/domain/services/drug_safety_service.py`, no confiado únicamente al LLM).

**Estado real**: implementado en
[`SafetyCheckAgent.check_interactions`](src/application/agents/safety_agent.py) (`async def`
desde BLOQUE D) con un contrato más simple: entrada `drugs: list[str]` (mínimo 2, sin
`patient_context`); salida `{"interactions": [{"primary_drug", "secondary_drug", "severity",
"description", "clinical_recommendation", "source"}], "verdict"}`
(`InteractionCheckResponse`). `severity` usa el enum de dominio `InteractionSeverity`
(`LOW`/`MEDIUM`/`HIGH`/`SEVERE`), no el `Severity` en español de este documento
(`leve`/`moderada`/`grave`/`contraindicada`); `verdict` sí conserva los mismos tres valores
(`apto`/`apto_con_precaucion`/`requiere_revision_medica`). La regla de negocio de este
apartado se cumple: `HIGH`/`SEVERE` fuerza siempre `requiere_revision_medica`, nunca `apto`,
sea cual sea la fuente.

**Diseño híbrido (BLOQUE D)**: ya no es "sin LLM" — es una búsqueda determinista contra una
base curada (20 interacciones en memoria, autoritativa, `source: "curated"`), y **solo si
ninguna coincide**, un razonamiento complementario vía `llama3` local (`source: "llm"`),
acercándose al diseño objetivo de un `SafetyCheckAgent` basado en `llama-3.1` — sin el
*fallback* a Gemini remoto descrito originalmente (no implementado, limitación aceptada).
Verificado con 7/7 veredictos correctos
sobre un dataset de evaluación sintético (3 casos de base curada + 4 de razonamiento LLM) —
ver [EVALUATION.md](EVALUATION.md) para metodología completa, latencias reales, y un
hallazgo relevante sobre un timeout de Ollama que produjo un acierto por coincidencia (no
por razonamiento genuino) en una ejecución previa.

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

    query: str = Field(
        ...,
        min_length=3,
        description="Pregunta o término de búsqueda en lenguaje natural.",
    )
    drug_name: str | None = Field(
        default=None,
        description="Nombre del medicamento para acotar la búsqueda, si se conoce.",
    )
    nregistro: str | None = Field(
        default=None,
        description="Número de registro CIMA, si ya se conoce (evita una búsqueda previa por nombre).",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Fragmentos máximos a devolver desde la caché vectorial.",
    )
    min_similarity: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Umbral mínimo de similitud coseno para un fragmento cacheado.",
    )


class CimaFragment(BaseModel):
    """Un fragmento de información oficial sobre un medicamento, en vivo o cacheado."""

    model_config = ConfigDict(strict=True)

    drug_name: str
    cima_code: str = Field(
        ..., description="Número de registro / código CIMA del medicamento."
    )
    section: str = Field(
        ...,
        description="Sección de la ficha técnica o prospecto, p. ej. '4.3 Contraindicaciones'.",
    )
    text: str
    source: CimaDataSource
    source_url: str = Field(
        ...,
        description="URL del endpoint oficial de cima.aemps.es del que procede el fragmento.",
    )
    similarity: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Similitud coseno; solo se informa para fragmentos de VECTOR_CACHE.",
    )

    @field_validator("source_url")
    @classmethod
    def restrict_to_aemps_domain(cls, v: str) -> str:
        if not v.startswith(CIMA_OFFICIAL_DOMAIN):
            raise ValueError(
                f"source_url debe pertenecer al dominio oficial {CIMA_OFFICIAL_DOMAIN}"
            )
        return v


class SearchCimaOfficialDataResult(BaseModel):
    """Salida de la tool: fragmentos oficiales recuperados, en vivo o desde caché."""

    model_config = ConfigDict(strict=True)

    fragments: list[CimaFragment] = Field(default_factory=list)
    primary_source_available: bool = Field(
        ...,
        description="True si cima.aemps.es respondió con éxito; False si se recurrió a la caché vectorial.",
    )


class RAGAnswer(BaseModel):
    """Respuesta final del RAGPharmAgent, tras generación fundamentada en `fragments`."""

    model_config = ConfigDict(strict=True)

    answer: str
    sources: list[CimaFragment] = Field(default_factory=list)
    grounded: bool = Field(
        ...,
        description="False si ni CIMA en vivo ni la caché vectorial aportaron fragmentos para fundamentar la respuesta.",
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

**Estado real**: implementado de forma más simple, con **dos fuentes por consulta pero en
orden invertido respecto al diseño original** (caché primero, CIMA en vivo como respaldo —
no CIMA primero con caché como *fallback*). `RAGPharmAgent.answer_consultation`
([pharmacy_agent.py](src/application/agents/pharmacy_agent.py)) llama a
`DrugService.search_drugs_semantic(query_o_drug_name, limit=3)`
([drug_service.py](src/application/services/drug_service.py)), que consulta primero
`pgvector` (distancia coseno con umbral de relevancia — ver
[drug_repository.py](src/infrastructure/repositories/drug_repository.py)) y, solo si no hay
resultados relevantes, invoca a `CimaAPIClient.search_medicamentos` en vivo, indexando
automáticamente los resultados encontrados. No hay `CimaDataSource`
(`CIMA_LIVE`/`VECTOR_CACHE`) ni `primary_source_available` como en el diseño objetivo, pero
sí un campo equivalente y más simple: `source: "cache"|"live"|"none"` en la salida real
(`ConsultationResponse`, ver [AGENTS.md](AGENTS.md#3-ragpharmagent)). El script de ingesta
por lotes (`scripts/ingest_drugs.py`) sigue existiendo como vía adicional para poblar la
caché de antemano, pero ya no es la única vía — una consulta de un fármaco no cacheado lo
indexa automáticamente en el momento. Verificado end-to-end contra CIMA/Ollama/Postgres
reales — ver "Verificación" en [AGENTS.md](AGENTS.md#3-ragpharmagent).

---

## Ubicación en el código

Tabla de diseño objetivo (ADK), no implementada — `src/adapters/adk/` fue eliminado por
estar vacío y redundante con `src/infrastructure/`. La implementación real es:

| Tool (diseño objetivo) | Implementación real | Puerto de dominio real | Endpoint REST |
|---|---|---|---|
| `extract_prescription_from_image` | [`GeminiClient`](src/infrastructure/external/gemini_client.py) + [`PrescriptionAgent`](src/application/agents/prescription_agent.py) | `PrescriptionVisionPort` ([drug_ports.py](src/domain/ports/drug_ports.py)) | `POST /api/v1/pharmacy/analyze-prescription` (solo extracción) / `POST /api/v1/pharmacy/process-prescription` (encadenado con `check_drug_interactions`) |
| `check_drug_interactions` | [`SafetyCheckAgent`](src/application/agents/safety_agent.py) | `LanguageModelPort` opcional (razonamiento para combinaciones no cubiertas por la base curada) + domain model `DrugInteraction` | `POST /api/v1/pharmacy/check-interactions` / `POST /api/v1/pharmacy/process-prescription` |
| `search_cima_official_data` | [`DrugService`](src/application/services/drug_service.py) + [`RAGPharmAgent`](src/application/agents/pharmacy_agent.py) | `CimaDataSourcePort` + `LanguageModelPort` + `DrugRepositoryPort` ([drug_ports.py](src/domain/ports/drug_ports.py)) | `POST /api/v1/pharmacy/search` y `POST /api/v1/pharmacy/consult` (caché primero, CIMA en vivo como respaldo automático) |

`PrescriptionRecordRepositoryPort` ([drug_ports.py](src/domain/ports/drug_ports.py)),
añadido en BLOQUE D, no corresponde a ninguna *tool* de este documento — es infraestructura
de persistencia auditable para `POST /process-prescription`
([`ProcessPrescriptionUseCase`](src/use_cases/process_prescription.py)), fuera del alcance
conceptual original de SKILLS.md.

Los modelos de este documento (`DrugInteractionReport` y esquemas afines) son el diseño
conceptual de las *tools*; el contrato REST real y más simple efectivamente implementado vive
en [drug_schemas.py](src/infrastructure/api/schemas/drug_schemas.py). Las entidades de
dominio puras (`Prescription`, `DrugInteraction`) sí están implementadas tal cual en
`src/domain/models/`.
