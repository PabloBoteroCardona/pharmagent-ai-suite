# CONTEXT.md — PharmAgent AI Suite

## Resumen del proyecto

PharmAgent AI Suite es un Trabajo de Fin de Máster (TFM) que implementa un sistema
multiagente, construido en Clean Architecture sobre Python/FastAPI, para el procesamiento
de recetas médicas, la verificación de interacciones farmacológicas y la consulta de fichas
técnicas oficiales (AEMPS/CIMA). Combina tres agentes sobre Google ADK — `PrescriptionAgent`
(Gemini 1.5 Pro multimodal), `SafetyCheckAgent` (Llama 3.1 local) y `RAGPharmAgent`
(Gemma 2 local) — y persiste datos en PostgreSQL + `pgvector`. Ver [AGENTS.md](../AGENTS.md)
y [SKILLS.md](../SKILLS.md) para el detalle de agentes y herramientas.

## Estado actual

**[BLOQUE D] "Profesionalización" — EN CURSO, pasos 1-6 de 10 completados y verificados.**
Tras cerrar [BLOQUE A]/[B]/[C], se pidió evaluar el proyecto con ojo crítico (puntos débiles
señalados: `SafetyCheckAgent` sin LLM, `RAGPharmAgent` no consulta CIMA en vivo por petición,
sin auth, sin CORS, sin persistencia real de `Prescription`, sin migraciones Alembic, sin
evaluación cuantitativa, cobertura de tests superficial). El usuario pidió corregir "todo lo
necesario para que quede un proyecto profesional"; se acordó (decisión propia, instrucción
del usuario: proceder con criterio propio) implementar en este orden:

1. ✅ CORS + autenticación por API key.
2. ✅ Dockerfile de la API + servicio en `docker-compose.yml`.
3. ✅ Orquestación end-to-end receta→extracción→interacciones (nuevo caso de uso + endpoint).
4. ✅ `SafetyCheckAgent`: capa de razonamiento con Ollama para combinaciones fuera de la tabla curada.
5. ✅ Persistencia real de recetas procesadas (modelo ORM + repositorio).
6. ✅ Migraciones Alembic (sustituye `create_all`/`init_db.py`, eliminado).
7. ⬜ Tests directos de `CimaAPIClient`/`OllamaClient`/`GeminiClient` (manejo de errores) — **siguiente paso**.
8. ⬜ `pytest-cov` + umbral de cobertura en CI.
9. ⬜ Dataset de evaluación sintético + script de métricas + `EVALUATION.md`.
10. ⬜ Actualizar README/AGENTS/SKILLS y memoria con el estado final.

**Resumen de los pasos 1-6 (todos verificados con `ruff check .`, `ruff format --check .` y
`pytest` en verde; varios además contra servicios reales, no solo dobles — ver detalle):**

- **1-2 (CORS + API key + Docker)**: `settings.api_key`/`cors_allowed_origins` nuevos;
  [security.py](../src/infrastructure/api/security.py) (`verify_api_key`, dependencia a
  nivel de router); `CORSMiddleware` en `main.py`.
  [Dockerfile](../Dockerfile) (`python:3.12-slim`, usuario no-root) + servicio `api` en
  [docker-compose.yml](../docker-compose.yml) — build y arranque del contenedor verificados
  con Docker Desktop real (`/health` → 200 dentro del contenedor).
- **3 (orquestación)**: [`ProcessPrescriptionUseCase`](../src/use_cases/process_prescription.py)
  encadena `PrescriptionAgent` → `SafetyCheckAgent` (solo si se extraen 2+ fármacos);
  `POST /api/v1/pharmacy/process-prescription`.
- **4 (SafetyCheckAgent + LLM)**: diseño híbrido — la base curada sigue siendo la fuente
  **autoritativa** (si aplica, nunca se consulta al LLM); para combinaciones no cubiertas, si
  hay un `LanguageModelPort` inyectado (Ollama), se le consulta con un prompt restrictivo;
  cada interacción lleva `source: "curated"|"llm"`. Ante JSON inválido o `uncertain: true`,
  el veredicto por defecto es `requiere_revision_medica` (nunca aprobación silenciosa).
  `check_interactions` es ahora `async`. **Verificado contra Ollama/llama3 real**:
  metformina+furosemida (fuera de la tabla) generó una interacción plausible con
  `source: "llm"`; warfarina+aspirina (en la tabla) no consultó al modelo.
- **5 (persistencia)**: `PrescriptionRecordModel`
  ([prescription_record_model.py](../src/infrastructure/models/prescription_record_model.py))
  — registro auditable (JSON crudo de `drugs`/`advertencias`/`safety_check`), deliberadamente
  NO mapeado a la entidad de dominio estricta `Prescription`/`PrescribedDrug` porque
  `GeminiClient` devuelve texto libre no normalizado (`"cada 8 horas"`) y forzarlo a
  `frequency_hours: int` introduciría conversión no verificada en datos de salud — decisión
  documentada en el propio modelo. `PrescriptionRecordRepository` +
  `PrescriptionRecordRepositoryPort`, inyectado opcionalmente en
  `ProcessPrescriptionUseCase`. **Verificado con escritura y lectura reales en Postgres.**
- **6 (Alembic)**: `alembic init -t async migrations`; `migrations/env.py` reconfigurado
  para usar `settings.database_url` y `Base.metadata` (autogenerate real, no manual).
  `src/infrastructure/init_db.py` **eliminado** (reemplazado por migraciones). Primera
  migración `272aeb551e68` (tablas `drugs` + `prescription_records`), con un fix manual al
  autogenerate (faltaba `import pgvector.sqlalchemy` y `CREATE EXTENSION IF NOT EXISTS
  vector`). **Verificado con upgrade/downgrade/upgrade real contra Postgres**, y con el
  contenedor Docker completo (`docker-compose up api` ejecuta `alembic upgrade head` antes
  de arrancar Uvicorn). CI: nuevo job `migrations` en
  [.github/workflows/ci.yml](../.github/workflows/ci.yml) que aplica y revierte la migración
  contra un Postgres de servicio en GitHub Actions.

**Nota**: tras dropear/recrear las tablas para generar la migración limpia, se re-ejecutó
`python -m scripts.ingest_drugs` (12/12 fármacos re-indexados) — la caché de `drugs` está
vacía hasta ese re-seed, ya hecho.

## Último hito verificado

**[BLOQUE C] — Suite de tests, CI/CD y documentación final.** Ver
[DECISIONS.md](DECISIONS.md) para el detalle completo. Resumen:

- **Tests** (`pytest` + `pytest-asyncio`, `pytest.ini`): `tests/unit/test_domain_models.py`,
  `test_safety_agent.py`, `test_prescription_agent.py`, `test_consult_use_case.py` +
  `tests/integration/test_api_endpoints.py` (los 5 endpoints REST). Todas las dependencias
  externas (CIMA, Ollama, `DrugRepository`, Gemini) se sustituyen por dobles en memoria vía
  `app.dependency_overrides` en [tests/integration/conftest.py](../tests/integration/conftest.py)
  — la suite es determinista, sin Docker/red/credenciales, y corre en ~1-3s. **38/38 tests
  verdes.**
- **CI/CD**: [.github/workflows/ci.yml](../.github/workflows/ci.yml) — `ruff check .`,
  `ruff format --check .`, `pytest` en cada `push`/`pull_request` a `main`.
- **`AGENTS.md`/`SKILLS.md` corregidos**: cada agente/tool tiene ahora una nota de "Estado
  real" que distingue el diseño ADK original del comportamiento implementado. Correcciones
  sustantivas: `RAGPharmAgent` usa `llama3` (no `gemma-2`) y solo consulta la caché vectorial
  por petición (CIMA en vivo es exclusivo de la ingesta batch); `SafetyCheckAgent` no usa
  ningún LLM.
- **`README.md` nuevo**: descripción, stack, arquitectura (árbol real de `src/`), despliegue
  local paso a paso, tabla de endpoints con ejemplos reales, sección de tests. Sin sección de
  credenciales de demo — el proyecto no tiene sistema de autenticación (decisión explícita,
  confirmada con el usuario antes de proceder).
- **Verificado sin regresiones**: `pytest` (38 passed), `ruff check .` y
  `ruff format --check .` limpios sobre todo el repositorio.

---

**[BLOQUE B] — Sentry, `GeminiClient`/`PrescriptionAgent` (Gemini 1.5 Pro multimodal) y
`SafetyCheckAgent`.** Ver [DECISIONS.md](DECISIONS.md) para el detalle completo. Resumen:

- **Sentry**: `sentry_sdk.init(dsn=settings.sentry_dsn, ...)` en
  [main.py](../src/infrastructure/api/main.py), solo si `SENTRY_DSN` está presente
  (`StarletteIntegration` + `FastApiIntegration`).
- **`GeminiClient`** ([gemini_client.py](../src/infrastructure/external/gemini_client.py)):
  `google-genai`, `gemini-1.5-pro`, `analyze_prescription_image(image_bytes, mime_type)` →
  `{"drugs": [...], "advertencias": [...]}` con `response_mime_type="application/json"`.
  Mismo patrón defensivo que `CimaAPIClient`/`OllamaClient` (nunca propaga excepciones).
  Único consumidor de `GOOGLE_API_KEY` — confirma la frontera ya documentada.
- **Nuevo puerto de dominio** `PrescriptionVisionPort`
  ([drug_ports.py](../src/domain/ports/drug_ports.py)) — `GeminiClient` lo satisface
  estructuralmente (verificado con `isinstance()`).
- **`PrescriptionAgent`** ([prescription_agent.py](../src/application/agents/prescription_agent.py)):
  orquestador delgado sobre `PrescriptionVisionPort`.
- **`SafetyCheckAgent`** ([safety_agent.py](../src/application/agents/safety_agent.py)):
  base curada de 6 interacciones conocidas (`DrugInteraction` de dominio), veredicto
  `apto`/`apto_con_precaucion`/`requiere_revision_medica` (`HIGH`/`SEVERE` fuerza revisión).
- **Endpoints nuevos** en `pharmacy_router.py`: `POST /analyze-prescription` (`UploadFile`) y
  `POST /check-interactions`.
- **Nueva dependencia**: `python-multipart` (requerida por `UploadFile`/`File(...)`).
- **Verificado sin regresiones**: `ruff check .` limpio; `TestClient` end-to-end —
  `/check-interactions` con warfarina+aspirina → `SEVERE`/`requiere_revision_medica`, sin
  coincidencias → `apto`; `/analyze-prescription` probado dos veces contra la API real de
  Gemini 1.5 Pro (bytes inválidos → degradación limpia; JPEG válido sin contenido → `drugs: []`
  sin alucinación).
- Pendiente explícito: base de interacciones de `SafetyCheckAgent` es mínima/demostrativa, no
  una fuente clínica completa.

---

**[BLOQUE A] — Configuración centralizada + puertos de dominio.** Ver
[DECISIONS.md](DECISIONS.md) para el detalle completo de la decisión. Resumen:

- `pydantic-settings` instalado; `Settings`
  ([src/infrastructure/config/settings.py](../src/infrastructure/config/settings.py))
  centraliza todas las variables de entorno. `database.py`, `cima_client.py` y
  `ollama_client.py` refactorizados para usar la instancia global `settings` en vez de
  `os.getenv`/`load_dotenv()` dispersos.
- Puertos de dominio nuevos
  ([src/domain/ports/drug_ports.py](../src/domain/ports/drug_ports.py)):
  `CimaDataSourcePort`, `LanguageModelPort`, `DrugRepositoryPort` (`typing.Protocol`,
  `@runtime_checkable`). `DrugService` y `RAGPharmAgent` dependen de estos puertos, no de
  las clases concretas de infraestructura — Dependency Inversion Principle aplicado.
  Verificado con `isinstance()`: `CimaAPIClient`, `OllamaClient` y `DrugRepository`
  satisfacen sus puertos sin ningún cambio (tipado estructural).
- `src/adapters/{adk,db,rag}/` eliminado (vacío, redundante con `src/infrastructure/`).
- Caso de uso explícito creado y conectado:
  [src/use_cases/consult_drug_rag.py](../src/use_cases/consult_drug_rag.py)
  (`ConsultDrugRAGUseCase`) — el endpoint `POST /consult` ahora pasa por este caso de uso
  en vez de llamar a `RAGPharmAgent` directamente.
- **Verificado sin regresiones**: `ruff check .` limpio; `python -m scripts.ingest_drugs` →
  12/12 fármacos indexados; los 3 endpoints (`/health`, `/search`, `/consult`) probados con
  `TestClient` contra CIMA + Postgres + Ollama reales, con respuestas correctas.
- `.env.example` actualizado: puerto de Postgres corregido a `5433`, añadidas
  `CIMA_BASE_URL` y `EMBEDDING_PROVIDER` (esta última ya presente en `.env` real, apuntando
  a `google` — sugiere que hay un cambio de proveedor de embeddings en marcha fuera de esta
  conversación; `Settings.embedding_provider` la centraliza pero nada la consume todavía).

**Pendiente explícito señalado en el propio análisis (no resuelto en este bloque)**:
`DrugRepositoryPort` sigue referenciando `DrugModel` (tipo ORM de infraestructura) — ver
limitación aceptada en [DECISIONS.md](DECISIONS.md).

---

**Pipeline 100% funcional de extremo a extremo con datos y modelos reales.** Se
descargaron los modelos que faltaban en `pharmagent_ollama`:
`docker exec pharmagent_ollama ollama pull nomic-embed-text` (274 MB, embeddings, dim=768,
coincide con `DrugModel.embedding: Vector(768)`) y `ollama pull llama3` (4.7 GB, generación).
Ver [BUGS.md](BUGS.md) para el detalle y una nota importante sobre arranque en frío.

Con ambos modelos disponibles:
- `python -m scripts.ingest_drugs` reejecutado → **12/12 fármacos indexados con embedding
  real** (antes quedaban `NULL`), confirmado con `psql` directo.
- `RAGPharmAgent.answer_consultation("¿qué dosis de ibuprofeno es adecuada?")` probado
  contra CIMA + Postgres + Ollama reales (sin stubs): `search_drugs_semantic` recuperó
  correctamente los 3 ibuprofenos más relevantes vía `l2_distance` de `pgvector`, y `llama3`
  generó una respuesta grounded citando las dosis reales (200 mg y 600 mg) de los fármacos
  recuperados. **38.7s** de latencia (CPU, sin GPU) — dentro del timeout de 60s de
  `OllamaClient`, pero ajustado; ver nota de arranque en frío en [BUGS.md](BUGS.md).

Con esto, el bug de `asyncpg` (resuelto antes) y la falta de modelos de Ollama (resuelta
ahora) quedan ambos cerrados — ya no hay bloqueadores de entorno conocidos.

**Bug de `asyncpg` en Windows/Python 3.14 RESUELTO.** Ver [BUGS.md](BUGS.md) para el
detalle completo. Fix: `WindowsSelectorEventLoopPolicy` + Postgres publicado en el puerto
`5433` (en vez de `5432`) + `connect_args={"ssl": False}` en el engine
([database.py](../src/infrastructure/database.py) /
[docker-compose.yml](../docker-compose.yml)).

**PASO 26 — Script de ingesta masiva creado.**
[scripts/ingest_drugs.py](../scripts/ingest_drugs.py): `ingest_top_drugs()` recorre
`SEARCH_TERMS` (`ibuprofeno`, `paracetamol`, `amoxicilina`, `omeprazol`), busca cada término
en CIMA (`CimaAPIClient.search_medicamentos`) y ejecuta
`DrugService.fetch_and_index_drug(nregistro)` sobre los 3 primeros resultados de cada uno,
imprimiendo progreso por fármaco (`[OK]`/`[FALLO]`/`[ERROR]`) y un resumen final
`indexados/procesados`. Cada fármaco se procesa en su propio `try/except` para que un fallo
puntual no aborte el resto del lote. Ejecutado con `python -m scripts.ingest_drugs` (no como
script suelto: `scripts/` no es un paquete instalado, y `src` solo es importable si el
proceso arranca desde la raíz del proyecto).

Ejecutado en tiempo real: búsqueda en CIMA correcta para los 4 términos (138, 198, 145 y 168
resultados respectivamente); los 12 intentos de indexación (`0/12`) fallan en el paso de
escritura en Postgres por el bug de `asyncpg`/Windows/Python 3.14 ya documentado en
[BUGS.md](BUGS.md) — el script demuestra ser resiliente a ese fallo (recorre los 12 fármacos
y reporta el resumen final en vez de abortar en el primer error).

**PASO 24 — Esquemas y endpoints REST con FastAPI creados.**
- [src/infrastructure/api/schemas/drug_schemas.py](../src/infrastructure/api/schemas/drug_schemas.py):
  `DrugSearchQuery` (`query`, `limit=5`), `ConsultationRequest` (`query`),
  `ConsultationResponse` (`query`, `response`, `sources`).
- [src/infrastructure/api/routers/pharmacy_router.py](../src/infrastructure/api/routers/pharmacy_router.py):
  `POST /api/v1/pharmacy/search` (llama a `DrugService.search_drugs_semantic`) y
  `POST /api/v1/pharmacy/consult` (llama a `RAGPharmAgent.answer_consultation`, devuelve
  `ConsultationResponse`). Cadena de dependencias FastAPI (`Depends`) construye
  `CimaAPIClient` → `OllamaClient` → `DrugRepository` (vía `get_db_session`) →
  `DrugService` → `RAGPharmAgent` por request.
- [src/infrastructure/api/main.py](../src/infrastructure/api/main.py): `app = FastAPI(...)`,
  incluye `pharmacy_router`, y `GET /health` → `{"status": "ok"}`.
- Validado end-to-end con `fastapi.testclient.TestClient`: `/health` (200), `/search` (200,
  `[]` porque Ollama no tiene modelo descargado en este entorno) y `/consult` (200,
  `response` vacía por el mismo motivo) — confirma que toda la cadena de dependencias, rutas
  y esquemas Pydantic queda correctamente cableada.

**PASO 23 — `RAGPharmAgent` creado.**
[src/application/agents/pharmacy_agent.py](../src/application/agents/pharmacy_agent.py):
`answer_consultation(query)` busca fármacos relevantes con
`DrugService.search_drugs_semantic(query, limit=3)`, compone un contexto (nombre,
principios activos, secciones del prospecto) con un system prompt grounded que exige
responder solo con esa información técnica o remitir a un profesional sanitario si falta,
genera la respuesta con `OllamaClient.generate_completion` y devuelve
`{"query", "response", "sources"}` (`sources` = nombres de los fármacos usados como
contexto). Validado con un `DrugService` *stub* + `OllamaClient` real: estructura del dict,
orden de `sources` y degradación correcta a `sources: []` sin contexto, verificados.

**PASO 22 — `DrugService` creado.**
[src/application/services/drug_service.py](../src/application/services/drug_service.py)
orquesta CIMA, Ollama y PostgreSQL: `fetch_and_index_drug(nregistro)` (consulta CIMA,
compone texto de nombre+principios activos+prospecto, genera embedding vía
`OllamaClient.generate_embedding` y persiste con `DrugRepository.save_drug`) y
`search_drugs_semantic(query, limit)` (embedding de la consulta +
`DrugRepository.search_similar_by_vector`, con corte defensivo a `[]` si el embedding
falla). Validado end-to-end contra CIMA y Ollama reales (con un repositorio *stub*, ya que
la escritura real en Postgres sigue bloqueada por el bug de `asyncpg`/Windows — ver
[BUGS.md](BUGS.md)): el medicamento nregistro=80298 se obtuvo y compuso correctamente.

**Fase 3 (Infraestructura Local) completa.** Hitos verificados:

- Cliente HTTP asíncrono `CimaAPIClient`
  ([src/infrastructure/external/cima_client.py](../src/infrastructure/external/cima_client.py))
  probado en tiempo real contra la API oficial de la AEMPS (`https://cima.aemps.es/cima/rest`):
  `search_medicamentos(nombre)`, `get_medicamento_by_nregistro(nregistro)` /
  `get_medicamento_by_cn(cn)`, `get_prospecto_html(nregistro)`. Manejo robusto de errores:
  captura tanto `httpx.HTTPError` como `json.JSONDecodeError` (CIMA devuelve `200 OK` con
  cuerpo vacío para un `nregistro`/`cn` inexistente, en vez de un 404 — degradado a
  `[]`/`None` en ambos casos). Validado con el script manual
  [test_cima.py](../test_cima.py) (búsqueda real de "ibuprofeno", 138 resultados, detalle y
  CN de los 3 primeros).
- `DrugModel` (SQLAlchemy 2.0 + `pgvector`,
  [src/infrastructure/models/drug_model.py](../src/infrastructure/models/drug_model.py)) y
  el script [init_db.py](../src/infrastructure/init_db.py) para habilitar la extensión
  `pgvector` en PostgreSQL y crear el esquema inicial.
- `DrugRepository` en
  [src/infrastructure/repositories/](../src/infrastructure/repositories/) (`save_drug`,
  `get_by_nregistro`, `search_similar_by_vector` con `l2_distance` de `pgvector`).
- `OllamaClient` en
  [src/infrastructure/external/ollama_client.py](../src/infrastructure/external/ollama_client.py)
  (`generate_embedding`, `generate_completion`), con manejo de errores defensivo y timeout de
  60s.

## Siguiente paso pendiente

**[BLOQUE D] "Profesionalización", paso 7 de 10: tests directos de `CimaAPIClient`/
`OllamaClient`/`GeminiClient`.** Pasos 1-6 completados y verificados (ver "Estado actual"
arriba). Acción exacta al retomar:

1. Crear `tests/unit/test_cima_client.py`, `test_ollama_client.py`, `test_gemini_client.py`
   — cubrir el manejo de errores defensivo de cada cliente (que hoy solo se ejercita
   indirectamente a través de los dobles en los tests de integración, nunca directamente):
   `httpx.HTTPError`/`json.JSONDecodeError` capturados en `CimaAPIClient`/`OllamaClient`
   (degradan a `[]`/`None`/`""`), y `APIError`/`JSONDecodeError`/`ValueError` en
   `GeminiClient` (degrada a `{"drugs": [], "advertencias": []}`). Usar `httpx.MockTransport`
   o mockear el cliente HTTP subyacente para simular timeouts, respuestas 5xx y cuerpos
   vacíos/malformados sin depender de red real.
2. Ejecutar `ruff check .`, `ruff format --check .`, `pytest`.
3. Continuar con el resto de la lista de [BLOQUE D] en orden: `pytest-cov` + umbral de
   cobertura en CI, dataset de evaluación sintético + script de métricas + `EVALUATION.md`,
   y cierre con actualización de README/AGENTS/SKILLS/memoria (documentar todo lo añadido en
   los pasos 1-9: auth, CORS, Docker, orquestación, SafetyCheckAgent híbrido, persistencia,
   Alembic, tests de clientes, cobertura, evaluación).

Candidatos de un bloque futuro posterior a [BLOQUE D] (no priorizados): desacoplar
`DrugRepositoryPort` de `DrugModel` (ORM) con una entidad de dominio `Drug` pura; desplegar
la API en un entorno remoto para la defensa del TFM; normalizar la extracción de
`PrescriptionAgent` a la entidad de dominio `Prescription`/`PrescribedDrug` cuando el modelo
devuelva campos estructurados en vez de texto libre.
