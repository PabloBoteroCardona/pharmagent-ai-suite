"""Configuración centralizada de la aplicación.

Única fuente de verdad para variables de entorno — sustituye a los `os.getenv`/
`load_dotenv()` dispersos que existían antes en `database.py`, `cima_client.py` y
`ollama_client.py`. Cualquier módulo que necesite un valor de configuración importa
`settings` de aquí, nunca lee el entorno directamente.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno de la aplicación, con valores por defecto seguros para desarrollo local."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "local"
    port: int = 8000

    database_url: str = (
        "postgresql+asyncpg://pharmagent:pharmagent_pass@127.0.0.1:5433/pharmagent_db"
    )

    ollama_base_url: str = "http://localhost:11434"
    cima_base_url: str = "https://cima.aemps.es/cima/rest"

    embedding_provider: str = "ollama"
    google_api_key: str | None = None

    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Punto único de construcción de `Settings`, cacheado (se lee el entorno una sola vez)."""
    return Settings()


settings = get_settings()
