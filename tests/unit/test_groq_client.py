"""Tests unitarios de `GroqClient`: manejo defensivo de errores de red/parseo y
degradación cuando no hay API key configurada.

Usa `httpx.MockTransport` para simular respuestas de la API de Groq sin red real — mismo
patrón que `test_ollama_client.py`/`test_cima_client.py`.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.infrastructure.external.groq_client import GroqClient


def _client_with_transport(
    handler, api_key: str | None = "fake-groq-key"
) -> GroqClient:
    """Construye un `GroqClient` cuyo `httpx.AsyncClient` interno usa `handler` como
    transporte, en vez de hacer peticiones de red reales.

    Fuerza `_api_key` directamente tras la construcción (en vez de confiar en el
    fallback del constructor a `settings.groq_api_key`): si este entorno de test tiene un
    `.env` local con una `GROQ_API_KEY` real configurada, el constructor la usaría pese a
    pedir `api_key=None`, igual que ya ocurre en `GeminiClient` (ver
    `test_gemini_client.py`, `test_returns_empty_result_when_no_api_key_configured`)."""
    client = GroqClient(api_key=api_key)
    client._api_key = api_key
    client._client = httpx.AsyncClient(
        base_url="https://api.groq.com/openai/v1",
        transport=httpx.MockTransport(handler),
    )
    return client


class TestGenerateEmbedding:
    @pytest.mark.asyncio
    async def test_always_returns_empty_list_without_any_network_call(self) -> None:
        """Groq no ofrece API de embeddings — este método es un stub inerte que nunca
        debería llegar a hacer una petición de red."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("generate_embedding no debería hacer ninguna petición")

        client = _client_with_transport(handler)

        result = await client.generate_embedding("ibuprofeno")

        assert result == []


class TestGenerateCompletion:
    @pytest.mark.asyncio
    async def test_returns_message_content_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Respuesta generada."}}]},
            )

        client = _client_with_transport(handler)

        result = await client.generate_completion(
            prompt="¿dosis?", system="system prompt"
        )

        assert result == "Respuesta generada."

    @pytest.mark.asyncio
    async def test_returns_empty_string_without_api_key_and_makes_no_request(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no debería llamar a la API sin api_key configurada")

        client = _client_with_transport(handler, api_key=None)

        result = await client.generate_completion(prompt="¿dosis?")

        assert result == ""

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
    async def test_returns_empty_string_on_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

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
    async def test_returns_empty_string_when_choices_field_missing(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        client = _client_with_transport(handler)

        result = await client.generate_completion(prompt="¿dosis?")

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_choices_list_is_empty(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": []})

        client = _client_with_transport(handler)

        result = await client.generate_completion(prompt="¿dosis?")

        assert result == ""

    @pytest.mark.asyncio
    async def test_forwards_prompt_system_and_model_and_auth_header_in_request(
        self,
    ) -> None:
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]}
            )

        client = _client_with_transport(handler, api_key="secret-groq-key")

        await client.generate_completion(
            prompt="¿dosis?", system="eres un asistente", model="llama-3.1-8b-instant"
        )

        request = captured_requests[0]
        body = json.loads(request.content)
        assert body["model"] == "llama-3.1-8b-instant"
        assert body["messages"] == [
            {"role": "system", "content": "eres un asistente"},
            {"role": "user", "content": "¿dosis?"},
        ]
        assert request.headers["Authorization"] == "Bearer secret-groq-key"

    @pytest.mark.asyncio
    async def test_forwards_temperature_when_given(self) -> None:
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]}
            )

        client = _client_with_transport(handler)

        await client.generate_completion(prompt="¿dosis?", temperature=0.0)

        body = json.loads(captured_requests[0].content)
        assert body["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_omits_temperature_field_when_not_given(self) -> None:
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]}
            )

        client = _client_with_transport(handler)

        await client.generate_completion(prompt="¿dosis?")

        body = json.loads(captured_requests[0].content)
        assert "temperature" not in body

    @pytest.mark.asyncio
    async def test_omits_system_message_when_system_is_empty(self) -> None:
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]}
            )

        client = _client_with_transport(handler)

        await client.generate_completion(prompt="¿dosis?")

        body = json.loads(captured_requests[0].content)
        assert body["messages"] == [{"role": "user", "content": "¿dosis?"}]
