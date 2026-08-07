import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# El proyecto no se instala como paquete (ver README) — el directorio raíz debe estar en
# `sys.path` para poder importar `src.*` cuando Alembic se ejecuta desde `migrations/`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.infrastructure.config.settings import settings
from src.infrastructure.database import Base
from src.infrastructure.models import (  # noqa: F401
    DrugModel,
    PrescriptionRecordModel,
)

# Este es el objeto Config de Alembic, que da acceso a los valores del archivo .ini en uso.
config = context.config

# Interpreta el archivo de configuración para el logging de Python.
# Esta línea configura los loggers.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `settings.database_url` (pydantic-settings, ver BLOQUE A) es la única fuente de verdad
# para la URL de conexión — sustituye el placeholder `driver://user:pass@...` de
# `alembic.ini` para no duplicar la configuración de la base de datos.
#
# `.replace("%", "%%")`: `Config.set_main_option` escribe en un `configparser.ConfigParser`
# interno, cuya interpolación por defecto trata `%` como sintaxis especial (`%(nombre)s`) —
# una URL con una contraseña que contenga `%` (p. ej. tras aplicar percent-encoding a un
# carácter especial, `/` → `%2F`) rompe `set_main_option` con
# `ValueError: invalid interpolation syntax` si no se escapa antes. Workaround documentado
# por el propio Alembic para URLs con caracteres especiales en la contraseña.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# `Base.metadata` (poblada al importar los modelos ORM arriba) habilita `--autogenerate`.
target_metadata = Base.metadata

# Otros valores de la configuración, según las necesidades de env.py, pueden obtenerse así:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Ejecuta las migraciones en modo 'offline'.

    Configura el contexto solo con una URL, no con un Engine (aunque un Engine también
    sería válido aquí). Al omitir la creación del Engine, ni siquiera hace falta que haya
    una DBAPI disponible.

    Las llamadas a context.execute() aquí emiten la cadena dada a la salida del script.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """En este escenario hace falta crear un Engine y asociar una conexión al contexto."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Ejecuta las migraciones en modo 'online'."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
