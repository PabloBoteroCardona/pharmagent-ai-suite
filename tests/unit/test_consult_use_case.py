"""Tests unitarios de `ConsultDrugRAGUseCase`, con un `RAGPharmAgent` mockeado."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.application.agents.pharmacy_agent import RAGPharmAgent
from src.use_cases.consult_drug_rag import ConsultDrugRAGUseCase


class TestConsultDrugRAGUseCase:
    @pytest.mark.asyncio
    async def test_delegates_query_to_rag_agent(self) -> None:
        rag_agent = AsyncMock(spec=RAGPharmAgent)
        rag_agent.answer_consultation.return_value = {
            "query": "¿qué dosis de ibuprofeno es adecuada?",
            "response": "La dosis habitual en adultos es de 400-600 mg cada 8 horas.",
            "sources": ["Ibuprofeno 600mg"],
        }
        use_case = ConsultDrugRAGUseCase(rag_agent=rag_agent)

        result = await use_case.execute("¿qué dosis de ibuprofeno es adecuada?")

        rag_agent.answer_consultation.assert_awaited_once_with(
            "¿qué dosis de ibuprofeno es adecuada?"
        )
        assert result["response"].startswith("La dosis habitual")
        assert result["sources"] == ["Ibuprofeno 600mg"]

    @pytest.mark.asyncio
    async def test_returns_rag_agent_result_unchanged(self) -> None:
        expected = {"query": "consulta", "response": "", "sources": []}
        rag_agent = AsyncMock(spec=RAGPharmAgent)
        rag_agent.answer_consultation.return_value = expected
        use_case = ConsultDrugRAGUseCase(rag_agent=rag_agent)

        result = await use_case.execute("consulta")

        assert result == expected
