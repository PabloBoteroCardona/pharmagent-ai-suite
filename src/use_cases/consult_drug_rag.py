"""Caso de uso: consulta en lenguaje natural sobre fármacos vía RAG.

Punto de entrada explícito e independiente del transporte (FastAPI, CLI, otro
agente...) para la consulta RAG — la capa de interfaz (`src/infrastructure/api/`)
depende de este caso de uso, nunca directamente de `RAGPharmAgent`.
"""

from __future__ import annotations

from src.application.agents.pharmacy_agent import RAGPharmAgent


class ConsultDrugRAGUseCase:
    """Orquesta la consulta en lenguaje natural sobre fármacos a través de `RAGPharmAgent`."""

    def __init__(self, rag_agent: RAGPharmAgent) -> None:
        self._rag_agent = rag_agent

    async def execute(self, query: str, drug_name: str | None = None) -> dict:
        """Ejecuta la consulta y devuelve `{"query", "response", "sources", "source"}`."""
        return await self._rag_agent.answer_consultation(query, drug_name=drug_name)
