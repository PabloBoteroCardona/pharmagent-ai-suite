"""Cliente HTTP asíncrono para la API pública de CIMA (AEMPS).

Encapsula el acceso de red a `settings.cima_base_url` — usado por `DrugService`
(`src/application/services/`) para poblar la caché semántica local con el texto
oficial de fichas técnicas y prospectos. Nunca propaga excepciones de red: ante
un fallo de conexión, timeout, respuesta de error o cuerpo vacío (CIMA devuelve
200 con cuerpo vacío para un nregistro/cn inexistente, en vez de un 404),
devuelve una estructura vacía/`None` para que las capas superiores decidan
cómo degradar.
"""

from __future__ import annotations

import json
from typing import Self

import httpx

from src.infrastructure.config.settings import settings

DEFAULT_TIMEOUT_SECONDS = 10.0

PROSPECTO_TIPO_DOC = 2


class CimaAPIClient:
    """Cliente de la API REST de CIMA/AEMPS."""

    def __init__(
        self, base_url: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.cima_base_url, timeout=timeout
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search_medicamentos(self, nombre: str) -> list[dict]:
        """Busca medicamentos por nombre. Devuelve lista vacía si no hay resultados o falla la red."""
        try:
            response = await self._client.get(
                "/medicamentos", params={"nombre": nombre}
            )
            response.raise_for_status()
            return response.json().get("resultados", [])
        except (httpx.HTTPError, json.JSONDecodeError):
            return []

    async def _get_medicamento(self, params: dict[str, str]) -> dict | None:
        try:
            response = await self._client.get("/medicamento", params=params)
            response.raise_for_status()
            return response.json() or None
        except (httpx.HTTPError, json.JSONDecodeError):
            return None

    async def get_medicamento_by_nregistro(self, nregistro: str) -> dict | None:
        """Obtiene la ficha completa de un medicamento por número de registro."""
        return await self._get_medicamento({"nregistro": nregistro})

    async def get_medicamento_by_cn(self, cn: str) -> dict | None:
        """Obtiene la ficha completa de un medicamento por código nacional (CN) del envase.

        Permite ir directo a la ficha cuando ya se conoce el CN (p. ej. leído del
        cupón-precinto), sin pasar por `search_medicamentos` ni recorrer resultados.
        """
        return await self._get_medicamento({"cn": cn})

    async def get_prospecto_html(self, nregistro: str) -> str | None:
        """Recupera y concatena el HTML de todas las secciones del prospecto oficial."""
        try:
            response = await self._client.get(
                f"/docSegmentado/contenido/{PROSPECTO_TIPO_DOC}",
                params={"nregistro": nregistro},
            )
            response.raise_for_status()
            secciones = response.json().get("secciones", [])
        except (httpx.HTTPError, json.JSONDecodeError):
            return None

        html_fragments = [
            seccion["contenido"] for seccion in secciones if seccion.get("contenido")
        ]
        return "\n".join(html_fragments) if html_fragments else None
