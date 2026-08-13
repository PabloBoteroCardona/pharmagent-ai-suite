"""Caso de uso: flujo completo receta → extracción → verificación de interacciones.

Orquesta `PrescriptionAgent` (extracción multimodal) y `SafetyCheckAgent` (interacciones
conocidas) en una única operación — el flujo natural que motiva tener ambos agentes, pero
que hasta ahora solo existía como dos endpoints aislados (`/analyze-prescription` y
`/check-interactions`, invocados por separado). Ver [AGENTES.md](../../docs/AGENTES.md) para el
contrato de cada agente por separado.

Regla de negocio: la verificación de interacciones solo tiene sentido con 2+ fármacos
(ver guardrail de `check_drug_interactions` en [HERRAMIENTAS.md](../../docs/HERRAMIENTAS.md#2-check_drug_interactions))
— con 0 o 1 fármaco extraído, se omite y `safety_check` queda en `None`.

Persistencia: si se inyecta un `PrescriptionRecordRepositoryPort`, el resultado se guarda
como registro auditable (ver
[prescription_record_model.py](../infrastructure/models/prescription_record_model.py) para
la decisión de no mapear directamente a la entidad de dominio `Prescription`). Es opcional
(`None` por defecto) para no forzar una dependencia de base de datos en contextos que no la
necesiten (p. ej. tests unitarios).
"""

from __future__ import annotations

from src.application.agents.prescription_agent import PrescriptionAgent
from src.application.agents.safety_agent import SafetyCheckAgent
from src.domain.ports import PrescriptionRecordRepositoryPort

MIN_DRUGS_FOR_INTERACTION_CHECK = 2


class ProcessPrescriptionUseCase:
    """Extrae los fármacos de una imagen de receta, verifica sus interacciones y,
    opcionalmente, persiste el resultado como registro auditable."""

    def __init__(
        self,
        prescription_agent: PrescriptionAgent,
        safety_agent: SafetyCheckAgent,
        record_repository: PrescriptionRecordRepositoryPort | None = None,
    ) -> None:
        self._prescription_agent = prescription_agent
        self._safety_agent = safety_agent
        self._record_repository = record_repository

    async def execute(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        patient_id: str | None = None,
    ) -> dict:
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

        if self._record_repository is not None:
            await self._record_repository.save(
                drugs=prescription.get("drugs", []),
                advertencias=prescription.get("advertencias", []),
                safety_check=safety_check,
                patient_id=patient_id,
            )

        return {"prescription": prescription, "safety_check": safety_check}
