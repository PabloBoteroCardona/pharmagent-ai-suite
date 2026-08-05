# CONTEXT.md — PharmAgent AI Suite

## Resumen del proyecto

PharmAgent AI Suite es un Trabajo de Fin de Máster (TFM) que implementa un sistema
multiagente, construido en Clean Architecture sobre Python/FastAPI, para el procesamiento
de recetas médicas, la verificación de interacciones farmacológicas y la consulta de fichas
técnicas oficiales (AEMPS/CIMA). Tres agentes — `PrescriptionAgent` (Gemini multimodal,
modelo `gemini-flash-latest`), `SafetyCheckAgent` (base curada + razonamiento `llama3` local
para combinaciones no cubiertas) y `RAGPharmAgent` (`llama3` local, RAG sobre caché
`pgvector`) — implementados como clases Python `async` simples (no sobre Google ADK, ver
nota de "Estado real" en [AGENTS.md](../AGENTS.md)), orquestables individualmente o
encadenados vía `ProcessPrescriptionUseCase`. Persiste en PostgreSQL + `pgvector`
(migraciones Alembic). API REST con autenticación opcional por API key y CORS. Ver
[AGENTS.md](../AGENTS.md) y [SKILLS.md](../SKILLS.md) para el detalle de agentes y
herramientas, y [EVALUATION.md](../EVALUATION.md) para su evaluación cuantitativa.

## Estado actual

**[BLOQUE D] "Profesionalización" — ✅ completado (10/10 pasos), + corrección posterior de
CIMA en vivo en `/search`/`/consult` — ✅ completada.** Tras cerrar [BLOQUE A]/[B]/[C], se
evaluó el proyecto con ojo crítico (puntos débiles señalados: `SafetyCheckAgent` sin LLM,
`RAGPharmAgent` no consulta CIMA en vivo por petición, sin auth, sin CORS, sin persistencia
real de recetas, sin migraciones Alembic, sin evaluación cuantitativa, cobertura de tests
superficial). El usuario pidió corregir "todo lo necesario para que quede un proyecto
profesional"; se implementó con criterio propio en 9 mejoras + cierre de documentación
(BLOQUE D). Después, el usuario preguntó explícitamente si consultar interacciones o un
medicamento concreto consultaba CIMA en tiempo real — la respuesta honesta era que no, y
pidió corregirlo ("si no de que sirve"). Se implementó un respaldo real de CIMA en vivo para
`/search` y `/consult` (ver "Último hito verificado" para el detalle, incluyendo un bug real
de métrica de relevancia encontrado y corregido durante la verificación contra Postgres
real). Todos los bloques A/B/C/D están cerrados y verificados, más esta corrección posterior.

## Último hito verificado

**CIMA en vivo como respaldo real de `/search` y `/consult`.** Ver
[DECISIONS.md](DECISIONS.md) para el detalle completo. Resumen ejecutivo:

- **Antes**: `/search` y `/consult` solo miraban `pgvector` (caché poblada exclusivamente
  por `scripts/ingest_drugs.py`, 12 fármacos); cualquier otro fármaco devolvía vacío aunque
  CIMA lo tuviera. `/check-interactions` nunca tocó CIMA (correcto — CIMA no tiene endpoint
  de interacciones, solo fichas técnicas).
- **`DrugService.search_drugs_semantic`** ahora devuelve `DrugSearchResult(drugs, source)`:
  consulta la caché primero y, si no hay resultados relevantes, cae a
  `CimaAPIClient.search_medicamentos` en vivo, indexando automáticamente hasta 3 resultados
  (mismo criterio que la ingesta por lotes) para que consultas futuras sean instantáneas.
- **`RAGPharmAgent`/`ConsultDrugRAGUseCase`** ganaron un parámetro `drug_name` opcional —
  CIMA hace coincidencia literal de nombre, no búsqueda semántica.
- **Endpoints**: `POST /search` devuelve ahora `{"results": [...], "source":
  "cache"|"live"|"none"}`; `POST /consult` acepta `drug_name` y devuelve `source` igual.
- **Bug real encontrado y corregido durante la verificación**: la primera versión filtraba
  la caché por `pgvector.l2_distance`, pero se descubrió (verificando contra Postgres real)
  que L2 es sensible a la longitud del texto — una consulta de una palabra quedaba
  artificialmente lejos incluso del propio fármaco que describe (L2≈16.6 vs. L2≈5.4-9.9 para
  la misma comparación con más texto), rompiendo el cache hit en la práctica. Corregido a
  `pgvector.cosine_distance` (umbral `MAX_RELEVANT_COSINE_DISTANCE = 0.35`,
  [drug_repository.py](../src/infrastructure/repositories/drug_repository.py)), que separó
  limpiamente relevante (coseno≈0.24-0.33) de irrelevante (coseno≈0.38-0.48) en las pruebas.
- **Verificado contra servicios reales, no solo dobles**: `enalapril` (no cacheado) →
  `source: "live"` en 0.76s + indexado; segunda consulta → `source: "cache"` en 0.04s.
  `amlodipino`/`losartan` probados vía HTTP real contra un servidor Uvicorn local.
  `warfarina` → `source: "none"` (CIMA no reconoce ese nombre — en España es "Aldocumar"),
  confirmando el límite real de la coincidencia por nombre literal.
- **Verificación**: 114 tests (`pytest`, +15 nuevos: `test_drug_service.py`,
  `test_pharmacy_agent.py` nuevos; casos añadidos en `test_consult_use_case.py` y
  `test_api_endpoints.py`), `ruff check .`/`ruff format --check .` limpios.
- **Documentación actualizada**: `AGENTS.md` (sección RAGPharmAgent reescrita con nota de
  verificación), `SKILLS.md` (`search_cima_official_data`), `README.md` (ejemplos de
  `/search`/`/consult` actualizados, sección de limitaciones).

---

**[BLOQUE D] — Profesionalización: auth, Docker, orquestación, `SafetyCheckAgent` híbrido,
persistencia, Alembic, tests de clientes, cobertura, evaluación cuantitativa.** Ver
[DECISIONS.md](DECISIONS.md) para el detalle completo de las 9 mejoras. Resumen ejecutivo:

- **Auth + CORS**: `X-API-Key` opcional (`settings.api_key`, desactivada por defecto) a
  nivel de router; `CORSMiddleware` (`settings.cors_allowed_origins`).
- **Docker**: [Dockerfile](../Dockerfile) + servicio `api` en `docker-compose.yml`,
  verificado con build/arranque reales (Docker Desktop) — `/health` → 200 en contenedor.
- **Orquestación**: [`ProcessPrescriptionUseCase`](../src/use_cases/process_prescription.py)
  (`POST /process-prescription`) — receta → extracción → interacciones automáticas si 2+
  fármacos, con persistencia auditable.
- **`SafetyCheckAgent` híbrido**: base curada autoritativa (nunca se consulta al LLM si
  aplica) + razonamiento `llama3` local para combinaciones no cubiertas
  (`source: "curated"|"llm"`). `check_interactions` ahora `async`. Verificado 7/7 correcto
  en evaluación cuantitativa.
- **Persistencia**: `PrescriptionRecordModel`/`Repository` — registro auditable JSON,
  deliberadamente no mapeado a `Prescription`/`PrescribedDrug` (decisión documentada en el
  propio modelo). Verificado con escritura/lectura reales en Postgres.
- **Alembic**: `src/infrastructure/init_db.py` eliminado; migraciones versionadas
  (`migrations/`), primera migración `272aeb551e68`. Bug real corregido en el autogenerate
  (`import pgvector.sqlalchemy` + `CREATE EXTENSION` faltantes). Verificado con
  upgrade/downgrade real + contenedor Docker + nuevo job de CI.
- **Tests de clientes externos**: `test_cima_client.py`/`test_ollama_client.py`
  (`httpx.MockTransport`) + `test_gemini_client.py` (mock del SDK).
- **Cobertura**: `pytest-cov`, umbral 85% en CI (real: ~87%).
- **Evaluación cuantitativa**: [evaluation/](../evaluation/) + [EVALUATION.md](../EVALUATION.md)
  — 7/7 `SafetyCheckAgent` correctos, recall=1.0 `PrescriptionAgent`. **Bug de producción
  real descubierto**: `gemini-1.5-pro` (desde BLOQUE B) fue retirado por Google —
  corregido a `gemini-flash-latest`.
- **Documentación**: `README.md`/`AGENTS.md`/`SKILLS.md` actualizados con el estado real de
  todo lo anterior.
- **Verificación global**: 99 tests (`pytest`) verdes, `ruff check .`/`ruff format --check .`
  limpios, cobertura 87%, migraciones y Docker verificados contra servicios reales.

---

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

Sin un PASO/BLOQUE numerado asignado todavía — [BLOQUE A]/[B]/[C]/[D] están todos cerrados y
verificados, más la corrección posterior de CIMA en vivo en `/search`/`/consult`. Candidatos
para un bloque futuro (no priorizados por el usuario):

1. Desacoplar `DrugRepositoryPort` de `DrugModel` (ORM) con una entidad de dominio `Drug`
   pura (limitación aceptada desde BLOQUE A).
2. Normalizar la extracción de `PrescriptionAgent` a la entidad de dominio
   `Prescription`/`PrescribedDrug` en vez del registro JSON auditable actual — requeriría que
   `GeminiClient` devuelva campos estructurados (`frequency_hours: int`, no
   `"cada 8 horas"`), ver nota en
   [prescription_record_model.py](../src/infrastructure/models/prescription_record_model.py).
3. Ampliar la base curada de `SafetyCheckAgent` más allá de 6 pares, o añadir el *fallback*
   a Gemini remoto descrito en el diseño original de AGENTS.md cuando Ollama no esté
   disponible.
4. Distinguir explícitamente en `SafetyCheckAgent` entre "el LLM respondió que no hay
   interacción" y "el LLM no respondió/timeout" — hoy ambos casos producen `interactions: []`
   sin diferenciarse en la salida (limitación señalada en
   [EVALUATION.md](../EVALUATION.md)).
5. Desplegar la API en un entorno remoto para la defensa del TFM.
6. Orquestar los 3 agentes (incluyendo `RAGPharmAgent`) en un único flujo de nivel superior,
   más allá de `ProcessPrescriptionUseCase` (que solo compone `PrescriptionAgent` +
   `SafetyCheckAgent`).
7. El respaldo de CIMA en vivo depende de coincidencia literal de nombre — considerar
   normalización de nombres comerciales/genéricos (p. ej. mapear "warfarina" → "Aldocumar")
   si se quiere mejorar la tasa de aciertos del respaldo en vivo.
