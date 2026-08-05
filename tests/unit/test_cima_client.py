"""Tests unitarios de `CimaAPIClient`: manejo defensivo de errores de red/parseo.

Usa `httpx.MockTransport` para simular respuestas de la API de CIMA sin red real —
cubre los casos que el resto de la suite solo ejercita indirectamente a través de
dobles (`FakeCimaClient` en `tests/integration/conftest.py`).
"""

from __future__ import annotations

import httpx
import pytest

from src.infrastructure.external.cima_client import CimaAPIClient


def _client_with_transport(handler) -> CimaAPIClient:
    """Construye un `CimaAPIClient` cuyo `httpx.AsyncClient` interno usa `handler`
    como transporte, en vez de hacer peticiones de red reales."""
    client = CimaAPIClient()
    client._client = httpx.AsyncClient(
        base_url="https://cima.aemps.es/cima/rest",
        transport=httpx.MockTransport(handler),
    )
    return client


class TestSearchMedicamentos:
    @pytest.mark.asyncio
    async def test_returns_resultados_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"resultados": [{"nombre": "Ibuprofeno"}]})

        client = _client_with_transport(handler)

        result = await client.search_medicamentos("ibuprofeno")

        assert result == [{"nombre": "Ibuprofeno"}]

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_http_error_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client = _client_with_transport(handler)

        result = await client.search_medicamentos("ibuprofeno")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_connection_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = _client_with_transport(handler)

        result = await client.search_medicamentos("ibuprofeno")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_malformed_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json")

        client = _client_with_transport(handler)

        result = await client.search_medicamentos("ibuprofeno")

        assert result == []


class TestGetMedicamentoByNregistro:
    @pytest.mark.asyncio
    async def test_returns_ficha_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"nombre": "Ibuprofeno 600mg"})

        client = _client_with_transport(handler)

        result = await client.get_medicamento_by_nregistro("12345")

        assert result == {"nombre": "Ibuprofeno 600mg"}

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_body_for_unknown_nregistro(self) -> None:
        """CIMA devuelve 200 OK con cuerpo vacío para un nregistro inexistente, no un 404."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"")

        client = _client_with_transport(handler)

        result = await client.get_medicamento_by_nregistro("00000")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

        client = _client_with_transport(handler)

        result = await client.get_medicamento_by_nregistro("12345")

        assert result is None


class TestGetMedicamentoByCn:
    @pytest.mark.asyncio
    async def test_returns_ficha_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["cn"] == "999888777"
            return httpx.Response(200, json={"nombre": "Ibuprofeno 600mg"})

        client = _client_with_transport(handler)

        result = await client.get_medicamento_by_cn("999888777")

        assert result == {"nombre": "Ibuprofeno 600mg"}

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        client = _client_with_transport(handler)

        result = await client.get_medicamento_by_cn("000000000")

        assert result is None


class TestGetProspectoHtml:
    @pytest.mark.asyncio
    async def test_concatenates_html_fragments(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "secciones": [
                        {"contenido": "<p>Sección 1</p>"},
                        {"contenido": "<p>Sección 2</p>"},
                    ]
                },
            )

        client = _client_with_transport(handler)

        result = await client.get_prospecto_html("12345")

        assert result == "<p>Sección 1</p>\n<p>Sección 2</p>"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_secciones(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"secciones": []})

        client = _client_with_transport(handler)

        result = await client.get_prospecto_html("12345")

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_secciones_without_contenido(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "secciones": [
                        {"contenido": "<p>Con contenido</p>"},
                        {"otronombre": "sin campo contenido"},
                    ]
                },
            )

        client = _client_with_transport(handler)

        result = await client.get_prospecto_html("12345")

        assert result == "<p>Con contenido</p>"

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        client = _client_with_transport(handler)

        result = await client.get_prospecto_html("12345")

        assert result is None
