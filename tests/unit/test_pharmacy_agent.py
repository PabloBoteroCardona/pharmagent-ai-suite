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
    prospecto_html="Indicado para el dolor.",
    ficha_tecnica_html="Posología: 400-600 mg cada 8 horas.",
    ficha_tecnica_url="https://cima.aemps.es/cima/dochtml/ft/12345/FT_12345.html",
    prospecto_url="https://cima.aemps.es/cima/dochtml/p/12345/P_12345.html",
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
        language_model = AsyncMock(spec=LanguageModelPort)
        language_model.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, language_model=language_model)

        await agent.answer_consultation("¿dosis de ibuprofeno?")

        drug_service.search_drugs_semantic.assert_awaited_once_with(
            "¿dosis de ibuprofeno?", limit=3
        )

    @pytest.mark.asyncio
    async def test_uses_drug_name_as_search_term_when_provided(self) -> None:
        drug_service = _make_drug_service(
            DrugSearchResult(drugs=[FAKE_DRUG], source="live")
        )
        language_model = AsyncMock(spec=LanguageModelPort)
        language_model.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, language_model=language_model)

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
        language_model = AsyncMock(spec=LanguageModelPort)
        language_model.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, language_model=language_model)

        result = await agent.answer_consultation("consulta")

        assert result["source"] == "live"
        assert result["sources"] == [
            {
                "nombre": FAKE_DRUG.nombre,
                "ficha_tecnica_url": FAKE_DRUG.ficha_tecnica_url,
                "prospecto_url": FAKE_DRUG.prospecto_url,
            }
        ]

    @pytest.mark.asyncio
    async def test_system_prompt_includes_ficha_tecnica_and_prospecto(self) -> None:
        """Regresión: la respuesta era demasiado básica porque el contexto solo incluía
        el prospecto (lenguaje divulgativo), nunca la ficha técnica (información clínica
        completa) — reportado por el usuario. Ambas deben llegar al prompt del LLM."""
        drug_service = _make_drug_service(
            DrugSearchResult(drugs=[FAKE_DRUG], source="cache")
        )
        language_model = AsyncMock(spec=LanguageModelPort)
        language_model.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, language_model=language_model)

        await agent.answer_consultation("¿qué dosis es adecuada?")

        system_prompt_used = language_model.generate_completion.call_args.kwargs[
            "system"
        ]
        assert FAKE_DRUG.ficha_tecnica_html in system_prompt_used
        assert FAKE_DRUG.prospecto_html in system_prompt_used

    @pytest.mark.asyncio
    async def test_truncates_oversized_documents_to_avoid_groq_rate_limit(self) -> None:
        """Regresión real: con los 3 fármacos del límite de búsqueda y ficha técnica +
        prospecto sin truncar (40-60k caracteres cada uno en la práctica), el prompt
        superaba el límite de 6000 tokens/minuto de Groq (nivel gratuito) y Groq
        rechazaba la petición — la respuesta llegaba vacía sin ningún aviso. Verificado
        contra la API real de Groq: una petición de ~22.5k tokens fue rechazada con 413
        `rate_limit_exceeded`."""
        oversized_drug = SimpleNamespace(
            nombre="Fármaco con documentos enormes",
            pactivos="principio activo",
            ficha_tecnica_html="F" * 50_000,
            prospecto_html="P" * 50_000,
            ficha_tecnica_url=None,
            prospecto_url=None,
        )
        drug_service = _make_drug_service(
            DrugSearchResult(
                drugs=[oversized_drug, oversized_drug, oversized_drug], source="cache"
            )
        )
        language_model = AsyncMock(spec=LanguageModelPort)
        language_model.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, language_model=language_model)

        await agent.answer_consultation("¿qué es esto?")

        system_prompt_used = language_model.generate_completion.call_args.kwargs[
            "system"
        ]
        # Sin truncar, el prompt tendría >300000 caracteres (3 fármacos x 100000
        # caracteres de documentos); acotado a MAX_CHARS_PER_DOCUMENT por documento debe
        # quedarse muy por debajo — el margen incluye SYSTEM_PROMPT y las etiquetas por
        # fármaco, no solo los documentos.
        assert len(system_prompt_used) < 25_000
        assert "…contenido truncado por límite de tamaño…" in system_prompt_used

    @pytest.mark.asyncio
    async def test_no_results_produces_none_source_and_no_context_note(self) -> None:
        drug_service = _make_drug_service(DrugSearchResult(drugs=[], source="none"))
        language_model = AsyncMock(spec=LanguageModelPort)
        language_model.generate_completion.return_value = "sin informacion verificada"
        agent = RAGPharmAgent(drug_service=drug_service, language_model=language_model)

        result = await agent.answer_consultation("consulta")

        assert result["source"] == "none"
        assert result["sources"] == []
        system_prompt_used = language_model.generate_completion.call_args.kwargs[
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
        language_model = AsyncMock(spec=LanguageModelPort)
        language_model.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, language_model=language_model)

        await agent.answer_consultation(
            "¿qué dosis es adecuada?", drug_name="ibuprofeno"
        )

        language_model.generate_completion.assert_awaited_once()
        assert (
            language_model.generate_completion.call_args.kwargs["prompt"]
            == "¿qué dosis es adecuada?"
        )

    @pytest.mark.asyncio
    async def test_requests_deterministic_output_from_language_model(self) -> None:
        """Regresión: sin `temperature=0.0`, la misma pregunta sobre datos clínicos
        (dosis, contraindicaciones) podía generar respuestas distintas entre peticiones por
        muestreo del LLM — mismo problema real de producción detectado en
        `SafetyCheckAgent`, aplicable aquí por el mismo motivo."""
        drug_service = _make_drug_service(
            DrugSearchResult(drugs=[FAKE_DRUG], source="cache")
        )
        language_model = AsyncMock(spec=LanguageModelPort)
        language_model.generate_completion.return_value = "respuesta"
        agent = RAGPharmAgent(drug_service=drug_service, language_model=language_model)

        await agent.answer_consultation("¿qué dosis es adecuada?")

        assert language_model.generate_completion.call_args.kwargs["temperature"] == 0.0
