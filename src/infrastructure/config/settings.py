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
    # `False` (por defecto) desactiva SSL explícitamente — necesario para el Postgres de
    # docker-compose.yml, que no lo ofrece. Un Postgres gestionado en un proveedor de
    # despliegue (p. ej. Render) normalmente lo exige; poner `DATABASE_SSL=true` ahí, o la
    # conexión falla. Ver database.py.
    database_ssl: bool = False

    ollama_base_url: str = "http://localhost:11434"
    cima_base_url: str = "https://cima.aemps.es/cima/rest"

    # Embeddings se generan siempre en local (Ollama) por privacidad de datos de salud —
    # nunca se envían a un proveedor externo. `google_api_key` está reservada
    # exclusivamente para el futuro PrescriptionAgent (Gemini 1.5 Pro multimodal, OCR de
    # recetas); no debe usarse para embeddings ni para RAGPharmAgent. Ver DECISIONS.md.
    embedding_provider: str = "ollama"
    google_api_key: str | None = None

    # Generación de texto (no embeddings) de RAGPharmAgent y SafetyCheckAgent: Groq (LPU,
    # <2s de latencia) en vez de Ollama local por CPU (~30s, ver BUGS.md/DECISIONS.md).
    # Los embeddings NO se mueven a Groq — siguen exclusivamente en Ollama local, sin
    # excepción (Groq no ofrece API de embeddings y la política de privacidad de datos de
    # salud de arriba sigue vigente para ese camino). Si `groq_api_key` no está configurada,
    # `GroqClient.generate_completion` degrada a `""` en vez de fallar.
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"

    sentry_dsn: str | None = None

    # Lista de orígenes permitidos por CORS. `["*"]` (por defecto) es apropiado para
    # desarrollo local; en producción debe restringirse a los orígenes reales del cliente.
    cors_allowed_origins: list[str] = ["*"]

    # `None`/vacío (por defecto) desactiva la autenticación por completo — apropiado para
    # desarrollo local, donde el frontend y la API corren en la misma máquina. Poner
    # `API_KEY=<valor>` activa la comprobación de la cabecera `X-API-Key` en todo
    # `pharmacy_router` (ver security.py) — necesario antes de exponer la API a Internet.
    api_key: str | None = None

    # Límite de peticiones por IP en pharmacy_router (protege de abuso/coste descontrolado
    # en Groq/Gemini si la API queda expuesta públicamente). Formato de `slowapi`/`limits`:
    # "<cantidad>/<periodo>".
    rate_limit: str = "30/minute"


@lru_cache
def get_settings() -> Settings:
    """Punto único de construcción de `Settings`, cacheado (se lee el entorno una sola vez)."""
    return Settings()


settings = get_settings()
