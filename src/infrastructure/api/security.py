"""Autenticación de la API vía API key en cabecera HTTP.

Mecanismo deliberadamente simple (cabecera estática, sin OAuth/JWT) — adecuado para el
alcance de un TFM con un único cliente de confianza (no hay gestión de usuarios ni de
sesiones en el dominio). Si `settings.api_key` no está configurada (por defecto en
desarrollo local/CI), la autenticación queda desactivada para no bloquear la evaluación ni
los tests.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.infrastructure.config.settings import settings

API_KEY_HEADER_NAME = "X-API-Key"


async def verify_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER_NAME),
) -> None:
    """Verifica la cabecera `X-API-Key` contra `settings.api_key`, si está configurada."""
    if settings.api_key is None:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente.",
        )
