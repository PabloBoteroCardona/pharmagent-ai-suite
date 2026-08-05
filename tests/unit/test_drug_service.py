"""Tests unitarios de `DrugService.search_drugs_semantic`: caché primero, CIMA en vivo
como respaldo automático cuando la caché no tiene el fármaco."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.application.services.drug_service import DrugService
from src.domain.ports import CimaDataSourcePort, DrugRepositoryPort, LanguageModelPort


def _make_service(
    cima_client: CimaDataSourcePort | None = None,
    ollama_client: LanguageModelPort | None = None,
    drug_repo: DrugRepositoryPort | None = None,
) -> DrugService:
    return DrugService(
        cima_client=cima_client or AsyncMock(spec=CimaDataSourcePort),
        ollama_client=ollama_client or AsyncMock(spec=LanguageModelPort),
        drug_repo=drug_repo or AsyncMock(spec=DrugRepositoryPort),
    )


class TestSearchDrugsSemanticCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_results_without_touching_cima(self) -> None:
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = [0.1, 0.2]
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.search_similar_by_vector.return_value = ["cached-drug"]
        cima_client = AsyncMock(spec=CimaDataSourcePort)
        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        result = await service.search_drugs_semantic("ibuprofeno")

        assert result.source == "cache"
        assert result.drugs == ["cached-drug"]
        cima_client.search_medicamentos.assert_not_called()


class TestSearchDrugsSemanticLiveFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_cima_when_cache_is_empty(self) -> None:
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = [0.1, 0.2]
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.search_similar_by_vector.return_value = []
        drug_repo.get_by_nregistro.return_value = None
        drug_repo.save_drug.return_value = "indexed-drug"

        cima_client = AsyncMock(spec=CimaDataSourcePort)
        cima_client.search_medicamentos.return_value = [
            {"nregistro": "111", "nombre": "Paracetamol 1g"}
        ]
        cima_client.get_medicamento_by_nregistro.return_value = {
            "nregistro": "111",
            "nombre": "Paracetamol 1g",
            "pactivos": "paracetamol",
        }
        cima_client.get_prospecto_html.return_value = "prospecto"
        cima_client.get_ficha_tecnica_html.return_value = "ficha tecnica"

        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        result = await service.search_drugs_semantic("paracetamol")

        assert result.source == "live"
        assert result.drugs == ["indexed-drug"]
        cima_client.search_medicamentos.assert_awaited_once_with("paracetamol")
        drug_repo.save_drug.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_source_when_cima_also_finds_nothing(self) -> None:
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = [0.1, 0.2]
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.search_similar_by_vector.return_value = []

        cima_client = AsyncMock(spec=CimaDataSourcePort)
        cima_client.search_medicamentos.return_value = []

        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        result = await service.search_drugs_semantic("farmacoinexistente")

        assert result.source == "none"
        assert result.drugs == []

    @pytest.mark.asyncio
    async def test_falls_back_to_cima_when_embedding_generation_fails(self) -> None:
        """Sin embedding no se puede consultar pgvector — debe caer directamente al
        respaldo de CIMA en vez de fallar."""
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = []
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.get_by_nregistro.return_value = None
        drug_repo.save_drug.return_value = "indexed-drug"

        cima_client = AsyncMock(spec=CimaDataSourcePort)
        cima_client.search_medicamentos.return_value = [
            {"nregistro": "111", "nombre": "Paracetamol 1g"}
        ]
        cima_client.get_medicamento_by_nregistro.return_value = {
            "nregistro": "111",
            "nombre": "Paracetamol 1g",
        }
        cima_client.get_prospecto_html.return_value = None
        cima_client.get_ficha_tecnica_html.return_value = None

        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        result = await service.search_drugs_semantic("paracetamol")

        assert result.source == "live"
        drug_repo.search_similar_by_vector.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_limit_on_live_fallback(self) -> None:
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = [0.1]
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.search_similar_by_vector.return_value = []
        drug_repo.get_by_nregistro.return_value = None
        drug_repo.save_drug.side_effect = lambda data: data["nregistro"]

        cima_client = AsyncMock(spec=CimaDataSourcePort)
        cima_client.search_medicamentos.return_value = [
            {"nregistro": str(i), "nombre": f"Farmaco {i}"} for i in range(10)
        ]
        cima_client.get_medicamento_by_nregistro.side_effect = lambda nregistro: {
            "nregistro": nregistro,
            "nombre": f"Farmaco {nregistro}",
        }
        cima_client.get_prospecto_html.return_value = None
        cima_client.get_ficha_tecnica_html.return_value = None

        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        result = await service.search_drugs_semantic("farmaco", limit=1)

        # LIVE_FALLBACK_MAX_RESULTS=3, pero limit=1 debe ganar (min de ambos).
        assert len(result.drugs) == 1

    @pytest.mark.asyncio
    async def test_skips_cima_results_without_nregistro(self) -> None:
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = [0.1]
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.search_similar_by_vector.return_value = []

        cima_client = AsyncMock(spec=CimaDataSourcePort)
        cima_client.search_medicamentos.return_value = [{"nombre": "Sin registro"}]

        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        result = await service.search_drugs_semantic("algo")

        assert result.source == "none"
        cima_client.get_medicamento_by_nregistro.assert_not_called()


class TestFetchAndIndexDrug:
    @pytest.mark.asyncio
    async def test_builds_drug_data_with_ficha_tecnica_and_document_urls(self) -> None:
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = [0.1, 0.2]
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.get_by_nregistro.return_value = None

        cima_client = AsyncMock(spec=CimaDataSourcePort)
        cima_client.get_medicamento_by_nregistro.return_value = {
            "nregistro": "83348",
            "nombre": "Naproxeno 600mg",
            "pactivos": "NAPROXENO SODICO",
            "labtitular": "Bayer",
            "cpresc": "Sin Receta",
            "docs": [
                {
                    "tipo": 1,
                    "urlHtml": "https://cima.aemps.es/cima/dochtml/ft/83348/FT_83348.html",
                },
                {
                    "tipo": 2,
                    "urlHtml": "https://cima.aemps.es/cima/dochtml/p/83348/P_83348.html",
                },
            ],
        }
        cima_client.get_prospecto_html.return_value = "contenido del prospecto"
        cima_client.get_ficha_tecnica_html.return_value = (
            "contenido de la ficha técnica"
        )

        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        await service.fetch_and_index_drug("83348")

        drug_data = drug_repo.save_drug.call_args.args[0]
        assert drug_data["prospecto_html"] == "contenido del prospecto"
        assert drug_data["ficha_tecnica_html"] == "contenido de la ficha técnica"
        assert (
            drug_data["ficha_tecnica_url"]
            == "https://cima.aemps.es/cima/dochtml/ft/83348/FT_83348.html"
        )
        assert (
            drug_data["prospecto_url"]
            == "https://cima.aemps.es/cima/dochtml/p/83348/P_83348.html"
        )

    @pytest.mark.asyncio
    async def test_embedding_text_excludes_ficha_tecnica(self) -> None:
        """El embedding de búsqueda no debe incluir la ficha técnica — cambiar su
        composición invalidaría el umbral `MAX_RELEVANT_COSINE_DISTANCE` ya calibrado
        (ver drug_repository.py) frente a los embeddings ya existentes en caché."""
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = [0.1]
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.get_by_nregistro.return_value = None

        cima_client = AsyncMock(spec=CimaDataSourcePort)
        cima_client.get_medicamento_by_nregistro.return_value = {
            "nregistro": "83348",
            "nombre": "Naproxeno 600mg",
            "pactivos": "NAPROXENO SODICO",
        }
        cima_client.get_prospecto_html.return_value = "texto del prospecto"
        cima_client.get_ficha_tecnica_html.return_value = "TEXTO_EXCLUSIVO_DE_LA_FICHA"

        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        await service.fetch_and_index_drug("83348")

        embedding_text = ollama_client.generate_embedding.call_args.args[0]
        assert "texto del prospecto" in embedding_text
        assert "TEXTO_EXCLUSIVO_DE_LA_FICHA" not in embedding_text

    @pytest.mark.asyncio
    async def test_missing_docs_field_yields_none_urls(self) -> None:
        ollama_client = AsyncMock(spec=LanguageModelPort)
        ollama_client.generate_embedding.return_value = [0.1]
        drug_repo = AsyncMock(spec=DrugRepositoryPort)
        drug_repo.get_by_nregistro.return_value = None

        cima_client = AsyncMock(spec=CimaDataSourcePort)
        cima_client.get_medicamento_by_nregistro.return_value = {
            "nregistro": "111",
            "nombre": "Farmaco sin docs",
        }
        cima_client.get_prospecto_html.return_value = None
        cima_client.get_ficha_tecnica_html.return_value = None

        service = _make_service(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        await service.fetch_and_index_drug("111")

        drug_data = drug_repo.save_drug.call_args.args[0]
        assert drug_data["ficha_tecnica_url"] is None
        assert drug_data["prospecto_url"] is None
