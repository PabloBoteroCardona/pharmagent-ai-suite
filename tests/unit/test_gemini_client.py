"""Tests unitarios de `GeminiClient`: manejo defensivo de errores de API/parseo.

Sustituye el cliente `google-genai` interno por un doble (`unittest.mock`) — cubre los
casos que la verificación manual contra la API real de Gemini no ejercita: errores de
API, JSON malformado y ausencia de `GOOGLE_API_KEY`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import requests
from google.genai.errors import APIError

from src.infrastructure.external.gemini_client import GeminiClient


def _client_with_mocked_response(response_text: str) -> GeminiClient:
    """Construye un `GeminiClient` cuyo `generate_content` interno devuelve
    `response_text` sin llamar a la API real de Gemini."""
    client = GeminiClient(api_key="fake-key-for-tests")
    fake_response = SimpleNamespace(text=response_text)
    client._client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(
                generate_content=AsyncMock(return_value=fake_response)
            )
        )
    )
    return client


class TestAnalyzePrescriptionImage:
    @pytest.mark.asyncio
    async def test_returns_parsed_drugs_and_advertencias_on_success(self) -> None:
        response_json = (
            '{"drugs": [{"farmaco": "Ibuprofeno", "dosificacion": "600 mg", '
            '"frecuencia": "cada 8 horas", "duracion": "5 días"}], '
            '"advertencias": ["Tomar con alimentos."]}'
        )
        client = _client_with_mocked_response(response_json)

        result = await client.analyze_prescription_image(b"fake-image-bytes")

        assert result == {
            "drugs": [
                {
                    "farmaco": "Ibuprofeno",
                    "dosificacion": "600 mg",
                    "frecuencia": "cada 8 horas",
                    "duracion": "5 días",
                }
            ],
            "advertencias": ["Tomar con alimentos."],
        }

    @pytest.mark.asyncio
    async def test_returns_empty_result_when_no_api_key_configured(self) -> None:
        client = GeminiClient(api_key=None)
        # Sin `GOOGLE_API_KEY` ni override, `settings.google_api_key` decide — en este
        # entorno de test puede o no estar configurada; forzamos el caso sin key.
        client._client = None

        result = await client.analyze_prescription_image(b"fake-image-bytes")

        assert result == {"drugs": [], "advertencias": []}

    @pytest.mark.asyncio
    async def test_returns_empty_result_on_malformed_json_response(self) -> None:
        client = _client_with_mocked_response("esto no es JSON")

        result = await client.analyze_prescription_image(b"fake-image-bytes")

        assert result == {"drugs": [], "advertencias": []}

    @pytest.mark.asyncio
    async def test_returns_empty_result_when_response_is_not_a_json_object(
        self,
    ) -> None:
        client = _client_with_mocked_response('["esto", "es", "una", "lista"]')

        result = await client.analyze_prescription_image(b"fake-image-bytes")

        assert result == {"drugs": [], "advertencias": []}

    @pytest.mark.asyncio
    async def test_returns_empty_result_on_empty_response_text(self) -> None:
        client = _client_with_mocked_response("")

        result = await client.analyze_prescription_image(b"fake-image-bytes")

        assert result == {"drugs": [], "advertencias": []}

    @pytest.mark.asyncio
    async def test_returns_empty_result_on_api_error(self) -> None:
        client = GeminiClient(api_key="fake-key-for-tests")
        fake_http_response = requests.Response()
        fake_http_response.status_code = 503
        fake_http_response._content = b'{"message": "service unavailable"}'
        api_error = APIError(code=503, response=fake_http_response)
        client._client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    generate_content=AsyncMock(side_effect=api_error)
                )
            )
        )

        result = await client.analyze_prescription_image(b"fake-image-bytes")

        assert result == {"drugs": [], "advertencias": []}

    @pytest.mark.asyncio
    async def test_returns_empty_result_on_read_timeout(self) -> None:
        """Bug real en producción: `google-genai` usa `requests` (no httpx) para sus
        llamadas HTTP internas — `requests.exceptions.ReadTimeout` no estaba entre las
        excepciones capturadas, así que un timeout de Gemini (bajo alta demanda de
        Google) se propagaba sin capturar y tumbaba la petición con un 500 en vez de
        degradar como el resto de fallos de este cliente."""
        client = GeminiClient(api_key="fake-key-for-tests")
        client._client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    generate_content=AsyncMock(
                        side_effect=requests.exceptions.ReadTimeout("timed out")
                    )
                )
            )
        )

        result = await client.analyze_prescription_image(b"fake-image-bytes")

        assert result == {"drugs": [], "advertencias": []}

    @pytest.mark.asyncio
    async def test_defaults_missing_fields_to_empty_lists(self) -> None:
        """Si el modelo devuelve un JSON válido pero sin alguno de los campos
        esperados, el cliente no debe lanzar `KeyError`."""
        client = _client_with_mocked_response('{"unrelated_field": true}')

        result = await client.analyze_prescription_image(b"fake-image-bytes")

        assert result == {"drugs": [], "advertencias": []}

    @pytest.mark.asyncio
    async def test_forwards_image_bytes_and_mime_type_to_the_model(self) -> None:
        client = GeminiClient(api_key="fake-key-for-tests")
        fake_response = SimpleNamespace(text='{"drugs": [], "advertencias": []}')
        generate_content_mock = AsyncMock(return_value=fake_response)
        client._client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content_mock)
            )
        )

        await client.analyze_prescription_image(
            b"raw-image-bytes", mime_type="image/png"
        )

        generate_content_mock.assert_awaited_once()
        call_kwargs = generate_content_mock.call_args.kwargs
        assert call_kwargs["contents"][0].inline_data.data == b"raw-image-bytes"
        assert call_kwargs["contents"][0].inline_data.mime_type == "image/png"
