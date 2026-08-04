"""Cliente HTTP asíncrono para la API pública de CIMA (AEMPS).

Encapsula el acceso de red a https://cima.aemps.es/cima/rest — usado por el
adaptador RAG (`src/adapters/rag/`) para poblar el almacén vectorial con el
texto oficial de fichas técnicas y prospectos. Nunca propaga excepciones de
red: ante un fallo de conexión, timeout o respuesta de error, devuelve una
estructura vacía/`None` para que las capas superiores decidan cómo degradar.
"""

from __future__ import annotations

from typing import Self

import httpx

CIMA_BASE_URL = "https://cima.aemps.es/cima/rest"
DEFAULT_TIMEOUT_SECONDS = 10.0

PROSPECTO_TIPO_DOC = 2


class CimaAPIClient:
    """Cliente de la API REST de CIMA/AEMPS."""

    def __init__(
        self, base_url: str = CIMA_BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search_medicamento(self, nombre: str) -> list[dict]:
        """Busca medicamentos por nombre. Devuelve lista vacía si no hay resultados o falla la red."""
        try:
            response = await self._client.get(
                "/medicamentos", params={"nombre": nombre}
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        return response.json().get("resultados", [])

    async def get_medicamento_by_nregistro(self, nregistro: str) -> dict | None:
        """Obtiene la ficha completa de un medicamento por número de registro."""
        try:
            response = await self._client.get(
                "/medicamento", params={"nregistro": nregistro}
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        data = response.json()
        return data or None

    async def get_prospecto_html(self, nregistro: str) -> str | None:
        """Recupera y concatena el HTML de todas las secciones del prospecto oficial."""
        try:
            response = await self._client.get(
                f"/docSegmentado/contenido/{PROSPECTO_TIPO_DOC}",
                params={"nregistro": nregistro},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        secciones = response.json().get("secciones", [])
        html_fragments = [
            seccion["contenido"] for seccion in secciones if seccion.get("contenido")
        ]
        return "\n".join(html_fragments) if html_fragments else None
