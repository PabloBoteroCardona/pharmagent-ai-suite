"""Servicio de aplicación: ingesta e indexación semántica de fármacos.

Orquesta CIMA (fuente primaria en vivo — ficha, ficha técnica y prospecto), Ollama
(embeddings locales) y PostgreSQL/pgvector (caché semántica), según la decisión de
arquitectura en [DECISIONS.md](../../../.memory/DECISIONS.md).

`search_drugs_semantic` consulta primero la caché vectorial (rápido, sin red externa) y,
si no hay resultados, cae automáticamente a una búsqueda en vivo en CIMA usando `query`
como nombre de fármaco — a diferencia del orden "CIMA en vivo primero" descrito en el
diseño original de SKILLS.md, se prioriza la caché por rendimiento (evita un round-trip a
CIMA en cada consulta de un fármaco ya conocido) sin sacrificar corrección: si la caché no
tiene el dato, CIMA en vivo sigue siendo la fuente de verdad consultada antes de devolver
una respuesta vacía. El resultado de la búsqueda en vivo se indexa automáticamente, así que
consultas futuras sobre el mismo fármaco son instantáneas. Esto solo funciona cuando
`query` es (o contiene) un nombre reconocible por la búsqueda de CIMA (coincidencia por
nombre, no semántica) — una pregunta en lenguaje natural sin nombre de fármaco identificable
seguirá sin encontrar nada en el paso de CIMA en vivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.ports import CimaDataSourcePort, DrugRepositoryPort, LanguageModelPort
from src.infrastructure.models import DrugModel

# Al caer al respaldo de CIMA en vivo (caché sin resultados), se indexan como máximo
# estos fármacos aunque `limit` sea mayor — cada uno implica 3 llamadas HTTP a CIMA
# (ficha, ficha técnica, prospecto) + 1 a Ollama (embedding) + 1 escritura en Postgres,
# secuenciales; limitarlo mantiene la latencia de una búsqueda "en frío" razonable (mismo
# criterio que scripts/ingest_drugs.py, 3 resultados por término).
LIVE_FALLBACK_MAX_RESULTS = 3

# Valores de `tipo` usados tanto en `docSegmentado/contenido/{tipo}` (CimaAPIClient) como
# en el campo `docs[].tipo` del detalle de medicamento — mismos códigos, dos superficies
# distintas de la API de CIMA.
FICHA_TECNICA_DOC_TIPO = 1
PROSPECTO_DOC_TIPO = 2


@dataclass
class DrugSearchResult:
    """Resultado de `search_drugs_semantic`, con la procedencia de los datos."""

    drugs: list[DrugModel] = field(default_factory=list)
    source: str = "none"  # "cache" | "live" | "none"


class DrugService:
    """Orquesta la ingesta, indexación y búsqueda semántica de fármacos.

    Depende únicamente de los puertos de dominio (`src/domain/ports/`), no de las
    clases concretas de infraestructura — cualquier implementación que satisfaga
    estos puertos estructuralmente (p. ej. un `CimaAPIClient` de test) sirve aquí.
    """

    def __init__(
        self,
        cima_client: CimaDataSourcePort,
        ollama_client: LanguageModelPort,
        drug_repo: DrugRepositoryPort,
    ) -> None:
        self._cima_client = cima_client
        self._ollama_client = ollama_client
        self._drug_repo = drug_repo

    async def fetch_and_index_drug(self, nregistro: str) -> DrugModel | None:
        """Consulta un fármaco en CIMA (ficha, ficha técnica y prospecto), genera su
        embedding y lo persiste/actualiza en caché."""
        medicamento = await self._cima_client.get_medicamento_by_nregistro(nregistro)
        if medicamento is None:
            return None

        nombre = medicamento.get("nombre", "")
        pactivos = medicamento.get("pactivos")
        prospecto_html = await self._cima_client.get_prospecto_html(nregistro)
        ficha_tecnica_html = await self._cima_client.get_ficha_tecnica_html(nregistro)

        # El embedding de búsqueda usa solo nombre/principios activos/prospecto — no la
        # ficha técnica — para no alterar la geometría de los embeddings ya calibrada
        # (`MAX_RELEVANT_COSINE_DISTANCE`, ver drug_repository.py). La ficha técnica sí
        # se guarda y se usa como contexto adicional para el LLM en `RAGPharmAgent`.
        texto_para_embedding = "\n".join(
            parte for parte in (nombre, pactivos, prospecto_html) if parte
        )
        embedding = await self._ollama_client.generate_embedding(texto_para_embedding)

        drug_data = {
            "nregistro": nregistro,
            "nombre": nombre,
            "pactivos": pactivos,
            "labtitular": medicamento.get("labtitular"),
            "cpres": medicamento.get("cpresc"),
            "prospecto_html": prospecto_html,
            "ficha_tecnica_html": ficha_tecnica_html,
            "prospecto_url": self._extract_doc_url(medicamento, PROSPECTO_DOC_TIPO),
            "ficha_tecnica_url": self._extract_doc_url(
                medicamento, FICHA_TECNICA_DOC_TIPO
            ),
            "embedding": embedding or None,
        }
        return await self._drug_repo.save_drug(drug_data)

    @staticmethod
    def _extract_doc_url(medicamento: dict, tipo: int) -> str | None:
        """Extrae la URL HTML pública del documento (ficha técnica `tipo=1`, prospecto
        `tipo=2`) del campo `docs` que CIMA ya incluye en el detalle del medicamento —
        evita una llamada de red adicional solo para construir el enlace de referencia."""
        for doc in medicamento.get("docs", []):
            if doc.get("tipo") == tipo:
                return doc.get("urlHtml")
        return None

    async def search_drugs_semantic(
        self, query: str, limit: int = 5
    ) -> DrugSearchResult:
        """Busca fármacos relevantes para `query`: primero en la caché vectorial y, si no
        hay resultados, en vivo en CIMA (ver docstring del módulo)."""
        embedding = await self._ollama_client.generate_embedding(query)
        cached = (
            await self._drug_repo.search_similar_by_vector(embedding, limit=limit)
            if embedding
            else []
        )
        if cached:
            return DrugSearchResult(drugs=cached, source="cache")

        live_drugs = await self._search_and_index_live(
            query, limit=min(limit, LIVE_FALLBACK_MAX_RESULTS)
        )
        if live_drugs:
            return DrugSearchResult(drugs=live_drugs, source="live")

        return DrugSearchResult(drugs=[], source="none")

    async def _search_and_index_live(self, name: str, limit: int) -> list[DrugModel]:
        """Busca `name` en vivo en CIMA y persiste/indexa los primeros `limit` resultados."""
        resultados = await self._cima_client.search_medicamentos(name)

        indexed: list[DrugModel] = []
        for medicamento in resultados[:limit]:
            nregistro = medicamento.get("nregistro")
            if not nregistro:
                continue
            drug = await self.fetch_and_index_drug(nregistro)
            if drug is not None:
                indexed.append(drug)
        return indexed
