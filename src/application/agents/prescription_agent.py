"""Agente de extracción de recetas: orquesta la visión multimodal de `GeminiClient`.

Ver [AGENTS.md](../../../AGENTS.md#1-prescriptionagent) para el contrato de
comportamiento (nunca inventar datos ilegibles, `GOOGLE_API_KEY` exclusiva para este
flujo).
"""

from __future__ import annotations

from src.domain.ports import PrescriptionVisionPort


class PrescriptionAgent:
    """Agente que extrae fármacos, posología y advertencias de una imagen de receta."""

    def __init__(self, vision_client: PrescriptionVisionPort) -> None:
        self._vision_client = vision_client

    async def extract_prescription(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> dict:
        """Analiza `image_bytes` y devuelve `{"drugs": [...], "advertencias": [...]}`."""
        return await self._vision_client.analyze_prescription_image(
            image_bytes, mime_type=mime_type
        )
