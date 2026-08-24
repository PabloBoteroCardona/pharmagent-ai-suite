"""Cliente HTTP asíncrono para la API pública de CIMA (AEMPS).

Encapsula el acceso de red a `settings.cima_base_url` — usado por `DrugService`
(`src/application/services/`) para poblar la caché semántica local con el texto
oficial de fichas técnicas (`get_ficha_tecnica_html`) y prospectos
(`get_prospecto_html`). Nunca propaga excepciones de red: ante
un fallo de conexión, timeout, respuesta de error o cuerpo vacío (CIMA devuelve
200 con cuerpo vacío para un nregistro/cn inexistente, en vez de un 404),
devuelve una estructura vacía/`None` para que las capas superiores decidan
cómo degradar.
"""

from __future__ import annotations

import json
import logging
from typing import Self

import httpx

from src.infrastructure.config.settings import settings
from src.infrastructure.external.retry import retry_transient_errors

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0

FICHA_TECNICA_TIPO_DOC = 1
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

    @retry_transient_errors
    async def search_medicamentos(self, nombre: str) -> list[dict]:
        """Busca medicamentos por nombre. Devuelve lista vacía si no hay resultados o falla la red."""
        try:
            response = await self._client.get(
                "/medicamentos", params={"nombre": nombre}
            )
            response.raise_for_status()
            return response.json().get("resultados", [])
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning(
                "cima_search_medicamentos_failed",
                extra={"nombre": nombre, "error": str(exc)},
            )
            return []

    @retry_transient_errors
    async def _get_medicamento(self, params: dict[str, str]) -> dict | None:
        try:
            response = await self._client.get("/medicamento", params=params)
            response.raise_for_status()
            return response.json() or None
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            logger.warning(
                "cima_get_medicamento_failed",
                extra={"params": params, "error": str(exc)},
            )
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

    async def get_ficha_tecnica_html(self, nregistro: str) -> str | None:
        """Recupera y concatena el HTML de todas las secciones de la ficha técnica
        oficial — información clínica para profesionales sanitarios (posología exacta,
        farmacocinética, contraindicaciones, interacciones), más completa que el
        prospecto para responder consultas clínicas."""
        return await self._get_documento_segmentado_html(
            nregistro, FICHA_TECNICA_TIPO_DOC
        )

    async def get_prospecto_html(self, nregistro: str) -> str | None:
        """Recupera y concatena el HTML de todas las secciones del prospecto oficial
        — información dirigida al paciente, en lenguaje divulgativo."""
        return await self._get_documento_segmentado_html(nregistro, PROSPECTO_TIPO_DOC)

    @retry_transient_errors
    async def _fetch_documento_segmentado(
        self, nregistro: str, tipo_doc: int
    ) -> httpx.Response:
        response = await self._client.get(
            f"/docSegmentado/contenido/{tipo_doc}",
            params={"nregistro": nregistro},
        )
        response.raise_for_status()
        return response

    async def _get_documento_segmentado_html(
        self, nregistro: str, tipo_doc: int
    ) -> str | None:
        try:
            response = await self._fetch_documento_segmentado(nregistro, tipo_doc)
        except httpx.HTTPError as exc:
            logger.warning(
                "cima_get_documento_segmentado_failed",
                extra={"nregistro": nregistro, "tipo_doc": tipo_doc, "error": str(exc)},
            )
            return None

        try:
            payload = response.json()
            # CIMA es inconsistente también en la forma del JSON: para algunos
            # medicamentos devuelve directamente el array de secciones (`[...]`) en
            # vez de envolverlo en `{"secciones": [...]}`. Bug real en producción:
            # `.get("secciones", [])` sobre una lista lanza `AttributeError` sin
            # capturar, tumbando la petición completa con un 500.
            secciones = (
                payload.get("secciones", []) if isinstance(payload, dict) else payload
            )
        except json.JSONDecodeError:
            # CIMA es inconsistente: para algunos medicamentos (sobre todo genéricos o
            # documentos más antiguos) este endpoint devuelve el texto completo
            # directamente como cuerpo plano, no envuelto en `{"secciones": [...]}` —
            # en ambos casos el `Content-Type` declarado es `text/plain`, así que no
            # sirve para distinguir el caso de antemano (verificado empíricamente:
            # nregistro=68435 devuelve texto plano, nregistro=83348 devuelve JSON, con
            # idéntico Content-Type). Bug real encontrado en producción: antes de este
            # `except`, cualquier medicamento con respuesta en texto plano perdía todo
            # su prospecto/ficha técnica silenciosamente (degradaba a `None`).
            return response.text or None

        html_fragments = [
            seccion["contenido"] for seccion in secciones if seccion.get("contenido")
        ]
        return "\n".join(html_fragments) if html_fragments else None
