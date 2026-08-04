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
