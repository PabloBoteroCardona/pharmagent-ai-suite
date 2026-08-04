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

**Fase 4 — Casos de Uso y Agentes de IA.**

## Último hito verificado

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

**PASO 22** — Implementar `DrugService` en `src/application/services/drug_service.py` para
orquestar la ingesta, indexación semántica y búsquedas RAG entre CIMA, Ollama y PostgreSQL.
