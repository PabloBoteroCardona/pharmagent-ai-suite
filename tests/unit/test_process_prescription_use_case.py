"""Tests unitarios de `ProcessPrescriptionUseCase` (orquestación receta→interacciones)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.application.agents.prescription_agent import PrescriptionAgent
from src.application.agents.safety_agent import SafetyCheckAgent
from src.use_cases.process_prescription import ProcessPrescriptionUseCase


class TestProcessPrescriptionUseCase:
    @pytest.mark.asyncio
    async def test_runs_safety_check_when_two_or_more_drugs_extracted(self) -> None:
        prescription_agent = AsyncMock(spec=PrescriptionAgent)
        prescription_agent.extract_prescription.return_value = {
            "drugs": [{"farmaco": "Warfarina"}, {"farmaco": "Aspirina"}],
            "advertencias": [],
        }
        safety_agent = AsyncMock(spec=SafetyCheckAgent)
        safety_agent.check_interactions.return_value = {
            "interactions": [
                {"primary_drug": "warfarina", "secondary_drug": "aspirina"}
            ],
            "verdict": "requiere_revision_medica",
        }
        use_case = ProcessPrescriptionUseCase(
            prescription_agent=prescription_agent, safety_agent=safety_agent
        )

        result = await use_case.execute(b"fake-bytes")

        safety_agent.check_interactions.assert_called_once_with(
            ["Warfarina", "Aspirina"]
        )
        assert result["safety_check"]["verdict"] == "requiere_revision_medica"

    @pytest.mark.asyncio
    async def test_skips_safety_check_with_a_single_drug(self) -> None:
        prescription_agent = AsyncMock(spec=PrescriptionAgent)
        prescription_agent.extract_prescription.return_value = {
            "drugs": [{"farmaco": "Ibuprofeno"}],
            "advertencias": [],
        }
        safety_agent = AsyncMock(spec=SafetyCheckAgent)
        use_case = ProcessPrescriptionUseCase(
            prescription_agent=prescription_agent, safety_agent=safety_agent
        )

        result = await use_case.execute(b"fake-bytes")

        safety_agent.check_interactions.assert_not_called()
        assert result["safety_check"] is None

    @pytest.mark.asyncio
    async def test_skips_safety_check_with_no_drugs(self) -> None:
        prescription_agent = AsyncMock(spec=PrescriptionAgent)
        prescription_agent.extract_prescription.return_value = {
            "drugs": [],
            "advertencias": [],
        }
        safety_agent = AsyncMock(spec=SafetyCheckAgent)
        use_case = ProcessPrescriptionUseCase(
            prescription_agent=prescription_agent, safety_agent=safety_agent
        )

        result = await use_case.execute(b"fake-bytes")

        safety_agent.check_interactions.assert_not_called()
        assert result["prescription"]["drugs"] == []
        assert result["safety_check"] is None

    @pytest.mark.asyncio
    async def test_forwards_image_bytes_and_mime_type(self) -> None:
        prescription_agent = AsyncMock(spec=PrescriptionAgent)
        prescription_agent.extract_prescription.return_value = {
            "drugs": [],
            "advertencias": [],
        }
        safety_agent = AsyncMock(spec=SafetyCheckAgent)
        use_case = ProcessPrescriptionUseCase(
            prescription_agent=prescription_agent, safety_agent=safety_agent
        )

        await use_case.execute(b"raw-bytes", mime_type="image/png")

        prescription_agent.extract_prescription.assert_awaited_once_with(
            b"raw-bytes", mime_type="image/png"
        )

    @pytest.mark.asyncio
    async def test_ignores_drug_entries_without_a_name(self) -> None:
        prescription_agent = AsyncMock(spec=PrescriptionAgent)
        prescription_agent.extract_prescription.return_value = {
            "drugs": [{"farmaco": "Warfarina"}, {"farmaco": None}, {"farmaco": ""}],
            "advertencias": [],
        }
        safety_agent = AsyncMock(spec=SafetyCheckAgent)
        use_case = ProcessPrescriptionUseCase(
            prescription_agent=prescription_agent, safety_agent=safety_agent
        )

        result = await use_case.execute(b"fake-bytes")

        safety_agent.check_interactions.assert_not_called()
        assert result["safety_check"] is None
