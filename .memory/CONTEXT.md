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

**[BLOQUE B] Observabilidad + `PrescriptionAgent` + `SafetyCheckAgent` — completado.**
Continúa Fase 6 (Ingesta de Datos y Pruebas) en paralelo.

## Último hito verificado

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

**PASO 27** — Formalizar pruebas automatizadas. La verificación end-to-end de
`RAGPharmAgent`, `PrescriptionAgent` y `SafetyCheckAgent` se ha hecho hasta ahora como
pruebas de humo manuales (`TestClient` ad-hoc); queda convertirlas en una suite real en
`tests/unit/`/`tests/integration/` (actualmente vacías). También pendiente: ampliar la base
curada de interacciones de `SafetyCheckAgent` y desacoplar `DrugRepositoryPort` de `DrugModel`
(ORM) con una entidad de dominio `Drug` pura.
