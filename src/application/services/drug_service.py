"""Servicio de aplicación: ingesta e indexación semántica de fármacos.

Orquesta CIMA (fuente primaria en vivo), Ollama (embeddings locales) y
PostgreSQL/pgvector (caché semántica), según la decisión de arquitectura en
[DECISIONS.md](../../../.memory/DECISIONS.md).
"""

from __future__ import annotations

from src.infrastructure.external.cima_client import CimaAPIClient
from src.infrastructure.external.ollama_client import OllamaClient
from src.infrastructure.models import DrugModel
from src.infrastructure.repositories import DrugRepository


class DrugService:
    """Orquesta la ingesta, indexación y búsqueda semántica de fármacos."""

    def __init__(
        self,
        cima_client: CimaAPIClient,
        ollama_client: OllamaClient,
        drug_repo: DrugRepository,
    ) -> None:
        self._cima_client = cima_client
        self._ollama_client = ollama_client
        self._drug_repo = drug_repo

    async def fetch_and_index_drug(self, nregistro: str) -> DrugModel | None:
        """Consulta un fármaco en CIMA, genera su embedding y lo persiste/actualiza en caché."""
        medicamento = await self._cima_client.get_medicamento_by_nregistro(nregistro)
        if medicamento is None:
            return None

        nombre = medicamento.get("nombre", "")
        pactivos = medicamento.get("pactivos")
        secciones_html = await self._cima_client.get_prospecto_html(nregistro)

        texto_para_embedding = "\n".join(
            parte for parte in (nombre, pactivos, secciones_html) if parte
        )
        embedding = await self._ollama_client.generate_embedding(texto_para_embedding)

        drug_data = {
            "nregistro": nregistro,
            "nombre": nombre,
            "pactivos": pactivos,
            "labtitular": medicamento.get("labtitular"),
            "cpres": medicamento.get("cpresc"),
            "documento_html": secciones_html,
            "embedding": embedding or None,
        }
        return await self._drug_repo.save_drug(drug_data)

    async def search_drugs_semantic(
        self, query: str, limit: int = 5
    ) -> list[DrugModel]:
        """Busca los fármacos cacheados semánticamente más similares a `query`."""
        embedding = await self._ollama_client.generate_embedding(query)
        if not embedding:
            return []
        return await self._drug_repo.search_similar_by_vector(embedding, limit=limit)
