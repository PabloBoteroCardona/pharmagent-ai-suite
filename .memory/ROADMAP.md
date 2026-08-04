# ROADMAP.md — PharmAgent AI Suite

## Fase 1 — Fundamentos y Especificación — ✅ 100%

- `.gitignore`, `requirements.txt`, entorno virtual (`.venv`) e instalación de dependencias.
- `AGENTS.md` — especificación de los 3 agentes (`PrescriptionAgent`, `SafetyCheckAgent`,
  `RAGPharmAgent`).
- `SKILLS.md` — contratos Pydantic v2 de las tools (`extract_prescription_from_image`,
  `check_drug_interactions`, `search_cima_official_data`).
- `.env.example` / `.env`.
- `.pre-commit-config.yaml` (Ruff) instalado.

## Fase 2 — Modelado de Dominio — ✅ 100%

- Entidades de dominio en `src/domain/models/`: `Prescription` / `PrescribedDrug`
  ([prescription.py](../src/domain/models/prescription.py)) y `DrugInteraction`
  ([drug_interaction.py](../src/domain/models/drug_interaction.py)) — Pydantic v2 puro, sin
  dependencias de infraestructura.
- ADR 001 ([docs/adr/001-stack-python-adk.md](../docs/adr/001-stack-python-adk.md)):
  Python 3.11+, monolito modular con Clean Architecture, FastAPI, Google ADK,
  PostgreSQL + pgvector.

## Fase 3 — Infraestructura Local — 🔄 en desarrollo

- ✅ **Paso 16** — `docker-compose.yml`: servicios `postgres` (`pgvector/pgvector:pg16`, con
  healthcheck) y `ollama` (`ollama/ollama:latest`), con volúmenes persistentes
  `postgres_data` y `ollama_data`.
- ✅ **Paso 17** — `src/infrastructure/database.py`: configuración de conexión asíncrona a
  PostgreSQL con SQLAlchemy 2.0 (`async_engine`, `async_sessionmaker`, `Base`,
  `get_db_session`).
- ✅ (adicional, no numerado en el roadmap original) `CimaAPIClient`
  ([src/infrastructure/external/cima_client.py](../src/infrastructure/external/cima_client.py))
  — cliente asíncrono de la API oficial de CIMA/AEMPS, probado en tiempo real. Ver
  [DECISIONS.md](DECISIONS.md) para la decisión de arquitectura asociada.
- ⏳ **Paso 18/19 (pendiente)** — Modelo ORM `DrugModel` (SQLAlchemy, sobre `Base`) y script
  `init_db.py` para habilitar la extensión `pgvector` en PostgreSQL y crear el esquema inicial.

## Fases futuras

Sin detallar todavía — pendientes de definición (implementación de agentes ADK, adaptador
RAG sobre `pgvector`, endpoints FastAPI, tests).
