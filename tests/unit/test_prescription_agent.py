"""Tests unitarios de `PrescriptionAgent`, con un doble de `PrescriptionVisionPort`."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.application.agents.prescription_agent import PrescriptionAgent
from src.domain.ports import PrescriptionVisionPort


class FakeVisionClient:
    """Doble de prueba que satisface `PrescriptionVisionPort` estructuralmente."""

    def __init__(self, result: dict) -> None:
        self._result = result
        self.received_calls: list[tuple[bytes, str]] = []

    async def analyze_prescription_image(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> dict:
        self.received_calls.append((image_bytes, mime_type))
        return self._result


class TestPrescriptionAgent:
    def test_fake_vision_client_satisfies_the_port(self) -> None:
        assert isinstance(FakeVisionClient(result={}), PrescriptionVisionPort)

    @pytest.mark.asyncio
    async def test_returns_vision_client_result_unchanged(self) -> None:
        expected = {
            "drugs": [
                {
                    "farmaco": "Ibuprofeno",
                    "dosificacion": "600 mg",
                    "frecuencia": "cada 8 horas",
                    "duracion": "5 días",
                }
            ],
            "advertencias": ["No administrar con el estómago vacío."],
        }
        vision_client = FakeVisionClient(result=expected)
        agent = PrescriptionAgent(vision_client=vision_client)

        result = await agent.extract_prescription(b"fake-image-bytes")

        assert result == expected

    @pytest.mark.asyncio
    async def test_forwards_image_bytes_and_default_mime_type(self) -> None:
        vision_client = FakeVisionClient(result={"drugs": [], "advertencias": []})
        agent = PrescriptionAgent(vision_client=vision_client)

        await agent.extract_prescription(b"raw-bytes")

        assert vision_client.received_calls == [(b"raw-bytes", "image/jpeg")]

    @pytest.mark.asyncio
    async def test_forwards_explicit_mime_type(self) -> None:
        vision_client = FakeVisionClient(result={"drugs": [], "advertencias": []})
        agent = PrescriptionAgent(vision_client=vision_client)

        await agent.extract_prescription(b"raw-bytes", mime_type="image/png")

        assert vision_client.received_calls == [(b"raw-bytes", "image/png")]

    @pytest.mark.asyncio
    async def test_delegates_to_mock_vision_client(self) -> None:
        mock_vision_client = AsyncMock(spec=PrescriptionVisionPort)
        mock_vision_client.analyze_prescription_image.return_value = {
            "drugs": [],
            "advertencias": [],
        }
        agent = PrescriptionAgent(vision_client=mock_vision_client)

        await agent.extract_prescription(b"img", mime_type="application/pdf")

        mock_vision_client.analyze_prescription_image.assert_awaited_once_with(
            b"img", mime_type="application/pdf"
        )
