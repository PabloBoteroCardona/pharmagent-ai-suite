# ROADMAP.md — PharmAgent AI Suite

## Fase 1 — Fundamentos y Especificación — ✅ 100%

- `.gitignore`, `requirements.txt`, entorno virtual (`.venv`) e instalación de dependencias.
- `AGENTS.md` — especificación de los 3 agentes (`PrescriptionAgent`, `SafetyCheckAgent`,
  `RAGPharmAgent`).
- `SKILLS.md` — contratos Pydantic v2 de las tools (`extract_prescription_from_image`,
  `check_drug_interactions`, `search_cima_official_data`).
- `.env.example` / `.env`.
- `.pre-commit-config.yaml` (Ruff) instalado.
- `CLAUDE.md` — Protocolo de Memoria (actualizar `.memory/CONTEXT.md` al cierre de cada paso).

## Fase 2 — Modelado de Dominio — ✅ 100%

- Entidades de dominio en `src/domain/models/`: `Prescription` / `PrescribedDrug`
  ([prescription.py](../src/domain/models/prescription.py)) y `DrugInteraction`
  ([drug_interaction.py](../src/domain/models/drug_interaction.py)) — Pydantic v2 puro, sin
  dependencias de infraestructura.
- ADR 001 ([docs/adr/001-stack-python-adk.md](../docs/adr/001-stack-python-adk.md)):
  Python 3.11+, monolito modular con Clean Architecture, FastAPI, Google ADK,
  PostgreSQL + pgvector.

## Fase 3 — Infraestructura Local — ✅ 100%

- **Paso 15/16** — `docker-compose.yml`: servicios `postgres` (`pgvector/pgvector:pg16`, con
  healthcheck) y `ollama` (`ollama/ollama:latest`), con volúmenes persistentes
  `postgres_data` y `ollama_data`.
- **Paso 17** — [database.py](../src/infrastructure/database.py): conexión asíncrona a
  PostgreSQL con SQLAlchemy 2.0 (`async_engine`, `async_sessionmaker`, `Base`,
  `get_db_session`).
- **Paso 18** — [`CimaAPIClient`](../src/infrastructure/external/cima_client.py): cliente
  asíncrono de la API oficial de CIMA/AEMPS (búsqueda, detalle por `nregistro`/`cn`,
  prospecto). Probado en tiempo real — ver decisión asociada en [DECISIONS.md](DECISIONS.md).
- **Paso 18/19** — [`DrugModel`](../src/infrastructure/models/drug_model.py) (SQLAlchemy 2.0
  + `pgvector`) y [init_db.py](../src/infrastructure/init_db.py) (extensión `pgvector` +
  esquema inicial).
- **Paso 20** — [`DrugRepository`](../src/infrastructure/repositories/) (`save_drug`,
  `get_by_nregistro`, `search_similar_by_vector` con `l2_distance`).
- **Paso 21** — [`OllamaClient`](../src/infrastructure/external/ollama_client.py)
  (`generate_embedding`, `generate_completion`), manejo defensivo de errores, timeout 60s.

## Fase 4 — Casos de Uso y Agentes de IA — ✅ 100%

- **Paso 22** — [`DrugService`](../src/application/services/drug_service.py):
  `fetch_and_index_drug(nregistro)` (CIMA → embedding Ollama → caché Postgres) y
  `search_drugs_semantic(query, limit)`.
- **Paso 23** — [`RAGPharmAgent`](../src/application/agents/pharmacy_agent.py):
  `answer_consultation(query)` — búsqueda semántica, contexto grounded, generación vía
  Ollama, respuesta `{"query", "response", "sources"}`.

## Fase 5 — API REST y Exposición de Servicios — ✅ 100%

- **Paso 24** — Esquemas Pydantic
  ([drug_schemas.py](../src/infrastructure/api/schemas/drug_schemas.py)) y endpoints
  ([pharmacy_router.py](../src/infrastructure/api/routers/pharmacy_router.py)):
  `POST /api/v1/pharmacy/search`, `POST /api/v1/pharmacy/consult`. App FastAPI
  ([main.py](../src/infrastructure/api/main.py)) con `GET /health`. Cadena de dependencias
  (`Depends`) validada end-to-end con `TestClient`.
- **Paso 25** — Documentación y ejecución del servidor con Uvicorn: **no registrado como
  ejecutado en esta conversación** — pendiente de confirmar/retomar si aún no se hizo.

## Fase 6 — Ingesta de Datos y Pruebas — 🔄 en desarrollo

- ✅ **Paso 26** — [scripts/ingest_drugs.py](../scripts/ingest_drugs.py): `ingest_top_drugs()`
  busca en CIMA (`ibuprofeno`, `paracetamol`, `amoxicilina`, `omeprazol`) e indexa los 3
  primeros resultados de cada término vía `DrugService.fetch_and_index_drug`, con manejo de
  fallos por fármaco (un error puntual no aborta el lote). **12/12 fármacos indexados con
  embedding real**, confirmado con `psql` directo sobre la tabla `drugs`.
- 🔄 **Paso 27 (siguiente)** — Pruebas End-to-End del Agente RAG. Ya verificado manualmente
  (`RAGPharmAgent.answer_consultation` funcionando contra CIMA + Postgres + Ollama reales,
  sin stubs — ver [BUGS.md](BUGS.md)); falta formalizarlo como suite de tests automatizados.

## Bugs de entorno — ambos ✅ RESUELTOS

- `asyncpg` 0.31.0 era incompatible con Python 3.14 en Windows (aislado y confirmado: no era
  un problema de Docker, Postgres ni del código de la app) y bloqueaba toda escritura/lectura
  real contra Postgres. **Solucionado** combinando `WindowsSelectorEventLoopPolicy` +
  Postgres publicado en el puerto `5433` (en vez de `5432`) + `connect_args={"ssl": False}`
  en el engine.
- El contenedor `pharmagent_ollama` no tenía ningún modelo descargado, por lo que
  `generate_embedding`/`generate_completion` degradaban siempre a `[]`/`""`. **Solucionado**
  descargando `nomic-embed-text` (embeddings, dim=768) y `llama3` (generación).

Detalle completo y verificación de ambos en [BUGS.md](BUGS.md). **Ya no hay bloqueadores de
entorno conocidos** — el pipeline completo (CIMA → Ollama → Postgres/pgvector →
`RAGPharmAgent`) funciona de extremo a extremo con datos y modelos reales.

## [BLOQUE A] Refactorización y orden del proyecto — ✅ completado

Ejecutado tras el análisis de arquitectura del handoff, en paralelo a la Fase 6. Detalle
completo en [DECISIONS.md](DECISIONS.md).

- **Configuración centralizada**: `pydantic-settings` +
  [`Settings`](../src/infrastructure/config/settings.py) — sustituye los
  `os.getenv`/`load_dotenv()` dispersos en `database.py`, `cima_client.py`,
  `ollama_client.py`.
- **Puertos de dominio**: [`src/domain/ports/drug_ports.py`](../src/domain/ports/drug_ports.py)
  (`CimaDataSourcePort`, `LanguageModelPort`, `DrugRepositoryPort`) — `DrugService` y
  `RAGPharmAgent` invierten su dependencia hacia estos puertos, no hacia las clases
  concretas de infraestructura.
- **Limpieza**: `src/adapters/{adk,db,rag}/` (vacío) eliminado.
- **Caso de uso explícito**: [`ConsultDrugRAGUseCase`](../src/use_cases/consult_drug_rag.py),
  conectado en `pharmacy_router.py` (`/consult` ya no llama a `RAGPharmAgent` directamente).
- Verificado sin regresiones: `ruff`, ingesta real (12/12), y los 3 endpoints de la API
  contra CIMA + Postgres + Ollama reales.
- Pendiente explícito (fuera de alcance de este bloque): `DrugRepositoryPort` sigue
  acoplado a `DrugModel` (tipo ORM) — requeriría una entidad de dominio `Drug` pura.

## [BLOQUE B] Observabilidad + `PrescriptionAgent` + `SafetyCheckAgent` — ✅ completado

Detalle completo y verificación en [DECISIONS.md](DECISIONS.md).

- **Sentry**: `sentry_sdk.init()` en [main.py](../src/infrastructure/api/main.py), condicionado
  a `settings.sentry_dsn`.
- **`GeminiClient`** ([gemini_client.py](../src/infrastructure/external/gemini_client.py)):
  `google-genai` + `gemini-1.5-pro` multimodal, `analyze_prescription_image(image_bytes)` →
  JSON estructurado (`drugs`, `advertencias`). Único consumidor de `GOOGLE_API_KEY`.
- **`PrescriptionAgent`** ([prescription_agent.py](../src/application/agents/prescription_agent.py)):
  orquesta `GeminiClient` vía el nuevo puerto `PrescriptionVisionPort`.
- **`SafetyCheckAgent`** ([safety_agent.py](../src/application/agents/safety_agent.py)):
  verifica interacciones sobre una base curada (6 pares) usando la entidad de dominio
  `DrugInteraction`; veredicto `apto`/`apto_con_precaucion`/`requiere_revision_medica`.
- **Endpoints nuevos**: `POST /api/v1/pharmacy/analyze-prescription` (`UploadFile`) y
  `POST /api/v1/pharmacy/check-interactions`.
- Verificado sin regresiones: `ruff` limpio; `TestClient` end-to-end incluyendo dos llamadas
  reales a la API de Gemini 1.5 Pro (bytes inválidos → degradación correcta; JPEG válido sin
  contenido → `drugs: []`, sin alucinación).
- Pendiente explícito: `SafetyCheckAgent` usa una base de interacciones curada mínima, no una
  fuente clínica completa.

## Fases futuras

Sin detallar todavía — pendientes de definición (tests automatizados, despliegue, entidad de
dominio `Drug` desacoplada del ORM, ampliación de la base de interacciones de
`SafetyCheckAgent`, orquestación de los 3 agentes vía Google ADK real).
