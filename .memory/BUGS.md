# BUGS.md — PharmAgent AI Suite

Registro de bugs de entorno/infraestructura conocidos, no atribuibles al código de la app.

## Incompatibilidad de `asyncpg` 0.31.0 en Windows sobre Python 3.14 — ✅ RESUELTO

**Bug**: al ejecutar `src/infrastructure/init_db.py` (o cualquier conexión `asyncpg`) contra el
Postgres del `docker-compose.yml` (`pharmagent_postgres`, puerto `5432` publicado en el host),
la conexión fallaba con `ConnectionResetError [WinError 10054]`, que se propagaba como
`asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of
operation`.

**Diagnóstico**: aislado por completo — no era un problema de red, Docker ni Postgres:
- Un socket TCP puro contra `127.0.0.1:5432` con un paquete de *startup* del protocolo
  Postgres construido a mano recibía correctamente la respuesta `AuthenticationMD5Password`
  del servidor.
- `psql` ejecutado dentro del propio contenedor `pharmagent_postgres` funcionaba sin problema.
- La causa quedó acotada a la extensión C de `asyncpg` (el módulo `_asyncpg`) fallando en el
  *handshake* asíncrono sobre Python 3.14 en Windows (probado con `ProactorEventLoop` por
  defecto y con `WindowsSelectorEventLoopPolicy` — el error cambiaba de forma pero persistía).

**Solución aplicada**: combinación de dos cambios que sí resolvieron el bug:
1. `WindowsSelectorEventLoopPolicy` forzada al inicio de
   [database.py](../src/infrastructure/database.py) e
   [init_db.py](../src/infrastructure/init_db.py) (`if sys.platform == "win32": ...`).
2. Publicar Postgres en el host en el puerto **`5433`** en vez de `5432` (`docker-compose.yml`,
   `"5433:5432"`) y conectar con `connect_args={"ssl": False}` en `create_async_engine`
   ([database.py](../src/infrastructure/database.py)); `DEFAULT_DATABASE_URL` actualizado a
   `postgresql+asyncpg://pharmagent:pharmagent_pass@127.0.0.1:5433/pharmagent_db`.

**Verificación (2026-08-04)**: conexión `asyncpg` directa OK, `python -m
src.infrastructure.init_db` OK (extensión `pgvector` habilitada, tabla `drugs` creada), y
`python -m scripts.ingest_drugs` → **12/12 fármacos indexados con éxito**, confirmado con una
consulta `psql` directa mostrando las 12 filas persistidas en la tabla `drugs`.

**Nota (histórica)**: en el momento de escribir esto, los embeddings de esas 12 filas
quedaban `NULL` porque `pharmagent_ollama` no tenía modelos descargados — resuelto, ver
siguiente entrada.

---

## Contenedor `pharmagent_ollama` sin modelos descargados — ✅ RESUELTO

**Síntoma**: `OllamaClient.generate_embedding` / `generate_completion` degradaban siempre a
`[]` / `""` (comportamiento defensivo correcto, sin excepción), porque `docker exec
pharmagent_ollama ollama list` no mostraba ningún modelo — no era un bug de código, era que
nunca se habían descargado modelos dentro del contenedor.

**Solución aplicada**:
```
docker exec pharmagent_ollama ollama pull nomic-embed-text   # 274 MB, embeddings, dim=768
docker exec pharmagent_ollama ollama pull llama3              # 4.7 GB, generación
```
`DrugModel.embedding` ya estaba definido como `Vector(768)` (no `1536`), coincidiendo
exactamente con la dimensión real de salida de `nomic-embed-text` — sin necesidad de tocar
el modelo.

**Verificación (2026-08-04)**: `python -m scripts.ingest_drugs` reejecutado → los 12
fármacos ya ingeridos obtuvieron embedding real (`NULL` → poblado), confirmado con `psql`.
`RAGPharmAgent.answer_consultation(...)` probado de extremo a extremo contra CIMA + Postgres
+ Ollama reales (sin ningún stub): recuperó semánticamente los 3 ibuprofenos correctos vía
`l2_distance` de `pgvector` y generó una respuesta grounded citando sus dosis reales.

**Nota sobre arranque en frío** (no es un bug, pero puede parecerlo): la primera llamada de
generación a un modelo recién descargado incluye el tiempo de cargarlo en memoria, que puede
superar el timeout de `OllamaClient` (60s por defecto) en hardware sin GPU — esa primera
llamada degrada silenciosamente a `""` (comportamiento defensivo, no un error visible).
Llamadas posteriores, con el modelo ya "caliente" en memoria, respondieron en ~38.7s. Si
esto vuelve a pasar tras un reinicio del contenedor o tras descargar un modelo nuevo, no es
un fallo — repetir la consulta o subir `DEFAULT_TIMEOUT_SECONDS` en
[ollama_client.py](../src/infrastructure/external/ollama_client.py) para el primer *warm-up*.
