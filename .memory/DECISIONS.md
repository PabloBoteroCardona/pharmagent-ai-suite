# DECISIONS.md — PharmAgent AI Suite

Registro de decisiones clave de arquitectura tomadas durante el desarrollo, complementario a
los ADR formales en [docs/adr/](../docs/adr/).

## CIMA en vivo como respaldo real de `/search` y `/consult` (no solo en la ingesta)

**Contexto**: el usuario preguntó explícitamente si consultar interacciones o un medicamento
concreto consultaba CIMA en tiempo real "reduciendo la pérdida de tiempo por otros métodos".
La respuesta honesta era **no**: `/check-interactions` nunca toca CIMA (no tiene sentido —
CIMA es una base de fichas técnicas, no un comprobador de interacciones), y `/search`/`/consult`
solo miraban la caché vectorial local, poblada exclusivamente por un script de ingesta manual
de 12 fármacos. Preguntar por cualquier fármaco fuera de esos 12 devolvía vacío, aunque CIMA
lo tuviera perfectamente disponible. El usuario pidió corregirlo: "si no de que sirve".

**Decisión**: `DrugService.search_drugs_semantic` ahora consulta primero la caché vectorial
y, si no hay resultados relevantes, cae automáticamente a una búsqueda en vivo en CIMA
(`CimaAPIClient.search_medicamentos`), indexando los primeros `LIVE_FALLBACK_MAX_RESULTS=3`
resultados encontrados (mismo criterio que `scripts/ingest_drugs.py`). Se prioriza
caché-primero sobre CIMA-primero (invirtiendo el orden del diseño objetivo de SKILLS.md) por
rendimiento: evita un *round-trip* de red en cada consulta de un fármaco ya conocido. Devuelve
un `DrugSearchResult(drugs, source)` con `source: "cache"|"live"|"none"` para que
`/search`/`/consult` expongan la procedencia. `RAGPharmAgent.answer_consultation` y
`ConsultDrugRAGUseCase.execute` ganaron un parámetro opcional `drug_name` — CIMA hace
coincidencia literal de nombre, no búsqueda semántica, así que una pregunta en lenguaje
natural sin el nombre exacto del fármaco no lo encontraría en CIMA aunque exista.

**Bug real encontrado y corregido durante la implementación — métrica de relevancia**:
la primera versión usó un umbral sobre `pgvector.l2_distance` (igual que ya usaba
`search_similar_by_vector`) para decidir si la caché "tenía algo relevante". Al verificar
contra la base real (Postgres + `nomic-embed-text` vía Ollama), se descubrió que la distancia
L2 es sensible a la longitud del texto comparado, no solo a su contenido semántico: la
consulta de una palabra `"metformina"` medía L2≈16.6 incluso frente al *propio* fármaco de
metformina recién indexado, mientras que consultas más largas del mismo fármaco medían
L2≈5.4-9.9 sin ser más relevantes — con cualquier umbral razonable, un fármaco recién
cacheado no producía un cache hit en su siguiente consulta corta, rompiendo el propósito de
cachear. Se sustituyó por `pgvector.cosine_distance`, que normaliza por magnitud y no tiene
ese problema: en las mismas pruebas, consultas relevantes midieron coseno≈0.24-0.33 y
consultas irrelevantes coseno≈0.38-0.48, con separación estable independiente de la longitud
de la consulta. Umbral fijado en `MAX_RELEVANT_COSINE_DISTANCE = 0.35`
([drug_repository.py](../src/infrastructure/repositories/drug_repository.py)) — es una
heurística calibrada empíricamente para este modelo de embedding, no una garantía: el modelo
(no especializado en farmacia) no siempre distingue bien fármacos relacionados por mecanismo
(p. ej. "omeprazol" quedó tan lejos de "esomeprazol" ya cacheado como de fármacos no
relacionados), en cuyo caso el sistema cae al respaldo de CIMA en vivo — una consulta extra,
no una respuesta incorrecta.

**Verificación contra servicios reales** (no solo dobles de test): con Postgres/Ollama/CIMA
reales corriendo, `enalapril` (no cacheado, sí existente en CIMA) devolvió `source: "live"`
en ~0.76s e indexó 3 resultados; una segunda consulta del mismo fármaco devolvió
`source: "cache"` en ~0.04s. `amlodipino` y `losartan` probados igual, vía HTTP real
(`POST /search`, `POST /consult` con `drug_name`) contra el servidor Uvicorn levantado en
local, con resultado `source: "live"` correcto en ambos. `warfarina` devolvió `source: "none"`
— CIMA no reconoce ese nombre porque en España se comercializa como "Aldocumar" (confirmado
consultando CIMA directamente), demostrando el límite real de la búsqueda por nombre literal,
no un fallo del mecanismo. Una llamada a `/consult` con un fármaco recién indexado en vivo
degradó `response: ""` la primera vez por el timeout de 60s de `OllamaClient` (arranque en
frío, comportamiento ya documentado en [BUGS.md](BUGS.md), no relacionado con este cambio) —
`source: "live"` y `sources` sí llegaron correctamente en esa misma respuesta; una segunda
llamada con el fármaco ya cacheado generó la respuesta completa sin problema.

**Alcance explícitamente no cubierto**: `/check-interactions` sigue sin consultar CIMA — no
existe ningún endpoint de CIMA para verificar interacciones entre fármacos (es una base de
fichas técnicas, no un comprobador de interacciones), así que no había nada que corregir ahí;
la verificación de interacciones sigue dependiendo exclusivamente de la base curada +
razonamiento LLM (ver bloque de decisión de BLOQUE D más abajo).

**Verificación**: 114 tests (`pytest`, subieron de 99 con 15 tests nuevos: `test_drug_service.py`,
`test_pharmacy_agent.py`, casos nuevos en `test_consult_use_case.py` y
`test_api_endpoints.py`), `ruff check .`/`ruff format --check .` limpios.

---

## [BLOQUE D] Profesionalización: auth, Docker, orquestación, SafetyCheckAgent híbrido, persistencia, Alembic, evaluación

**Contexto**: tras cerrar [BLOQUE A]/[B]/[C], se pidió una evaluación crítica del proyecto
(ver conversación) que señaló puntos débiles concretos: `SafetyCheckAgent` sin ningún LLM
(solo tabla curada), `RAGPharmAgent` sin CIMA en vivo por petición, sin autenticación ni
CORS, sin persistencia real de recetas procesadas, esquema de BD gestionado con
`create_all` en vez de migraciones versionadas, sin tests directos de los clientes HTTP
externos, sin medición de cobertura, y sin ninguna evaluación cuantitativa de exactitud. El
usuario pidió corregir "todo lo necesario para que quede un proyecto profesional"; ante una
pregunta de alcance rechazada por el usuario, se procedió con criterio propio, implementando
9 mejoras concretas en un orden priorizado.

**Decisiones y resultados, en orden de ejecución:**

1. **CORS + API key**: `settings.api_key`/`cors_allowed_origins` nuevos;
   [security.py](../src/infrastructure/api/security.py) (`verify_api_key`, dependencia a
   nivel de router — protege los 6 endpoints de `pharmacy_router` de una vez, `/health`
   queda fuera). Si `API_KEY` no está configurada (por defecto en local/CI), la
   autenticación queda desactivada — evita fricción en evaluación del TFM.
   `CORSMiddleware` en `main.py`.
2. **Dockerfile + servicio `api` en Compose**: imagen `python:3.12-slim`, usuario no-root.
   **Verificado con Docker Desktop real**: build exitoso, contenedor arranca y responde
   `/health` → 200; tras el paso 6 (Alembic), el contenedor ejecuta `alembic upgrade head`
   antes de Uvicorn.
3. **Orquestación end-to-end**:
   [`ProcessPrescriptionUseCase`](../src/use_cases/process_prescription.py) — `PrescriptionAgent`
   → (si 2+ fármacos) → `SafetyCheckAgent`, endpoint `POST /process-prescription`. Antes,
   ambos agentes solo existían como endpoints aislados sin flujo natural entre ellos.
4. **`SafetyCheckAgent` híbrido**: la base curada sigue siendo la fuente **autoritativa** (si
   aplica, nunca se consulta al LLM — evita que un modelo contradiga una interacción ya
   verificada). Para combinaciones no cubiertas, si se inyecta un `LanguageModelPort`
   (Ollama), se consulta con un prompt que exige JSON + campo `uncertain: bool`. Cada
   interacción lleva `source: "curated"|"llm"`. Ante JSON inválido, vacío, o
   `uncertain: true`, el veredicto por defecto es `requiere_revision_medica` — nunca
   aprobación silenciosa. `check_interactions` pasó a ser `async`.
5. **Persistencia auditable**: `PrescriptionRecordModel`
   ([prescription_record_model.py](../src/infrastructure/models/prescription_record_model.py))
   — decisión explícita de **no** mapear a la entidad de dominio estricta
   `Prescription`/`PrescribedDrug` (que exige `frequency_hours: int`/`duration_days: int`)
   porque `GeminiClient` devuelve texto libre (`"cada 8 horas"`) y forzarlo a un entero sería
   una conversión no verificada en datos de salud. Se persiste el JSON crudo de la
   extracción + el resultado de seguridad, como registro auditable.
   `PrescriptionRecordRepository` + `PrescriptionRecordRepositoryPort`, inyectado
   opcionalmente en `ProcessPrescriptionUseCase`.
6. **Migraciones Alembic**: `src/infrastructure/init_db.py` **eliminado**
   (`Base.metadata.create_all` sustituido por migraciones versionadas).
   `migrations/env.py` usa `settings.database_url` y `Base.metadata` reales (autogenerate
   funcional, no manual). Primera migración `272aeb551e68`. Bug real encontrado y corregido
   en la migración autogenerada: faltaba `import pgvector.sqlalchemy` (referenciado pero no
   importado) y `CREATE EXTENSION IF NOT EXISTS vector` (antes en `init_db.py`, no
   trasladado automáticamente por Alembic). **Verificado con upgrade/downgrade/upgrade real
   contra Postgres**, y con el contenedor Docker completo. Nuevo job `migrations` en CI que
   aplica y revierte la migración contra un Postgres de servicio en GitHub Actions.
7. **Tests directos de clientes externos**: `test_cima_client.py`, `test_ollama_client.py`
   (ambos con `httpx.MockTransport`, sin red real) y `test_gemini_client.py` (mock del SDK
   `google-genai`) — cubren el manejo defensivo de errores (`httpx.HTTPError`,
   `json.JSONDecodeError`, `APIError`, timeouts, cuerpos vacíos/malformados) que antes solo
   se ejercitaba indirectamente a través de dobles en los tests de integración.
8. **Cobertura de tests**: `pytest-cov` añadido; `.coveragerc` (branch coverage);
   `--cov-fail-under=85` en CI (cobertura real medida: ~87%). Los módulos con menor
   cobertura (`DrugRepository`/`PrescriptionRecordRepository`, ~40-50%) requieren una sesión
   real de SQLAlchemy/Postgres para testear directamente — se aceptó el umbral 85% en vez de
   perseguir 100% forzando tests de infraestructura de bajo valor.
9. **Evaluación cuantitativa**: [evaluation/](../evaluation/) — dataset sintético (7 casos
   de interacciones + 3 recetas), generador de imágenes con Pillow, script de métricas
   (`evaluation/run_evaluation.py`), resultados documentados en
   [EVALUATION.md](../EVALUATION.md). **Hallazgo relevante durante la evaluación**: el
   modelo `gemini-1.5-pro` (usado desde BLOQUE B) resultó estar **retirado por Google**
   (`404 NOT_FOUND` para esta API key) — causaba que `PrescriptionAgent` devolviera
   `drugs: []` silenciosamente en producción. Corregido a `gemini-flash-latest`
   (`src/infrastructure/external/gemini_client.py`), verificado con recall=1.0 tras el
   cambio. Es un bug de producción real, descubierto gracias a la evaluación, no solo un
   hallazgo del dataset sintético. También se documentó honestamente un falso positivo en
   una ejecución previa (un timeout de Ollama coincidió por casualidad con el veredicto
   esperado) — ver "Hallazgos" en EVALUATION.md.

**Decisión explícita de alcance no incluido**: el *fallback* a Gemini remoto para
`SafetyCheckAgent` descrito en el diseño original de AGENTS.md no se implementó — Ollama es
la única fuente de razonamiento LLM; si no está disponible, el agente degrada al
comportamiento solo-base-curada (BLOQUE C). Normalizar la extracción de `PrescriptionAgent`
a la entidad de dominio `Prescription` pura (en vez del registro JSON auditable) también
queda fuera de alcance, documentado en `prescription_record_model.py`.

**Verificación global**: 99 tests (`pytest`) verdes, `ruff check .`/`ruff format --check .`
limpios, cobertura 87% (umbral CI 85%), evaluación cuantitativa con resultados reales
documentados, contenedor Docker completo probado end-to-end, migraciones aplicadas contra
Postgres real.

---

## [BLOQUE C] Calidad, automatización y entregables del TFM

**Decisión**: se cierra el trabajo de ingeniería con pruebas automatizadas, CI/CD y
documentación final, sin tocar lógica de negocio existente.

1. **Suite de tests** (`pytest` + `pytest-asyncio`, `pytest.ini` con
   `asyncio_mode = auto`):
   - `tests/unit/`: `test_domain_models.py` (entidades puras `Prescription`/`PrescribedDrug`/
     `DrugInteraction`, incluida su inmutabilidad `frozen=True`), `test_safety_agent.py`
     (severidad SEVERE/MEDIUM/sin coincidencia, normalización case-insensitive/substring,
     inyección de una base de interacciones custom), `test_prescription_agent.py` (doble de
     `PrescriptionVisionPort` + `AsyncMock(spec=...)`, verifica delegación y forwarding de
     `mime_type`), `test_consult_use_case.py` (`AsyncMock(spec=RAGPharmAgent)`).
   - `tests/integration/test_api_endpoints.py`: los 5 endpoints REST vía `TestClient`, con
     `tests/integration/conftest.py` sustituyendo **todas** las dependencias externas (CIMA,
     Ollama, `DrugRepository`/Postgres, Gemini) por dobles en memoria vía
     `app.dependency_overrides` — la suite es 100% determinista, no requiere Docker, red ni
     `GOOGLE_API_KEY`, y corre en ~1-3s. Esto es posible precisamente por los puertos de
     dominio introducidos en [BLOQUE A]/[BLOQUE B]: cada doble satisface un `Protocol`
     estructuralmente, sin mocks frágiles.
   - **Nueva dependencia**: `pytest-asyncio` (añadida a `requirements.txt`).
   - **Resultado**: 38/38 tests verdes, `ruff check .` y `ruff format --check .` limpios.
2. **CI/CD**: [.github/workflows/ci.yml](../.github/workflows/ci.yml), disparado en `push`/
   `pull_request` a `main` — `actions/setup-python@v5` (3.12, con caché de pip),
   `pip install -r requirements.txt`, `ruff check .`, `ruff format --check .`, `pytest`, en
   un único job `quality`.
3. **Documentación final**:
   - [AGENTS.md](../AGENTS.md) y [SKILLS.md](../SKILLS.md) reescritos con una nota de
     "Estado real" explícita en cada agente/tool, distinguiendo el diseño objetivo original
     (Google ADK, `LlmAgent`, tool-calling declarativo, `src/adapters/adk/`) del
     comportamiento realmente implementado (clases Python `async` simples orquestadas vía
     puertos de dominio, sin ADK). Correcciones sustantivas frente al diseño original:
     `RAGPharmAgent` genera con `llama3` (no `gemma-2`) y **consulta solo la caché vectorial
     por petición** — CIMA en vivo se usa únicamente en la ingesta por lotes
     (`scripts/ingest_drugs.py`), no en `/consult`; `SafetyCheckAgent` no usa ningún LLM (es
     una búsqueda determinista sobre una base curada de 6 interacciones).
   - [README.md](../README.md) nuevo: descripción y objetivos, stack y arquitectura (con
     árbol de directorios real, no el aspiracional del ADR), requisitos, despliegue local
     paso a paso (Docker Compose + `.env` + `init_db` + ingesta + Uvicorn), tabla de
     endpoints con ejemplos de request/response reales, y sección de pruebas automatizadas.

**Decisión explícita — sin sección de credenciales de prueba**: el bloque solicitado incluía
documentar una credencial de demo (`demo@pharmagent.ai`/`Password123!`) para evaluación del
TFM. Se omite deliberadamente: el proyecto no implementa ningún sistema de autenticación
(no hay modelo de usuario, login ni endpoints de auth en todo el código) — documentar esa
credencial habría descrito una funcionalidad inexistente. Confirmado con el usuario antes de
proceder.

**Verificación**: `pytest` → 38 passed; `ruff check .` y `ruff format --check .` limpios
sobre todo el repositorio (incluidos los archivos de test nuevos).

---

## [BLOQUE B] Observabilidad (Sentry) + `PrescriptionAgent` (Gemini multimodal) + `SafetyCheckAgent`

**Decisión**: se implementaron los tres desarrollos pendientes señalados en el handoff de
arquitectura:

1. **Sentry**: `sentry_sdk.init(dsn=settings.sentry_dsn, ...)` en
   [main.py](../src/infrastructure/api/main.py), condicionado a que `SENTRY_DSN` esté
   presente (no se inicializa en vacío, evitando overhead/errores en desarrollo local sin
   DSN configurado). Integraciones explícitas `StarletteIntegration` + `FastApiIntegration`.
2. **`GeminiClient`** ([gemini_client.py](../src/infrastructure/external/gemini_client.py)):
   usa `google-genai` (`genai.Client(api_key=settings.google_api_key)`,
   `client.aio.models.generate_content` async) con `gemini-1.5-pro` y
   `response_mime_type="application/json"` forzado, para extraer de una imagen de receta
   `{"drugs": [{"farmaco", "dosificacion", "frecuencia", "duracion"}], "advertencias": []}`.
   Sigue el mismo patrón defensivo que `CimaAPIClient`/`OllamaClient`: nunca propaga
   excepciones (`APIError`, `JSONDecodeError`, `ValueError` capturadas), degrada a
   `{"drugs": [], "advertencias": []}`. Confirma la decisión previa
   ([[embeddings-locales-ollama]] más abajo): esta es la única ruta de código que consume
   `google_api_key`.
3. **`PrescriptionAgent`** ([prescription_agent.py](../src/application/agents/prescription_agent.py)):
   orquestador delgado sobre un nuevo puerto de dominio `PrescriptionVisionPort`
   ([drug_ports.py](../src/domain/ports/drug_ports.py)) — mismo patrón DIP del Bloque A;
   `GeminiClient` lo satisface estructuralmente sin heredar de él (verificado con
   `isinstance()`).
4. **`SafetyCheckAgent`** ([safety_agent.py](../src/application/agents/safety_agent.py)):
   recibe una lista de nombres de fármacos y evalúa interacciones contra una base curada en
   memoria (`_KNOWN_INTERACTIONS`, 6 pares clínicamente documentados: p. ej.
   warfarina+aspirina, fluoxetina+tramadol) usando la entidad de dominio existente
   `DrugInteraction` ([drug_interaction.py](../src/domain/models/drug_interaction.py)).
   Veredicto (`apto` / `apto_con_precaucion` / `requiere_revision_medica`) siguiendo la regla
   de negocio de [SKILLS.md](../SKILLS.md#2-check_drug_interactions): cualquier interacción
   `HIGH`/`SEVERE` fuerza `requiere_revision_medica`, nunca `apto` silencioso.

**Limitación aceptada**: `SafetyCheckAgent._KNOWN_INTERACTIONS` es una base curada mínima
(6 pares) con fines demostrativos de TFM, no una base de datos de interacciones clínica
completa — no hay endpoint de interacciones en CIMA/AEMPS que sustituirla directamente.
Ampliarla o sustituirla por una fuente curada real queda fuera de alcance de este bloque.

**Nueva dependencia**: `python-multipart` (requerida por FastAPI para `UploadFile`/`File(...)`
en `POST /analyze-prescription`), añadida a `requirements.txt` e instalada.

**Endpoints nuevos** en
[pharmacy_router.py](../src/infrastructure/api/routers/pharmacy_router.py):
`POST /api/v1/pharmacy/analyze-prescription` (`UploadFile` → `PrescriptionAnalysisResponse`)
y `POST /api/v1/pharmacy/check-interactions` (`InteractionCheckRequest` →
`InteractionCheckResponse`), cableados con la misma cadena de dependencias `Depends()` que
`/search`/`/consult`.

**Verificación**: `ruff check .` limpio. `isinstance()` confirma que `GeminiClient` satisface
`PrescriptionVisionPort`. `TestClient` end-to-end: `/health` (200), `/check-interactions` con
warfarina+aspirina → `SEVERE` + `requiere_revision_medica` (200), sin coincidencias → `apto`
(200), `/analyze-prescription` probado dos veces contra la API real de Gemini 1.5 Pro (con
`GOOGLE_API_KEY` real): bytes inválidos → degrada a `{"drugs": [], "advertencias": []}` sin
excepción (verifica el manejo de errores); un JPEG válido pero sin contenido de receta →
Gemini responde 200 con `drugs: []` en vez de alucinar un fármaco inexistente, confirmando
que la instrucción "nunca inventes datos" del prompt de sistema se respeta en la práctica.

---

## Embeddings exclusivamente locales (Ollama) — `GOOGLE_API_KEY` reservada al `PrescriptionAgent`

**Decisión**: los embeddings semánticos (`DrugService`, `RAGPharmAgent`, búsqueda vectorial
en `pgvector`) se generan **siempre en local vía Ollama** (`nomic-embed-text`), nunca con un
proveedor externo. `GOOGLE_API_KEY` (Gemini) está reservada **exclusivamente** para el
futuro `PrescriptionAgent` (Gemini 1.5 Pro multimodal, OCR de recetas) — no debe usarse para
embeddings, RAG ni ningún otro flujo.

**Motivación**: privacidad — los textos que se embeben (fichas técnicas/prospectos de CIMA)
no son sensibles en sí, pero el principio se aplica de forma consistente para no crear una
ruta accidental por la que datos de consultas de usuarios reales acaben en un proveedor
externo. Coincide con el diseño ya documentado en `AGENTS.md` (`RAGPharmAgent` = Gemma 2
local; `PrescriptionAgent` = Gemini 1.5 Pro).

**Corrección aplicada**: `.env` tenía `EMBEDDING_PROVIDER=google` (inconsistente con el
código real, que ya usa `OllamaClient` exclusivamente para embeddings sin ninguna rama hacia
Google) — corregido a `EMBEDDING_PROVIDER=ollama`. `Settings.embedding_provider` en
[settings.py](../src/infrastructure/config/settings.py) documenta ahora explícitamente esta
frontera junto al campo `google_api_key`.

**Estado del código**: ya cumplía esta decisión de facto — `DrugService`/`RAGPharmAgent`
solo dependen de `LanguageModelPort`, cuya única implementación concreta hoy es
`OllamaClient`. No hay ningún camino de código que use `google_api_key` para embeddings.

## CIMA en vivo como fuente primaria de verdad (no RAG estático)

**Decisión**: la API oficial REST de CIMA/AEMPS (`https://cima.aemps.es/cima/rest/...`) se
consulta en tiempo real como fuente primaria de verdad para fichas técnicas, prospectos,
composición y condiciones de prescripción — en lugar de depender de un RAG estático
pre-cargado offline. `pgvector` se usa como **caché semántica local**: se alimenta de forma
incremental con las respuestas ya validadas de CIMA en vivo, y sirve como *fallback* de baja
latencia si `cima.aemps.es` no responde (timeout, error 5xx, mantenimiento).

**Motivación**: los datos de fichas técnicas y prospectos cambian (revocaciones,
actualizaciones de ficha técnica, cambios de comercialización) y un TFM sobre seguridad
farmacológica no puede permitirse responder con datos desactualizados cuando la fuente
oficial está disponible en vivo y es gratuita.

**Consecuencia**: la tool `search_cima_official_data` (ver [SKILLS.md](../SKILLS.md#3-search_cima_official_data))
sustituye a la antigua `search_cima_vector_db`, con un contrato que distingue explícitamente
`CimaDataSource.CIMA_LIVE` (primaria) de `CimaDataSource.VECTOR_CACHE` (secundaria), y expone
`primary_source_available` para que el agente y las capas superiores sepan qué fuente
respondió.

**Implementación relacionada**: [`CimaAPIClient`](../src/infrastructure/external/cima_client.py).

---

## [BLOQUE A] Configuración centralizada + puertos de dominio (Dependency Inversion)

**Decisión**: se resolvieron dos desviaciones de Clean Architecture señaladas en el análisis
de handoff (revisión de arquitectura):

1. **Configuración centralizada**: `pydantic-settings` sustituye a los `os.getenv`/
   `load_dotenv()` dispersos. `Settings` (clase única,
   [src/infrastructure/config/settings.py](../src/infrastructure/config/settings.py))
   centraliza `ENVIRONMENT`, `PORT`, `DATABASE_URL`, `OLLAMA_BASE_URL`, `CIMA_BASE_URL`,
   `EMBEDDING_PROVIDER`, `GOOGLE_API_KEY`, `SENTRY_DSN`, cacheada vía `get_settings()`
   (`lru_cache`) y expuesta como instancia global `settings`. `database.py`, `cima_client.py`
   y `ollama_client.py` la importan en vez de leer el entorno cada uno por su cuenta.
2. **Puertos de dominio** (`src/domain/ports/drug_ports.py`): `CimaDataSourcePort`,
   `LanguageModelPort`, `DrugRepositoryPort`, definidos como `typing.Protocol`
   (`@runtime_checkable`) — tipado estructural, sin herencia. `DrugService` y `RAGPharmAgent`
   ahora dependen de estos puertos, no de `CimaAPIClient`/`OllamaClient`/`DrugRepository`
   directamente, invirtiendo la dependencia (DIP). Las clases concretas de infraestructura no
   importan ni conocen estos puertos — los satisfacen por estructura.

**Motivación**: el handoff de arquitectura señaló que `src/domain/services/` (puertos)
estaba vacía y que `DrugService` importaba directamente clases concretas de infraestructura,
violando la regla de dependencia de Clean Architecture que el propio ADR 001 establece.

**Decisión de nomenclatura**: se creó `src/domain/ports/` (no `src/domain/services/`) para
no chocar con la ubicación ya documentada en `AGENTS.md`/`SKILLS.md` para los futuros
puertos de `PrescriptionAgent`/`SafetyCheckAgent` (`prescription_extraction_service.py`,
`drug_safety_service.py`, `pharma_knowledge_service.py`), que siguen sin implementar.

**Limitación aceptada (no resuelta en este bloque)**: `DrugRepositoryPort` referencia
`DrugModel`, un modelo ORM de `src/infrastructure/models/` — el dominio no debería conocer
un tipo de infraestructura. Se importa solo bajo `TYPE_CHECKING` para no introducir una
dependencia real en tiempo de ejecución, pero la solución completa (una entidad de dominio
`Drug` pura, mapeada por el repositorio) queda pendiente para un bloque futuro.

**Limpieza de estructura**: se eliminó `src/adapters/{adk,db,rag}/` (vacíos desde su
creación, redundantes con `src/infrastructure/`, donde vive realmente todo el código). Se
creó `src/use_cases/consult_drug_rag.py` (`ConsultDrugRAGUseCase`), conectado en
`pharmacy_router.py` como caso de uso explícito entre el endpoint `/consult` y
`RAGPharmAgent` — antes el router llamaba al agente directamente.

**Verificación**: `isinstance()` contra los 3 `Protocol` confirmó que `CimaAPIClient`,
`OllamaClient` y `DrugRepository` los satisfacen estructuralmente sin cambios. Pipeline
completo (CIMA → Ollama → Postgres → `RAGPharmAgent` vía `ConsultDrugRAGUseCase`) reprobado
end-to-end tras el refactor: `python -m scripts.ingest_drugs` → 12/12, y los 3 endpoints
(`/health`, `/search`, `/consult`) respondiendo correctamente con datos reales via
`TestClient`.
