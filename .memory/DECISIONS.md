# DECISIONS.md — PharmAgent AI Suite

Registro de decisiones clave de arquitectura tomadas durante el desarrollo, complementario a
los ADR formales en [docs/adr/](../docs/adr/).

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
