# PharmAgent — instrucciones del proyecto

Sistema multiagente (procesamiento de recetas, verificación de interacciones, consulta RAG
sobre fichas técnicas AEMPS/CIMA) con backend en Clean Architecture (Python/FastAPI) y un
frontend SPA independiente (TypeScript/Vite). Ver [README.md](README.md) para la descripción
completa, [AGENTS.md](AGENTS.md)/[SKILLS.md](SKILLS.md) para el contrato de los agentes, y
[docs/adr/](docs/adr/) para las decisiones de arquitectura.

## Stack

- **Backend** (`src/`): Python 3.12, FastAPI async, Pydantic v2, SQLAlchemy 2.0 async +
  `asyncpg`, PostgreSQL + `pgvector`, Alembic. LLMs: Groq (`llama-3.1-8b-instant`, generación),
  Gemini (`gemini-flash-latest`, multimodal/OCR de recetas), Ollama local (embeddings,
  `nomic-embed-text`).
- **Frontend** (`frontend/`): TypeScript + Vite + Tailwind CSS v4, sin framework de UI (DOM
  directo). Cliente HTTP puro de la API REST — no importa nada de `src/`.
- **Calidad**: Ruff (lint+format), Pytest/`pytest-cov` (backend), Vitest+jsdom (frontend),
  GitHub Actions (`.github/workflows/ci.yml`).

## Comandos esenciales

```bash
# Backend
pytest                                          # suite completa (sin los tests marcados `postgres`, ver abajo)
pytest --cov=src --cov-report=term-missing      # con cobertura (umbral CI: 85%)
pytest -m postgres tests/integration/test_*_postgres.py  # tests de repositorio contra un Postgres real (requiere docker compose up -d postgres + alembic upgrade head)
ruff check . && ruff format --check .           # lint + formato

# Frontend (cd frontend/)
npm test                                        # Vitest
npm run build                                   # tsc -b + vite build (type-check incluido)
npm run dev                                     # servidor de desarrollo
```

## Convenciones de arquitectura (no romper sin querer)

- **Regla de dependencia estricta**: `src/domain/` no importa nada fuera de la librería
  estándar y Pydantic. Las capas externas dependen del dominio a través de `typing.Protocol`
  (`src/domain/ports/`), nunca al revés — los adaptadores de infraestructura los satisfacen
  por tipado estructural (`@runtime_checkable`), sin herencia.
- **Los agentes NO usan Google ADK** pese a que el diseño conceptual original (AGENTS.md,
  ADR 001) lo describía — son clases Python `async` simples. Ambos documentos tienen una nota
  explícita de "Estado real"; no asumir ADK al leer el diseño conceptual.
- **`frontend/src/style.css`**: la paleta clínica vive en un único bloque `@theme` (Tailwind
  v4) — es el mecanismo real que genera las clases `bg-safe-600`/`text-warning-700`/etc. que
  usa el resto del frontend. No sustituir por un `:root` plano sin actualizar todos los call
  sites: las clases dejarían de generarse en silencio, sin error.
- **Autenticación de la API opcional y desactivada por defecto** (`API_KEY` vacía =
  desactivada, consumo local sin fricción). Con `API_KEY` configurada, `pharmacy_router`
  exige `X-API-Key` (ver `security.py`) — necesario antes de exponer la API a Internet, junto
  con `RATE_LIMIT` (por IP, `slowapi`, ver `main.py`) y restringir `CORS_ALLOWED_ORIGINS`.
  Ver [README.md, "Seguridad en un despliegue público"](README.md#seguridad-en-un-despliegue-público).

## Convenciones de testing

- **Backend**: dobles en memoria vía `app.dependency_overrides` de FastAPI
  (`tests/integration/conftest.py`) para tests de endpoint; `httpx.MockTransport`/mocks
  directos para clientes HTTP individuales (`tests/unit/test_*_client.py`). Determinista, sin
  Docker/red/credenciales. Los tests de repositorio (`test_drug_repository_postgres.py`,
  `test_prescription_record_repository_postgres.py`) son la excepción deliberada: corren
  contra un Postgres real (SQL/pgvector reales, no un doble), marcados `postgres` y
  excluidos del `pytest` por defecto (`pytest.ini`, `addopts = -m "not postgres"`) — en CI
  corren en el job `migrations`, que ya levanta el servicio Postgres.
- **Frontend**: Vitest + `jsdom`. Cubre lógica pura (`ui.ts`, `autocomplete.ts`,
  `markdown.ts`) — mocks de `./api` con `vi.mock`, temporizadores falsos (`vi.useFakeTimers`)
  para el debounce del autocompletado.
- Los scripts manuales (`scripts/manual_check_cima.py`, `scripts/ingest_drugs.py`) hacen
  peticiones reales a servicios externos — no son parte de la suite automatizada, no correrlos
  en CI.

## Protocolo de Memoria (`.memory/`, local — no forma parte del repositorio publicado)

`.memory/` es un directorio de trabajo local (listado en `.gitignore`) que da continuidad
entre sesiones de desarrollo asistido: no se sube al repositorio porque es un registro de
proceso (quién pidió qué y por qué), no documentación del producto — la documentación
pública equivalente vive en `README.md`, `AGENTS.md`, `SKILLS.md` y `docs/adr/`.

- Al finalizar cualquier paso del roadmap, implementación de función, corrección de bug o
  prueba (backend **o frontend**), ACTUALIZA SIEMPRE `.memory/CONTEXT.md`.
- Registra el hito completado en "Último hito verificado" y el siguiente paso exacto en
  "Siguiente paso pendiente".
- Si hay decisiones de arquitectura nuevas o bugs resueltos, actualiza también
  `.memory/DECISIONS.md` y `.memory/BUGS.md`.
- Si una decisión o limitación documentada ahí es relevante para quien lea el repositorio
  (no solo para continuidad entre sesiones), reflejarla también en la documentación pública
  correspondiente — `.memory/` no es un sustituto de eso.
