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

**Fase 3 — Infraestructura Local.**

## Último hito verificado

Cliente HTTP asíncrono `CimaAPIClient`
([src/infrastructure/external/cima_client.py](../src/infrastructure/external/cima_client.py))
probado en tiempo real contra la API oficial de la AEMPS (`https://cima.aemps.es/cima/rest`):
- `search_medicamentos(nombre)` — búsqueda por nombre.
- `get_medicamento_by_nregistro(nregistro)` / `get_medicamento_by_cn(cn)` — detalle completo.
- `get_prospecto_html(nregistro)` — texto oficial del prospecto.
- Manejo robusto de errores: captura tanto `httpx.HTTPError` como `json.JSONDecodeError`
  (CIMA devuelve `200 OK` con cuerpo vacío para un `nregistro`/`cn` inexistente, en vez de
  un 404 — degradado a `[]`/`None` en ambos casos).

Validado con el script manual [test_cima.py](../test_cima.py) (búsqueda real de
"ibuprofeno", 138 resultados, detalle y CN de los 3 primeros).

## Siguiente paso pendiente

**PASO 18/19** — Crear el modelo ORM `DrugModel` (SQLAlchemy 2.0, sobre `Base` de
[src/infrastructure/database.py](../src/infrastructure/database.py)) y el script
`init_db.py` para habilitar la extensión `pgvector` en PostgreSQL y crear el esquema inicial.
