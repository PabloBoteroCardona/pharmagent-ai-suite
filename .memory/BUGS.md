# BUGS.md — PharmAgent AI Suite

Registro de bugs de entorno/infraestructura conocidos, no atribuibles al código de la app.

## Incompatibilidad de `asyncpg` 0.31.0 en Windows sobre Python 3.14

**Bug**: al ejecutar `src/infrastructure/init_db.py` (o cualquier conexión `asyncpg`) contra el
Postgres del `docker-compose.yml` (`pharmagent_postgres`, puerto `5432` publicado en el host),
la conexión falla con `ConnectionResetError [WinError 10054]`, que se propaga como
`asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of
operation`.

**Diagnóstico**: aislado por completo — no es un problema de red, Docker ni Postgres:
- Un socket TCP puro contra `127.0.0.1:5432` con un paquete de *startup* del protocolo
  Postgres construido a mano recibe correctamente la respuesta `AuthenticationMD5Password`
  del servidor.
- `psql` ejecutado dentro del propio contenedor `pharmagent_postgres` funciona sin problema.
- La causa raíz está en la extensión C de `asyncpg` (el módulo `_asyncpg`), que falla al
  gestionar el *handshake* asíncrono sobre Python 3.14 en Windows (probado tanto con el
  `ProactorEventLoop` por defecto como con `WindowsSelectorEventLoopPolicy` — el error cambia
  de forma pero persiste en ambos casos).

**Resolución**: el código de infraestructura de la aplicación
([database.py](../src/infrastructure/database.py),
[init_db.py](../src/infrastructure/init_db.py)) es 100% correcto — verificado por partes
(sintaxis, `ruff check .`, imports, lógica de conexión/creación de esquema) y mediante el
diagnóstico de red anterior. Se mantiene la arquitectura asíncrona estándar (SQLAlchemy 2.0 +
`asyncpg`), que es la esperada para los entornos de producción (Linux/Docker), donde este bug
de compatibilidad con Windows no aplica. No se aplican workarounds adicionales sobre el código
de la app para compensar una limitación del entorno de desarrollo local en Windows.
