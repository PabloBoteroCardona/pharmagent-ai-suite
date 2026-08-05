# AGENTS.md — PharmAgent AI Suite

Especificación de los tres agentes de PharmAgent AI Suite.

**Estado real de la implementación** (actualizado tras [BLOQUE B]/[BLOQUE C]/[BLOQUE D], ver
[.memory/DECISIONS.md](.memory/DECISIONS.md)): los agentes **no** se implementan sobre el
Google Agent Development Kit (`LlmAgent`, tool-calling declarativo) — se implementan como
clases Python asíncronas simples en `src/application/agents/`, orquestando directamente los
clientes concretos (`GeminiClient`, `OllamaClient`) a través de puertos de dominio
(`src/domain/ports/`, `typing.Protocol`). La inversión de dependencias (DIP) se consigue así
sin necesitar el framework ADK: `src/application/` depende únicamente de las interfaces de
`src/domain/ports/`, nunca de las clases concretas de `src/infrastructure/`. `google-genai`
(el SDK base de Gemini, no el framework ADK completo) se usa directamente en `GeminiClient`.
Esta es una simplificación deliberada de alcance frente al diseño original de este documento
— la sección "Tipo ADK"/tool-calling de cada agente describe el diseño conceptual objetivo,
no el mecanismo de invocación real actual (invocación directa de métodos Python `async`).

Las herramientas (`tools`) descritas conceptualmente en [SKILLS.md](SKILLS.md) documentan el
contrato de entrada/salida objetivo; la implementación real expone un contrato equivalente
pero más simple vía esquemas Pydantic REST en
[drug_schemas.py](src/infrastructure/api/schemas/drug_schemas.py) — ver la nota de "Estado
real" en cada sección de SKILLS.md para el detalle de las diferencias.

---

## 1. PrescriptionAgent

**Propósito**: extraer datos estructurados de recetas médicas a partir de imágenes (foto,
escaneo o PDF) mediante comprensión multimodal.

| Campo | Valor |
|---|---|
| **Modelo** | `gemini-flash-latest` (multimodal, vía `google-genai`) — implementado ✅. Originalmente `gemini-1.5-pro` (BLOQUE B); **Google retiró ese modelo** (devuelve `404 NOT_FOUND` para claves nuevas) — descubierto y corregido durante la evaluación cuantitativa de [BLOQUE D], ver [EVALUATION.md](EVALUATION.md) |
| **Tipo de invocación** | Llamada directa a `client.aio.models.generate_content()` con `Part.from_bytes` (imagen) + prompt de sistema; `response_mime_type="application/json"` fuerza salida estructurada. Sin capa ADK/tool-calling. |
| **Ubicación real** | [`src/application/agents/prescription_agent.py`](src/application/agents/prescription_agent.py) (orquestador) + [`src/infrastructure/external/gemini_client.py`](src/infrastructure/external/gemini_client.py) (`GeminiClient`, cliente concreto) |
| **Puerto de dominio** | [`PrescriptionVisionPort`](src/domain/ports/drug_ports.py) (`typing.Protocol`) — `GeminiClient` lo satisface estructuralmente |
| **Endpoints REST** | `POST /api/v1/pharmacy/analyze-prescription` (`UploadFile`, solo extracción) y `POST /api/v1/pharmacy/process-prescription` (extracción + verificación automática de interacciones vía `ProcessPrescriptionUseCase`, ver sección 2) |
| **Modo de ejecución** | Remoto (API de Google), latencia tolerable para flujo síncrono de subida de receta — medida en [EVALUATION.md](EVALUATION.md) (~4-6s por imagen) |

### Responsabilidades
- Recibir la imagen de la receta (bytes o URI) y el contexto del paciente (opcional).
- Aplicar OCR + comprensión de layout para identificar: médico prescriptor, colegiado,
  paciente, fármacos, dosis, posología, duración del tratamiento y fecha.
- Normalizar nombres de fármacos contra el vocabulario de principios activos (para
  facilitar el cruce posterior con `SafetyCheckAgent`).
- Devolver una respuesta **estructurada y validada** (Pydantic) — nunca texto libre — junto
  con un `confidence_score` por campo para permitir revisión humana en casos dudosos.
- Señalar campos ilegibles o ambiguos como `null` en lugar de inventar datos (mitigación de
  alucinaciones en un dominio crítico para la seguridad del paciente).

### Instrucciones del sistema (resumen)
> Eres un asistente farmacéutico que transcribe recetas médicas con precisión clínica.
> Nunca inventes dosis, fármacos o datos del paciente que no sean legibles en la imagen.
> Si un campo no es legible con certeza, devuélvelo como `null` y baja su `confidence_score`.
> Responde exclusivamente invocando la herramienta `extract_prescription_from_image`.

### Entradas / salidas
- **Entrada real**: `image_bytes: bytes`, `mime_type: str` (por defecto `image/jpeg`) — vía
  `UploadFile` en el endpoint REST. `patient_id` y el diseño multi-campo con
  `confidence_score` por campo (`PrescriptionExtractionResult` en SKILLS.md) son el contrato
  objetivo, **no implementado todavía**.
- **Salida real**: `{"drugs": [{"farmaco", "dosificacion", "frecuencia", "duracion"}],
  "advertencias": [str]}` (ver `PrescriptionAnalysisResponse` en
  [drug_schemas.py](src/infrastructure/api/schemas/drug_schemas.py)) — un subconjunto más
  simple del contrato objetivo de SKILLS.md, sin `confidence_score`,
  `requires_manual_review` ni normalización de principio activo todavía.

### Consideraciones de seguridad y cumplimiento
- Las imágenes de recetas contienen datos de salud (categoría especial, RGPD/LOPDGDD). El
  cliente HTTP no persiste la imagen en disco ni en logs; **pendiente**: no hay todavía una
  capa de observabilidad que filtre explícitamente PII de las trazas de Sentry (BLOQUE B solo
  cablea la captura de errores a nivel de aplicación, sin scrubbing específico de este flujo).
- El umbral de confianza (`PRESCRIPTION_MIN_CONFIDENCE`) y el enrutado a revisión manual
  descritos como diseño objetivo **no están implementados**: hoy `GeminiClient` no calcula ni
  devuelve ningún `confidence_score`.

---

## 2. SafetyCheckAgent

**Propósito**: detectar interacciones medicamentosas, contraindicaciones y alertas de
seguridad a partir de la lista de fármacos ya extraída.

| Campo | Valor |
|---|---|
| **Modelo** | **Diseño híbrido** (añadido en [BLOQUE D]): base curada en memoria (determinista, autoritativa) + `llama3` local vía Ollama como razonamiento complementario para combinaciones no cubiertas por la base. Ya no es "ningún LLM" como en [BLOQUE C] — se acerca al diseño objetivo de esta sección (`llama-3.1` local), aunque sin el *fallback* a Gemini descrito originalmente (no implementado; ver limitación aceptada abajo) |
| **Tipo de invocación** | Método Python asíncrono (`check_interactions`, `async def` desde BLOQUE D). Consulta la base curada primero (sin red); solo si no hay coincidencia y hay un `LanguageModelPort` inyectado, llama a `OllamaClient.generate_completion` con un prompt restrictivo |
| **Ubicación real** | [`src/application/agents/safety_agent.py`](src/application/agents/safety_agent.py) |
| **Puerto de dominio** | `LanguageModelPort` (opcional, inyectado — `None` desactiva el razonamiento LLM y el agente degrada al comportamiento de BLOQUE C) — usa además directamente la entidad de dominio `DrugInteraction` ([drug_interaction.py](src/domain/models/drug_interaction.py)) |
| **Endpoints REST** | `POST /api/v1/pharmacy/check-interactions` (standalone) y `POST /api/v1/pharmacy/process-prescription` (encadenado tras `PrescriptionAgent`, ver `ProcessPrescriptionUseCase` más abajo) en `pharmacy_router.py` |
| **Modo de ejecución** | 100% local, sin dependencia de red externa (Ollama local) — cumple el objetivo de privacidad del diseño original |

### Responsabilidades
- Recibir una lista de nombres de fármacos (texto libre, p. ej. salida de `PrescriptionAgent`
  o introducidos manualmente) y normalizarlos (minúsculas, recorte de espacios) para
  comparación por subcadena contra la base curada.
- **Paso 1 — base curada (autoritativa)**: evaluar cada par conocido de
  `_KNOWN_INTERACTIONS` (6 interacciones clínicamente documentadas) y, si alguna aplica,
  devolverla tal cual (`source: "curated"`) — **nunca** se consulta al LLM en este caso,
  para no arriesgar que un modelo contradiga una interacción ya verificada.
- **Paso 2 — razonamiento LLM (complementario)**: si ningún par de la base curada aplica y
  hay un `LanguageModelPort` inyectado, consulta a `llama3` con un prompt que exige JSON
  estructurado y un campo `uncertain: bool` explícito. Las interacciones que devuelva se
  marcan `source: "llm"`.
- Emitir una recomendación explícita: `apto`, `apto_con_precaucion` o `requiere_revision_medica`.
- **Nunca** aprobar silenciosamente una combinación con interacción `HIGH`/`SEVERE` (de
  cualquier fuente) — el veredicto en ese caso es siempre `requiere_revision_medica`. Ante
  JSON del LLM inválido, vacío, o `uncertain: true`, el veredicto por defecto es también
  `requiere_revision_medica` — nunca `apto` ante incertidumbre.

**Verificación cuantitativa**: 7/7 veredictos correctos sobre un dataset sintético de 3 casos
de la base curada + 4 casos de razonamiento LLM (interacciones farmacológicas públicas
elegidas para no solapar con la base curada) — ver [EVALUATION.md](EVALUATION.md) para
metodología, latencias y un hallazgo relevante: un timeout de Ollama en una ejecución
produjo un "acierto" por coincidencia con el veredicto por defecto, no por razonamiento
real — documentado explícitamente para no sobre-representar la fiabilidad del camino LLM.

**Limitación aceptada**: la base curada es mínima y demostrativa (fines de TFM, 6 pares), no
una base de datos de interacciones clínica completa. El razonamiento LLM complementario no
está *grounded* en ninguna base de datos verificada — es conocimiento paramétrico del
modelo, con las mismas limitaciones de fiabilidad que cualquier LLM sin RAG. El *fallback* a
Gemini remoto descrito en el diseño original no está implementado (Ollama es la única fuente
de razonamiento; si no está disponible, el agente cae al comportamiento solo-curada).

### Principio rector (equivalente al prompt de sistema del diseño original)
> Prioridad absoluta: la seguridad del paciente sobre la conveniencia. Ante cualquier
> interacción `HIGH`/`SEVERE` conocida (curada o razonada por el LLM), el veredicto nunca es
> `apto` — es siempre `requiere_revision_medica`. Ante incertidumbre del modelo o fallo de
> parseo, el mismo principio aplica por defecto. Ver `LLM_SYSTEM_PROMPT` en
> [safety_agent.py](src/application/agents/safety_agent.py) para el texto exacto usado en
> el camino de razonamiento.

### Entradas / salidas
- **Entrada real**: `drugs: list[str]` (mínimo 2, ver `InteractionCheckRequest` en
  [drug_schemas.py](src/infrastructure/api/schemas/drug_schemas.py)). El diseño objetivo con
  `patient_context` (edad, alergias, medicación crónica, embarazo/lactancia) **no está
  implementado**.
- **Salida real**: `{"interactions": [{"primary_drug", "secondary_drug", "severity",
  "description", "clinical_recommendation", "source"}], "verdict"}`
  (`InteractionCheckResponse`) — `source` (`"curated"`/`"llm"`) es una adición de BLOQUE D
  sin equivalente directo en el `DrugInteractionReport` objetivo de SKILLS.md.
- Consumido directamente por el router (`/check-interactions`) o por
  [`ProcessPrescriptionUseCase`](src/use_cases/process_prescription.py) (`/process-prescription`,
  BLOQUE D) — este último es el caso de uso explícito que orquesta `PrescriptionAgent` →
  `SafetyCheckAgent` en un único flujo, con persistencia auditable (ver
  [prescription_record_model.py](src/infrastructure/models/prescription_record_model.py)).

### Consideraciones de seguridad y cumplimiento
- Al ejecutarse 100% en memoria/Ollama local, no hay salida de datos clínicos hacia terceros
  (a diferencia de un *fallback* a Gemini, no implementado).
- **Implementado en BLOQUE D**: `ProcessPrescriptionUseCase` persiste el veredicto y las
  interacciones detectadas en la tabla `prescription_records` (registro auditable) cuando se
  usa el flujo `/process-prescription`. El endpoint standalone `/check-interactions` sigue
  siendo *stateless*.

---

## 3. RAGPharmAgent

**Propósito**: responder preguntas en lenguaje natural sobre fichas técnicas de
medicamentos (AEMPS/CIMA) mediante *Retrieval-Augmented Generation*.

| Campo | Valor |
|---|---|
| **Modelo** | Ollama local: `llama3` para generación, `nomic-embed-text` (768 dim) para embeddings — **no** `gemma-2` como decía el diseño original (ver [.memory/DECISIONS.md](.memory/DECISIONS.md), "Embeddings exclusivamente locales") |
| **Tipo de invocación** | Método Python asíncrono (`answer_consultation`), sin capa ADK/tool-calling |
| **Ubicación real** | [`src/application/agents/pharmacy_agent.py`](src/application/agents/pharmacy_agent.py) (`RAGPharmAgent`), orquestado por [`ConsultDrugRAGUseCase`](src/use_cases/consult_drug_rag.py) |
| **Puerto de dominio** | `LanguageModelPort` (generación/embeddings) + `DrugService` (aplicación) sobre `CimaDataSourcePort`/`DrugRepositoryPort` ([drug_ports.py](src/domain/ports/drug_ports.py)) |
| **Endpoint REST** | `POST /api/v1/pharmacy/consult` en `pharmacy_router.py` |
| **Fuente de recuperación real** | **Solo la caché vectorial local** (`pgvector`, vía `DrugService.search_drugs_semantic`) — **corrección importante sobre el diseño original**: `/consult` no consulta CIMA en vivo en el momento de la pregunta. CIMA en vivo se consulta únicamente durante la **ingesta por lotes** (`scripts/ingest_drugs.py` → `DrugService.fetch_and_index_drug`), que puebla la caché de antemano. La estrategia dual "CIMA en vivo primero, caché como *fallback*" descrita más abajo es el diseño objetivo, no el comportamiento actual. |
| **Modo de ejecución** | 100% local en el momento de la consulta (generación + recuperación); la actualización de la caché desde CIMA es un proceso separado y asíncrono respecto a la consulta del usuario |

### Responsabilidades
- Recibir la pregunta del usuario (profesional sanitario o paciente) sobre un medicamento.
- Recuperar los 3 fármacos semánticamente más similares de la caché vectorial local
  (`DrugService.search_drugs_semantic`, embedding de la consulta + `pgvector.l2_distance`).
- Generar una respuesta **basada exclusivamente en los fragmentos recuperados** (nombre,
  principios activos, prospecto) vía el `system_prompt` grounded de `OllamaClient`.
- Si la caché no devuelve ningún fármaco relevante, el `system_prompt` indica explícitamente
  la ausencia de contexto en lugar de generar una respuesta no fundamentada — pero, a
  diferencia del diseño objetivo, no hay un campo `grounded: bool` explícito en la salida
  todavía; la ausencia de fuentes se refleja solo en `sources: []`.

**Diseño objetivo pendiente** (`search_cima_official_data`, dos fuentes con CIMA en vivo como
primaria por consulta): requeriría que `RAGPharmAgent`/`DrugService` invoquen
`CimaAPIClient` de forma síncrona a la consulta del usuario, no solo en la ingesta — fuera de
alcance de los bloques ejecutados hasta ahora.

### Principio rector (equivalente al prompt de sistema del diseño original)
> Responde únicamente con la información técnica del contexto recuperado (nombre, principios
> activos, prospecto de los fármacos más relevantes de la caché). No completes con
> conocimiento general no verificado ni inventes datos que no estén en el contexto. Si el
> contexto no contiene información suficiente, indica explícitamente que no dispones de
> información verificada y recomienda consultar a un profesional sanitario. Ver
> `SYSTEM_PROMPT` en [pharmacy_agent.py](src/application/agents/pharmacy_agent.py) para el
> texto exacto usado en producción.

### Entradas / salidas
- **Entrada real**: `query: str` (`ConsultationRequest`). `drug_name`/`nregistro` para acotar
  la búsqueda **no están implementados** — la recuperación siempre es semántica sobre toda la
  caché.
- **Salida real**: `{"query", "response", "sources": [nombre_farmaco, ...]}`
  (`ConsultationResponse`) — más simple que el `RAGAnswer` objetivo: `sources` es una lista de
  nombres, no de fragmentos con metadatos, y no hay campo `grounded: bool` explícito.
- Consumido por [`ConsultDrugRAGUseCase`](src/use_cases/consult_drug_rag.py) (caso de uso
  real, sí implementado, a diferencia del nombre `answer_pharma_query.py` del diseño
  original).

### Consideraciones de seguridad y cumplimiento
- No sustituye el prospecto oficial ni el criterio de un profesional sanitario.
  **Pendiente**: el aviso explícito al usuario final sobre esta limitación no está
  implementado todavía en la capa de presentación (`pharmacy_router.py` devuelve la
  respuesta del LLM sin un disclaimer añadido).
- Las llamadas en vivo a CIMA (`CimaAPIClient`) quedan restringidas exclusivamente al dominio
  oficial `cima.aemps.es` (`settings.cima_base_url`, no parametrizable desde la entrada de
  ningún endpoint).
- La caché vectorial se alimenta únicamente desde el script de ingesta
  (`scripts/ingest_drugs.py`), nunca desde la generación del propio LLM.

---

## Convenciones comunes a los tres agentes

- **Orquestación real**: cada agente se invoca directamente desde su propio endpoint REST en
  `pharmacy_router.py`, vía la cadena de dependencias FastAPI (`Depends`).
  `RAGPharmAgent` pasa por un caso de uso explícito (`ConsultDrugRAGUseCase`); desde
  [BLOQUE D], `PrescriptionAgent` y `SafetyCheckAgent` también se componen en un único flujo
  a través de [`ProcessPrescriptionUseCase`](src/use_cases/process_prescription.py)
  (`POST /process-prescription`: receta → extracción → verificación automática de
  interacciones si hay 2+ fármacos, con persistencia auditable). Ambos agentes siguen
  siendo invocables por separado (`/analyze-prescription`, `/check-interactions`) para casos
  de uso más simples. No existe todavía un agente orquestador de nivel superior que
  incluya también a `RAGPharmAgent` en el mismo flujo.
- **Contratos reales**: toda entrada/salida pasa por los esquemas Pydantic v2 de
  [drug_schemas.py](src/infrastructure/api/schemas/drug_schemas.py) (contrato REST real,
  más simple que los esquemas de *tool* de [SKILLS.md](SKILLS.md), que documentan el diseño
  objetivo).
- **Observabilidad real**: Sentry está cableado a nivel de aplicación
  ([main.py](src/infrastructure/api/main.py), BLOQUE B) — captura errores no controlados de
  cualquier endpoint. **Pendiente**: no hay todavía trazas por invocación de agente
  individual (latencia, modelo usado, éxito/fallback) como describía el diseño original —
  aunque sí existe una medición de latencia puntual (no continua) en
  [EVALUATION.md](EVALUATION.md).
- **Configuración real**: nombres de modelo (`gemini-flash-latest`, `llama3`,
  `nomic-embed-text`) y endpoints (`OLLAMA_BASE_URL`, `CIMA_BASE_URL`, `GOOGLE_API_KEY`) se
  leen de `src/infrastructure/config/settings.py` (`pydantic-settings`, BLOQUE A) — ya
  implementado, no pendiente. Desde BLOQUE D también centraliza `API_KEY`
  (autenticación REST) y `CORS_ALLOWED_ORIGINS`.
- **Persistencia y migraciones (BLOQUE D)**: el esquema de base de datos se gestiona con
  Alembic ([migrations/](migrations/)), no con `Base.metadata.create_all` — ver
  [README.md](README.md#migraciones-de-base-de-datos). `PrescriptionRecordModel` persiste el
  resultado de `ProcessPrescriptionUseCase` como registro auditable.
- **Autenticación y CORS (BLOQUE D)**: los endpoints de `pharmacy_router.py` exigen la
  cabecera `X-API-Key` si `settings.api_key` está configurada (`src/infrastructure/api/security.py`);
  CORS se controla vía `settings.cors_allowed_origins`. Ambos desactivados por defecto en
  desarrollo local/CI.
