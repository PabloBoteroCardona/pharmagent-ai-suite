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

    @pytest.mark.asyncio
    async def test_does_not_persist_when_no_repository_injected(self) -> None:
        prescription_agent = AsyncMock(spec=PrescriptionAgent)
        prescription_agent.extract_prescription.return_value = {
            "drugs": [{"farmaco": "Ibuprofeno"}],
            "advertencias": [],
        }
        safety_agent = AsyncMock(spec=SafetyCheckAgent)
        use_case = ProcessPrescriptionUseCase(
            prescription_agent=prescription_agent,
            safety_agent=safety_agent,
            record_repository=None,
        )

        result = await use_case.execute(b"fake-bytes")

        assert result["prescription"]["drugs"] == [{"farmaco": "Ibuprofeno"}]

    @pytest.mark.asyncio
    async def test_persists_record_when_repository_injected(self) -> None:
        prescription_agent = AsyncMock(spec=PrescriptionAgent)
        prescription_agent.extract_prescription.return_value = {
            "drugs": [{"farmaco": "Warfarina"}, {"farmaco": "Aspirina"}],
            "advertencias": ["Tomar con alimentos."],
        }
        safety_agent = AsyncMock(spec=SafetyCheckAgent)
        safety_check_result = {
            "interactions": [
                {"primary_drug": "warfarina", "secondary_drug": "aspirina"}
            ],
            "verdict": "requiere_revision_medica",
        }
        safety_agent.check_interactions.return_value = safety_check_result
        record_repository = AsyncMock()
        use_case = ProcessPrescriptionUseCase(
            prescription_agent=prescription_agent,
            safety_agent=safety_agent,
            record_repository=record_repository,
        )

        await use_case.execute(b"fake-bytes", patient_id="paciente-1")

        record_repository.save.assert_awaited_once_with(
            drugs=[{"farmaco": "Warfarina"}, {"farmaco": "Aspirina"}],
            advertencias=["Tomar con alimentos."],
            safety_check=safety_check_result,
            patient_id="paciente-1",
        )

    @pytest.mark.asyncio
    async def test_persists_record_with_none_safety_check_for_single_drug(self) -> None:
        prescription_agent = AsyncMock(spec=PrescriptionAgent)
        prescription_agent.extract_prescription.return_value = {
            "drugs": [{"farmaco": "Ibuprofeno"}],
            "advertencias": [],
        }
        safety_agent = AsyncMock(spec=SafetyCheckAgent)
        record_repository = AsyncMock()
        use_case = ProcessPrescriptionUseCase(
            prescription_agent=prescription_agent,
            safety_agent=safety_agent,
            record_repository=record_repository,
        )

        await use_case.execute(b"fake-bytes")

        record_repository.save.assert_awaited_once_with(
            drugs=[{"farmaco": "Ibuprofeno"}],
            advertencias=[],
            safety_check=None,
            patient_id=None,
        )
