"""Script de ingesta masiva: busca en CIMA e indexa localmente los fármacos más consultados.

Para cada término de `SEARCH_TERMS`, busca en CIMA y ejecuta
`DrugService.fetch_and_index_drug` sobre los `TOP_N_PER_TERM` primeros resultados,
generando su embedding (Ollama) y persistiéndolos en la caché local (Postgres/pgvector).

Uso (desde la raíz del proyecto, para que `src` sea importable): python -m scripts.ingest_drugs
"""

from __future__ import annotations

import asyncio

from src.application.services import DrugService
from src.infrastructure.database import AsyncSessionFactory
from src.infrastructure.external.cima_client import CimaAPIClient
from src.infrastructure.external.ollama_client import OllamaClient
from src.infrastructure.repositories import DrugRepository

SEARCH_TERMS = ["ibuprofeno", "paracetamol", "amoxicilina", "omeprazol"]
TOP_N_PER_TERM = 3


async def ingest_top_drugs() -> None:
    """Busca `SEARCH_TERMS` en CIMA e indexa los `TOP_N_PER_TERM` primeros resultados de cada uno."""
    procesados = 0
    indexados = 0

    async with (
        CimaAPIClient() as cima_client,
        OllamaClient() as ollama_client,
        AsyncSessionFactory() as session,
    ):
        drug_repo = DrugRepository(session)
        drug_service = DrugService(
            cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
        )

        for termino in SEARCH_TERMS:
            print(f"\nBuscando '{termino}' en CIMA...")
            resultados = await cima_client.search_medicamentos(termino)
            print(
                f"  {len(resultados)} resultados encontrados. Indexando los {TOP_N_PER_TERM} primeros..."
            )

            for medicamento in resultados[:TOP_N_PER_TERM]:
                nregistro = medicamento["nregistro"]
                nombre = medicamento.get("nombre", nregistro)
                procesados += 1

                try:
                    drug = await drug_service.fetch_and_index_drug(nregistro)
                except Exception as exc:  # noqa: BLE001 — un fallo puntual no debe abortar el resto del lote
                    print(f"  [ERROR] {nombre} (nregistro={nregistro}): {exc}")
                    continue

                if drug is not None:
                    indexados += 1
                    print(f"  [OK] {nombre} (nregistro={nregistro}) indexado.")
                else:
                    print(
                        f"  [FALLO] {nombre} (nregistro={nregistro}) no se pudo indexar."
                    )

    print(
        f"\nIngesta finalizada: {indexados}/{procesados} fármacos indexados con éxito."
    )


if __name__ == "__main__":
    asyncio.run(ingest_top_drugs())
