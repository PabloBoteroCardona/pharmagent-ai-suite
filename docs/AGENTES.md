# AGENTES.md — PharmAgent

> Este documento describe los **agentes de dominio del propio producto** PharmAgent
> (`PrescriptionAgent`, `SafetyCheckAgent`, `RAGPharmAgent`) — no es el archivo `AGENTS.md`
> de la convención abierta para instrucciones de agentes de codificación (Codex CLI, Cursor,
> etc.); esas instrucciones viven en [`CLAUDE.md`](../CLAUDE.md).

Especificación de los tres agentes de PharmAgent.

**Estado real de la implementación**: los agentes **no** se implementan sobre el
Google Agent Development Kit (`LlmAgent`, tool-calling declarativo) — se implementan como
clases Python asíncronas simples en `src/application/agents/`, orquestando directamente los
clientes concretos (`GeminiClient`, `OllamaClient`, `GroqClient`) a través de puertos de dominio
(`src/domain/ports/`, `typing.Protocol`). La inversión de dependencias (DIP) se consigue así
sin necesitar el framework ADK: `src/application/` depende únicamente de las interfaces de
`src/domain/ports/`, nunca de las clases concretas de `src/infrastructure/`. `google-genai`
(el SDK base de Gemini, no el framework ADK completo) se usa directamente en `GeminiClient`.
Esta es una simplificación deliberada de alcance frente al diseño original de este documento
— la sección "Tipo ADK"/tool-calling de cada agente describe el diseño conceptual objetivo,
no el mecanismo de invocación real actual (invocación directa de métodos Python `async`).

Las herramientas (`tools`) descritas conceptualmente en [HERRAMIENTAS.md](HERRAMIENTAS.md) documentan el
contrato de entrada/salida objetivo; la implementación real expone un contrato equivalente
pero más simple vía esquemas Pydantic REST en
[drug_schemas.py](../src/infrastructure/api/schemas/drug_schemas.py) — ver la nota de "Estado
real" en cada sección de HERRAMIENTAS.md para el detalle de las diferencias.

---

## 1. PrescriptionAgent

**Propósito**: extraer datos estructurados de recetas médicas a partir de imágenes (foto,
escaneo o PDF) mediante comprensión multimodal.

| Campo | Valor |
|---|---|
| **Modelo** | `gemini-flash-latest` (multimodal, vía `google-genai`) — implementado. Originalmente `gemini-1.5-pro` (BLOQUE B); **Google retiró ese modelo** (devuelve `404 NOT_FOUND` para claves nuevas) — descubierto y corregido durante la evaluación cuantitativa de [BLOQUE D], ver [EVALUATION.md](../EVALUATION.md) |
| **Tipo de invocación** | Llamada directa a `client.aio.models.generate_content()` con `Part.from_bytes` (imagen) + prompt de sistema; `response_mime_type="application/json"` fuerza salida estructurada. Sin capa ADK/tool-calling. |
| **Ubicación real** | [`src/application/agents/prescription_agent.py`](../src/application/agents/prescription_agent.py) (orquestador) + [`src/infrastructure/external/gemini_client.py`](../src/infrastructure/external/gemini_client.py) (`GeminiClient`, cliente concreto) |
| **Puerto de dominio** | [`PrescriptionVisionPort`](../src/domain/ports/drug_ports.py) (`typing.Protocol`) — `GeminiClient` lo satisface estructuralmente |
| **Endpoints REST** | `POST /api/v1/pharmacy/analyze-prescription` (`UploadFile`, solo extracción) y `POST /api/v1/pharmacy/process-prescription` (extracción + verificación automática de interacciones vía `ProcessPrescriptionUseCase`, ver sección 2) |
| **Modo de ejecución** | Remoto (API de Google), latencia tolerable para flujo síncrono de subida de receta — medida en [EVALUATION.md](../EVALUATION.md) (~4-6s por imagen) |

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
  `confidence_score` por campo (`PrescriptionExtractionResult` en HERRAMIENTAS.md) son el contrato
  objetivo, **no implementado todavía**.
- **Salida real**: `{"drugs": [{"farmaco", "dosificacion", "frecuencia", "duracion"}],
  "advertencias": [str]}` (ver `PrescriptionAnalysisResponse` en
  [drug_schemas.py](../src/infrastructure/api/schemas/drug_schemas.py)) — un subconjunto más
  simple del contrato objetivo de HERRAMIENTAS.md, sin `confidence_score`,
  `requires_manual_review` ni normalización de principio activo todavía.

### Consideraciones de seguridad y cumplimiento
- Las imágenes de recetas contienen datos de salud (categoría especial, RGPD/LOPDGDD) y con
  frecuencia datos identificativos directos (nombre del paciente, DNI/NIE, dirección) —
  no solo "datos de salud" en abstracto. `GeminiClient` envía la **imagen completa** a
  Gemini; el filtrado solo puede actuar sobre lo que el modelo devuelve, no sobre lo que
  Google procesa en sus servidores antes de responder — riesgo real, no eliminado. Decisión
  completa, incluyendo por qué un aviso/casilla no basta legalmente como mitigación única, en
  [ADR 002](adr/002-datos-personales-foto-receta.md).
  - **Despliegue público** (`VITE_DEMO_MODE=true` + `DEMO_MODE=true`): no se acepta ninguna
    foto real — la pestaña de Receta solo ofrece imágenes de ejemplo sintéticas, y el
    backend rechaza con 403 cualquier imagen que no sea una de ellas
    (`src/infrastructure/api/demo_mode.py`), aunque se llame a la API directamente sin pasar
    por la interfaz. Elimina el riesgo en vez de gestionarlo.
  - **Desarrollo local**: mitigaciones en profundidad — `SYSTEM_PROMPT` instruye a no incluir
    ningún dato identificativo en la respuesta; el resultado extraído es lo único que se
    persiste (la imagen no se guarda en disco ni en logs); el frontend exige una casilla de
    confirmación explícita antes de habilitar el envío, junto a un aviso de que subir datos
    identificativos de terceros con un dato de salud sin su consentimiento puede infringir el
    RGPD/LOPDGDD.
  - **Pendiente**: no hay todavía una capa de observabilidad que filtre explícitamente PII de
    las trazas de Sentry (BLOQUE B solo cablea la captura de errores a nivel de aplicación,
    sin scrubbing específico de este flujo); un uso real con pacientes reales, más allá de
    desarrollo/demo, necesitaría además un acuerdo de encargado de tratamiento con Google.
- El umbral de confianza (`PRESCRIPTION_MIN_CONFIDENCE`) y el enrutado a revisión manual
  descritos como diseño objetivo **no están implementados**: hoy `GeminiClient` no calcula ni
  devuelve ningún `confidence_score`.

---

## 2. SafetyCheckAgent

**Propósito**: detectar interacciones medicamentosas, contraindicaciones y alertas de
seguridad a partir de la lista de fármacos ya extraída.

| Campo | Valor |
|---|---|
| **Modelo** | **Diseño híbrido** (añadido en [BLOQUE D]): base curada en memoria (determinista, autoritativa) + `llama-3.1-8b-instant` en la nube vía Groq como razonamiento complementario para combinaciones no cubiertas por la base. Antes de migrar a Groq el modelo era `llama3` local vía Ollama — sustituido por latencia (~30s en CPU local frente a <2s en Groq) |
| **Tipo de invocación** | Método Python asíncrono (`check_interactions`, `async def` desde BLOQUE D). Consulta la base curada primero (sin red); solo si no hay coincidencia y hay un `LanguageModelPort` inyectado, llama a `GroqClient.generate_completion` con un prompt restrictivo |
| **Ubicación real** | [`src/application/agents/safety_agent.py`](../src/application/agents/safety_agent.py) |
| **Puerto de dominio** | `LanguageModelPort` (opcional, inyectado — `None` desactiva el razonamiento LLM y el agente degrada al comportamiento de BLOQUE C) — usa además directamente la entidad de dominio `DrugInteraction` ([drug_interaction.py](../src/domain/models/drug_interaction.py)) |
| **Endpoints REST** | `POST /api/v1/pharmacy/check-interactions` (standalone) y `POST /api/v1/pharmacy/process-prescription` (encadenado tras `PrescriptionAgent`, ver `ProcessPrescriptionUseCase` más abajo) en `pharmacy_router.py` |
| **Modo de ejecución** | Base curada 100% local (sin red); razonamiento LLM complementario en la nube (Groq) desde la migración a Groq — los nombres de fármaco evaluados salen de la máquina en ese camino, ya no es "100% local" como antes de la migración |

### Responsabilidades
- Recibir una lista de nombres de fármacos (texto libre, p. ej. salida de `PrescriptionAgent`
  o introducidos manualmente) y normalizarlos (minúsculas, recorte de espacios) para
  comparación por subcadena contra la base curada.
- **Paso 1 — base curada (autoritativa)**: evaluar cada par conocido de
  `_KNOWN_INTERACTIONS` (20 interacciones clínicamente documentadas) y, si alguna aplica,
  devolverla tal cual (`source: "curated"`) — **nunca** se consulta al LLM en este caso,
  para no arriesgar que un modelo contradiga una interacción ya verificada.
- **Paso 2 — razonamiento LLM (complementario)**: si ningún par de la base curada aplica y
  hay un `LanguageModelPort` inyectado, consulta a `llama-3.1-8b-instant` (Groq) con un
  prompt que exige JSON estructurado y un campo `uncertain: bool` explícito. Las
  interacciones que devuelva se marcan `source: "llm"`.
- Emitir una recomendación explícita: `apto`, `apto_con_precaucion` o `requiere_revision_medica`.
- **Nunca** aprobar silenciosamente una combinación con interacción `HIGH`/`SEVERE` (de
  cualquier fuente) — el veredicto en ese caso es siempre `requiere_revision_medica`. Ante
  JSON del LLM inválido, vacío, o `uncertain: true`, el veredicto por defecto es también
  `requiere_revision_medica` — nunca `apto` ante incertidumbre.

**Verificación cuantitativa**: 7/7 veredictos correctos sobre un dataset sintético de 3 casos
de la base curada + 4 casos de razonamiento LLM (interacciones farmacológicas públicas
elegidas para no solapar con la base curada) — ver [EVALUATION.md](../EVALUATION.md) para
metodología, latencias y un hallazgo relevante: un timeout de Ollama en una ejecución
produjo un "acierto" por coincidencia con el veredicto por defecto, no por razonamiento
real — documentado explícitamente para no sobre-representar la fiabilidad del camino LLM.

**Limitación aceptada**: la base curada es mínima y demostrativa (fines de TFM, 20 pares), no
una base de datos de interacciones clínica completa. El razonamiento LLM complementario no
está *grounded* en ninguna base de datos verificada — es conocimiento paramétrico del
modelo, con las mismas limitaciones de fiabilidad que cualquier LLM sin RAG. El *fallback* a
Gemini remoto descrito en el diseño original no está implementado (Groq es la única fuente
de razonamiento desde la migración; si `GROQ_API_KEY` no está configurada o la API no está
disponible, el agente cae al comportamiento solo-curada).

### Principio rector (equivalente al prompt de sistema del diseño original)
> Prioridad absoluta: la seguridad del paciente sobre la conveniencia. Ante cualquier
> interacción `HIGH`/`SEVERE` conocida (curada o razonada por el LLM), el veredicto nunca es
> `apto` — es siempre `requiere_revision_medica`. Ante incertidumbre del modelo o fallo de
> parseo, el mismo principio aplica por defecto. Ver `LLM_SYSTEM_PROMPT` en
> [safety_agent.py](../src/application/agents/safety_agent.py) para el texto exacto usado en
> el camino de razonamiento.

### Entradas / salidas
- **Entrada real**: `drugs: list[str]` (mínimo 2, ver `InteractionCheckRequest` en
  [drug_schemas.py](../src/infrastructure/api/schemas/drug_schemas.py)). El diseño objetivo con
  `patient_context` (edad, alergias, medicación crónica, embarazo/lactancia) **no está
  implementado**.
- **Salida real**: `{"interactions": [{"primary_drug", "secondary_drug", "severity",
  "description", "clinical_recommendation", "source"}], "verdict"}`
  (`InteractionCheckResponse`) — `source` (`"curated"`/`"llm"`) es una adición de BLOQUE D
  sin equivalente directo en el `DrugInteractionReport` objetivo de HERRAMIENTAS.md.
- Consumido directamente por el router (`/check-interactions`) o por
  [`ProcessPrescriptionUseCase`](../src/use_cases/process_prescription.py) (`/process-prescription`,
  BLOQUE D) — este último es el caso de uso explícito que orquesta `PrescriptionAgent` →
  `SafetyCheckAgent` en un único flujo, con persistencia auditable (ver
  [prescription_record_model.py](../src/infrastructure/models/prescription_record_model.py)).

### Consideraciones de seguridad y cumplimiento
- La base curada (camino prioritario) se evalúa 100% en memoria, sin red. El razonamiento
  LLM complementario (Groq, desde la migración de Ollama local) sí envía los nombres de
  fármaco evaluados a un tercero — una salida de datos que no existía cuando el razonamiento
  era Ollama local.
  Es una decisión consciente de intercambiar esa privacidad estricta por latencia (~30s → <2s);
  no se envían datos identificativos del paciente, solo nombres de fármacos.
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
| **Modelo** | Groq (`llama-3.1-8b-instant`) para generación, migrado por latencia (~30s en CPU local frente a <2s en Groq); Ollama local (`nomic-embed-text`, 768 dim) para embeddings, sin cambios y exclusivamente local (nunca un proveedor externo) — **no** `gemma-2` como decía el diseño original. Antes de la migración, la generación también era Ollama local (`llama3`) |
| **Tipo de invocación** | Método Python asíncrono (`answer_consultation`), sin capa ADK/tool-calling |
| **Ubicación real** | [`src/application/agents/pharmacy_agent.py`](../src/application/agents/pharmacy_agent.py) (`RAGPharmAgent`), orquestado por [`ConsultDrugRAGUseCase`](../src/use_cases/consult_drug_rag.py) |
| **Puerto de dominio** | `LanguageModelPort` (generación/embeddings) + `DrugService` (aplicación) sobre `CimaDataSourcePort`/`DrugRepositoryPort` ([drug_ports.py](../src/domain/ports/drug_ports.py)) |
| **Endpoint REST** | `POST /api/v1/pharmacy/consult` en `pharmacy_router.py` |
| **Fuente de recuperación real** | **Caché vectorial local primero, CIMA en vivo como respaldo automático** (`DrugService.search_drugs_semantic`) — implementado como corrección posterior a que una consulta sobre un medicamento no pre-cargado no devolviera nada. Si la caché no tiene un resultado suficientemente relevante, `DrugService` consulta `CimaAPIClient.search_medicamentos` en vivo, indexa automáticamente los primeros resultados (embedding + persistencia) y los devuelve — consultas futuras sobre el mismo fármaco son entonces instantáneas (cache hit). Se prioriza caché-primero sobre CIMA-primero (orden invertido respecto al diseño original de HERRAMIENTAS.md) por rendimiento: evita un *round-trip* a CIMA en cada consulta de un fármaco ya conocido, sin sacrificar corrección. |
| **Modo de ejecución** | Búsqueda: local en el caso más común (fármaco ya cacheado); remoto (CIMA) solo la primera vez que se pregunta por un fármaco nuevo — latencia medida ~0.1-1.3s para la búsqueda en vivo (ver verificación abajo). Generación: remoto (Groq) desde la migración, <2s frente a los ~30s de Ollama local en CPU. |

### Responsabilidades
- Recibir la pregunta del usuario (profesional sanitario o paciente) sobre un medicamento,
  y opcionalmente el nombre del fármaco (`drug_name`) para acotar la búsqueda.
- Recuperar los fármacos relevantes vía `DrugService.search_drugs_semantic`: primero contra
  la caché vectorial (embedding de `drug_name` o `query` + `pgvector.cosine_distance`,
  filtrado por un umbral de relevancia — ver nota sobre la métrica más abajo); si no hay
  resultados relevantes, busca en vivo en CIMA por nombre y los indexa.
- Generar una respuesta **basada exclusivamente en los fragmentos recuperados** (nombre,
  principios activos, ficha técnica y prospecto — la ficha técnica se prioriza para
  preguntas clínicas/de dosificación, más completa que el prospecto) vía el
  `system_prompt` grounded de `GroqClient`. La respuesta incluye además enlaces directos
  a la ficha técnica y al prospecto oficiales de CIMA de cada fármaco citado
  (`ConsultationResponse.sources[].ficha_tecnica_url`/`.prospecto_url`).
- Si ni la caché ni CIMA en vivo devuelven nada relevante, el `system_prompt` indica
  explícitamente la ausencia de contexto — la salida además expone `source: "cache"|"live"|"none"`
  para que el consumidor sepa la procedencia (ver "Entradas/salidas" abajo); sigue sin haber
  un campo `grounded: bool` explícito como en el diseño objetivo.

**Nota sobre la métrica de relevancia**: la caché usa distancia coseno (no L2, usada
originalmente) — se comprobó empíricamente contra la caché real del proyecto que L2 es
sensible a la longitud del texto comparado, no solo a su contenido semántico (una consulta
de una palabra queda artificialmente lejos incluso del fármaco exacto que describe), lo que
haría casi imposible un cache hit real. Ver comentario extenso en
[drug_repository.py](../src/infrastructure/repositories/drug_repository.py). El umbral
(`MAX_RELEVANT_COSINE_DISTANCE = 0.35`) es una heurística calibrada con `nomic-embed-text`,
no una garantía: el modelo (no especializado en farmacia) a veces no distingue bien fármacos
relacionados por mecanismo (p. ej. "omeprazol" vs. "esomeprazol" ya cacheado) — en esos
casos el sistema cae al respaldo de CIMA en vivo en vez de acertar con el cache hit, lo cual
es un comportamiento aceptable (una consulta extra a CIMA), no una respuesta incorrecta.

**Búsqueda en vivo por nombre, no semántica**: CIMA hace coincidencia literal de nombre
(`search_medicamentos`), no búsqueda semántica — una pregunta en lenguaje natural sin el
nombre del fármaco de forma literal (p. ej. "¿qué tomar para el dolor de cabeza?") no
encontrará nada en CIMA aunque exista un fármaco relevante. Por eso `drug_name` existe como
parámetro separado de `query`: acota la búsqueda al nombre exacto cuando se conoce, mientras
`query` sigue siendo la pregunta real enviada al LLM para generar la respuesta.

### Principio rector (equivalente al prompt de sistema del diseño original)
> Responde únicamente con la información técnica del contexto recuperado (nombre, principios
> activos, prospecto de los fármacos más relevantes de la caché). No completes con
> conocimiento general no verificado ni inventes datos que no estén en el contexto. Si el
> contexto no contiene información suficiente, indica explícitamente que no dispones de
> información verificada y recomienda consultar a un profesional sanitario. Ver
> `SYSTEM_PROMPT` en [pharmacy_agent.py](../src/application/agents/pharmacy_agent.py) para el
> texto exacto usado en producción.

### Entradas / salidas
- **Entrada real**: `query: str` + `drug_name: str | None` (`ConsultationRequest`) — `drug_name`
  sí está implementado (a diferencia de versiones anteriores de este documento); `nregistro`
  para acotar por número de registro exacto sigue sin implementarse.
- **Salida real**: `{"query", "response", "sources": [nombre_farmaco, ...], "source":
  "cache"|"live"|"none"}` (`ConsultationResponse`) — más simple que el `RAGAnswer` objetivo:
  `sources` es una lista de nombres, no de fragmentos con metadatos, y `source` (procedencia
  agregada) sustituye al `grounded: bool` explícito del diseño objetivo sin ser equivalente.
- Consumido por [`ConsultDrugRAGUseCase`](../src/use_cases/consult_drug_rag.py) (caso de uso
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
- La caché vectorial se alimenta desde el script de ingesta por lotes
  (`scripts/ingest_drugs.py`) **y** automáticamente desde el respaldo en vivo de
  `DrugService.search_drugs_semantic` — en ambos casos, el contenido persistido procede
  siempre de CIMA, nunca de la generación del propio LLM.

### Verificación
Comportamiento verificado end-to-end contra CIMA/Ollama/Postgres reales (no dobles de
test): `enalapril` (fármaco no cacheado, sí existente en CIMA) devolvió `source: "live"` en
~0.76s, indexándose automáticamente; una segunda consulta del mismo fármaco devolvió
`source: "cache"` en ~0.04s. `warfarina` (nombre no reconocido por la búsqueda literal de
CIMA — en España se comercializa como "Aldocumar") devolvió `source: "none"`, confirmando
que el respaldo depende de que CIMA reconozca el nombre exacto, no es una garantía universal.
`POST /consult` con `drug_name="losartan"` probado vía HTTP real: primera llamada degradó
`response: ""` por el timeout de 60s de `OllamaClient` (arranque en frío conocido de Ollama,
no un fallo del respaldo en vivo — `source: "live"` y `sources` sí llegaron correctamente);
segunda llamada con el fármaco ya cacheado generó una
respuesta completa citando los 3 medicamentos de losartán encontrados.

---

## Convenciones comunes a los tres agentes

- **Orquestación real**: cada agente se invoca directamente desde su propio endpoint REST en
  `pharmacy_router.py`, vía la cadena de dependencias FastAPI (`Depends`).
  `RAGPharmAgent` pasa por un caso de uso explícito (`ConsultDrugRAGUseCase`); desde
  [BLOQUE D], `PrescriptionAgent` y `SafetyCheckAgent` también se componen en un único flujo
  a través de [`ProcessPrescriptionUseCase`](../src/use_cases/process_prescription.py)
  (`POST /process-prescription`: receta → extracción → verificación automática de
  interacciones si hay 2+ fármacos, con persistencia auditable). Ambos agentes siguen
  siendo invocables por separado (`/analyze-prescription`, `/check-interactions`) para casos
  de uso más simples. No existe todavía un agente orquestador de nivel superior que
  incluya también a `RAGPharmAgent` en el mismo flujo.
- **Contratos reales**: toda entrada/salida pasa por los esquemas Pydantic v2 de
  [drug_schemas.py](../src/infrastructure/api/schemas/drug_schemas.py) (contrato REST real,
  más simple que los esquemas de *tool* de [HERRAMIENTAS.md](HERRAMIENTAS.md), que documentan el diseño
  objetivo).
- **Observabilidad real**: Sentry está cableado a nivel de aplicación
  ([main.py](../src/infrastructure/api/main.py), BLOQUE B) — captura errores no controlados de
  cualquier endpoint. **Pendiente**: no hay todavía trazas por invocación de agente
  individual (latencia, modelo usado, éxito/fallback) como describía el diseño original —
  aunque sí existe una medición de latencia puntual (no continua) en
  [EVALUATION.md](../EVALUATION.md).
- **Configuración real**: nombres de modelo (`gemini-flash-latest`, `llama-3.1-8b-instant`
  vía Groq, `nomic-embed-text`) y endpoints (`OLLAMA_BASE_URL`, `GROQ_BASE_URL`,
  `CIMA_BASE_URL`, `GOOGLE_API_KEY`) se leen de `src/infrastructure/config/settings.py`
  (`pydantic-settings`, BLOQUE A) — ya implementado, no pendiente. También centraliza
  `CORS_ALLOWED_ORIGINS`.
- **Persistencia y migraciones (BLOQUE D)**: el esquema de base de datos se gestiona con
  Alembic ([migrations/](../migrations/)), no con `Base.metadata.create_all` — ver
  [README.md](../README.md#migraciones-de-base-de-datos). `PrescriptionRecordModel` persiste el
  resultado de `ProcessPrescriptionUseCase` como registro auditable.
- **CORS (BLOQUE D)**: `settings.cors_allowed_origins` (`["*"]` por defecto en desarrollo
  local/CI, restringir al dominio real en un despliegue público). Autenticación por API key
  opcional (`settings.api_key`, `security.py`) + rate limiting por IP (`slowapi`, `main.py`)
  — desactivados por defecto para consumo local sin fricción, activables antes de exponer la
  API a Internet. Ver [README.md, "Seguridad en un despliegue público"](../README.md#seguridad-en-un-despliegue-público).
