"""Tests unitarios de `OllamaClient`: manejo defensivo de errores de red/parseo.

Usa `httpx.MockTransport` para simular respuestas del servidor Ollama sin red real —
cubre los casos que el resto de la suite solo ejercita indirectamente a través de
dobles (`FakeOllamaClient` en `tests/integration/conftest.py`).
"""

from __future__ import annotations

import httpx
import pytest

from src.infrastructure.external.ollama_client import OllamaClient


def _client_with_transport(handler) -> OllamaClient:
    """Construye un `OllamaClient` cuyo `httpx.AsyncClient` interno usa `handler`
    como transporte, en vez de hacer peticiones de red reales."""
    client = OllamaClient()
    client._client = httpx.AsyncClient(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(handler),
    )
    return client


class TestGenerateEmbedding:
    @pytest.mark.asyncio
    async def test_returns_embedding_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

        client = _client_with_transport(handler)

        result = await client.generate_embedding("ibuprofeno")

        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_http_error_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client = _client_with_transport(handler)

        result = await client.generate_embedding("ibuprofeno")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_connection_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = _client_with_transport(handler)

        result = await client.generate_embedding("ibuprofeno")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

        client = _client_with_transport(handler)

        result = await client.generate_embedding("ibuprofeno")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_malformed_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json")

        client = _client_with_transport(handler)

        result = await client.generate_embedding("ibuprofeno")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_embedding_field_missing(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        client = _client_with_transport(handler)

        result = await client.generate_embedding("ibuprofeno")

        assert result == []


class TestGenerateCompletion:
    @pytest.mark.asyncio
    async def test_returns_response_text_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"response": "Respuesta generada."})

        client = _client_with_transport(handler)

        result = await client.generate_completion(
            prompt="¿dosis?", system="system prompt"
        )

        assert result == "Respuesta generada."

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_http_error_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client = _client_with_transport(handler)

        result = await client.generate_completion(prompt="¿dosis?")

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_connection_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = _client_with_transport(handler)

        result = await client.generate_completion(prompt="¿dosis?")

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_malformed_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json")

        client = _client_with_transport(handler)

        result = await client.generate_completion(prompt="¿dosis?")

        assert result == ""

    @pytest.mark.asyncio
    async def test_forwards_prompt_system_and_model_in_request_body(self) -> None:
        captured_bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured_bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"response": "ok"})

        client = _client_with_transport(handler)

        await client.generate_completion(
            prompt="¿dosis?", system="eres un asistente", model="llama3"
        )

        assert captured_bodies[0]["prompt"] == "¿dosis?"
        assert captured_bodies[0]["system"] == "eres un asistente"
        assert captured_bodies[0]["model"] == "llama3"
        assert captured_bodies[0]["stream"] is False
