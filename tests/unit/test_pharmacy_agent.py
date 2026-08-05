"""Tests unitarios de `RAGPharmAgent.answer_consultation`, con `DrugService` mockeado."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.agents.pharmacy_agent import RAGPharmAgent
from src.application.services.drug_service import DrugSearchResult
from src.domain.ports import LanguageModelPort

FAKE_DRUG = SimpleNamespace(
    nombre="Ibuprofeno 600mg",
    pactivos="ibuprofeno",
    documento_html="Indicado para el dolor.",
)


def _make_drug_service(search_result: DrugSearchResult) -> AsyncMock:
    drug_service = AsyncMock()
    drug_service.search_drugs_semantic.return_value = search_result
    return drug_service


class TestAnswerConsultation:
    @pytest.mark.asyncio
    async def test_uses_query_as_search_term_by_default(self) -> None:
        drug_service = _make_drug_service(
            DrugSearchResult(drugs=[FAKE_DRUG], source="cache")
        )
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, ollama_client=ollama_client)

        await agent.answer_consultation("¿dosis de ibuprofeno?")

        drug_service.search_drugs_semantic.assert_awaited_once_with(
            "¿dosis de ibuprofeno?", limit=3
        )

    @pytest.mark.asyncio
    async def test_uses_drug_name_as_search_term_when_provided(self) -> None:
        drug_service = _make_drug_service(
            DrugSearchResult(drugs=[FAKE_DRUG], source="live")
        )
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, ollama_client=ollama_client)

        await agent.answer_consultation(
            "¿qué dosis es adecuada?", drug_name="ibuprofeno"
        )

        drug_service.search_drugs_semantic.assert_awaited_once_with(
            "ibuprofeno", limit=3
        )

    @pytest.mark.asyncio
    async def test_response_includes_source_from_drug_service(self) -> None:
        drug_service = _make_drug_service(
            DrugSearchResult(drugs=[FAKE_DRUG], source="live")
        )
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, ollama_client=ollama_client)

        result = await agent.answer_consultation("consulta")

        assert result["source"] == "live"
        assert result["sources"] == [FAKE_DRUG.nombre]

    @pytest.mark.asyncio
    async def test_no_results_produces_none_source_and_no_context_note(self) -> None:
        drug_service = _make_drug_service(DrugSearchResult(drugs=[], source="none"))
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_completion.return_value = "sin informacion verificada"
        agent = RAGPharmAgent(drug_service=drug_service, ollama_client=ollama_client)

        result = await agent.answer_consultation("consulta")

        assert result["source"] == "none"
        assert result["sources"] == []
        system_prompt_used = ollama_client.generate_completion.call_args.kwargs[
            "system"
        ]
        assert "no se encontró ningún medicamento" in system_prompt_used

    @pytest.mark.asyncio
    async def test_original_query_is_always_sent_to_the_model_not_drug_name(
        self,
    ) -> None:
        """`drug_name` acota la búsqueda de contexto, pero la pregunta real del
        usuario (`query`) es la que se le pasa al LLM para generar la respuesta."""
        drug_service = _make_drug_service(
            DrugSearchResult(drugs=[FAKE_DRUG], source="live")
        )
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, ollama_client=ollama_client)

        await agent.answer_consultation(
            "¿qué dosis es adecuada?", drug_name="ibuprofeno"
        )

        ollama_client.generate_completion.assert_awaited_once()
        assert (
            ollama_client.generate_completion.call_args.kwargs["prompt"]
            == "¿qué dosis es adecuada?"
        )
