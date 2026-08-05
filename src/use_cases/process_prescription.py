"""Caso de uso: flujo completo receta → extracción → verificación de interacciones.

Orquesta `PrescriptionAgent` (extracción multimodal) y `SafetyCheckAgent` (interacciones
conocidas) en una única operación — el flujo natural que motiva tener ambos agentes, pero
que hasta ahora solo existía como dos endpoints aislados (`/analyze-prescription` y
`/check-interactions`, invocados por separado). Ver [AGENTS.md](../../AGENTS.md) para el
contrato de cada agente por separado.

Regla de negocio: la verificación de interacciones solo tiene sentido con 2+ fármacos
(ver guardrail de `check_drug_interactions` en [SKILLS.md](../../SKILLS.md#2-check_drug_interactions))
— con 0 o 1 fármaco extraído, se omite y `safety_check` queda en `None`.
"""

from __future__ import annotations

from src.application.agents.prescription_agent import PrescriptionAgent
from src.application.agents.safety_agent import SafetyCheckAgent

MIN_DRUGS_FOR_INTERACTION_CHECK = 2


class ProcessPrescriptionUseCase:
    """Extrae los fármacos de una imagen de receta y verifica sus interacciones."""

    def __init__(
        self, prescription_agent: PrescriptionAgent, safety_agent: SafetyCheckAgent
    ) -> None:
        self._prescription_agent = prescription_agent
        self._safety_agent = safety_agent

    async def execute(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
        """Devuelve `{"prescription": {...}, "safety_check": {...} | None}`."""
        prescription = await self._prescription_agent.extract_prescription(
            image_bytes, mime_type=mime_type
        )
        drug_names = [
            drug["farmaco"]
            for drug in prescription.get("drugs", [])
            if drug.get("farmaco")
        ]

        safety_check = None
        if len(drug_names) >= MIN_DRUGS_FOR_INTERACTION_CHECK:
            safety_check = await self._safety_agent.check_interactions(drug_names)

        return {"prescription": prescription, "safety_check": safety_check}
