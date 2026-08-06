"""Autenticación ligera por API key para `pharmacy_router`.

Desactivada por completo si `settings.api_key` está vacío/ausente (valor por defecto,
apropiado para desarrollo local) — ver `Settings.api_key`. Cuando está configurada, exige
la cabecera `X-API-Key` en cada petición al router; no es un sistema de autenticación de
usuarios (no hay sesiones, roles ni credenciales por cliente), es una barrera mínima contra
abuso anónimo si la API se expone públicamente.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.infrastructure.config.settings import settings


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Dependencia FastAPI: exige `X-API-Key` == `settings.api_key` cuando esta última
    está configurada. Sin `API_KEY` en el entorno, no comprueba nada (auth desactivada)."""
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key inválida o ausente.",
        )
