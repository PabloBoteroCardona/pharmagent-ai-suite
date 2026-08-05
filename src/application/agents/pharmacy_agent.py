"""Agente RAG farmacéutico: responde consultas grounded en fármacos, con CIMA en vivo
como respaldo cuando la caché semántica no tiene el dato.

Ver [AGENTS.md](../../../AGENTS.md#3-ragpharmagent) y
[SKILLS.md](../../../SKILLS.md#3-search_cima_official_data) para el contrato de
comportamiento de este agente (fuente primaria CIMA + caché `pgvector`, respuesta grounded).
"""

from __future__ import annotations

from src.application.services.drug_service import DrugService
from src.domain.ports import LanguageModelPort

SYSTEM_PROMPT = (
    "Eres un asistente farmacéutico que responde consultas sobre medicamentos autorizados "
    "en España (AEMPS/CIMA). Responde ÚNICAMENTE con la información técnica proporcionada "
    "en el contexto a continuación (nombre, principios activos y secciones del prospecto). "
    "No completes con conocimiento general no verificado ni inventes datos que no estén en "
    "el contexto. Si el contexto no contiene información suficiente para responder con "
    "certeza, indica explícitamente que no dispones de información verificada y recomienda "
    "consultar a un profesional sanitario o farmacéutico. No emitas diagnósticos ni "
    "sustituyas el criterio médico."
)

NO_CONTEXT_NOTE = (
    "Contexto: no se encontró ningún medicamento relevante ni en la caché local ni en "
    "CIMA (AEMPS) en vivo para esta consulta."
)


class RAGPharmAgent:
    """Agente RAG que responde consultas farmacéuticas: caché semántica primero, CIMA
    en vivo como respaldo automático si la caché no tiene el fármaco."""

    def __init__(
        self, drug_service: DrugService, ollama_client: LanguageModelPort
    ) -> None:
        self._drug_service = drug_service
        self._ollama_client = ollama_client

    async def answer_consultation(
        self, query: str, drug_name: str | None = None
    ) -> dict:
        """Responde `query` basándose en los fármacos más relevantes de la caché o, si no
        hay ninguno, en una búsqueda en vivo en CIMA.

        `drug_name`, si se proporciona, se usa como término de búsqueda (en vez de
        `query`) tanto para la caché como para CIMA en vivo — CIMA solo hace
        coincidencia por nombre, no búsqueda semántica, así que una pregunta en lenguaje
        natural (p. ej. "¿qué dosis de ibuprofeno es adecuada?") no siempre encuentra el
        fármaco en CIMA salvo que se indique su nombre explícitamente.
        """
        search_term = drug_name or query
        search_result = await self._drug_service.search_drugs_semantic(
            search_term, limit=3
        )
        context_drugs = search_result.drugs

        if context_drugs:
            context = "\n\n".join(
                f"Medicamento: {drug.nombre}\n"
                f"Principios activos: {drug.pactivos or 'no disponible'}\n"
                f"Prospecto: {drug.documento_html or 'no disponible'}"
                for drug in context_drugs
            )
            system_prompt = f"{SYSTEM_PROMPT}\n\n{context}"
        else:
            system_prompt = f"{SYSTEM_PROMPT}\n\n{NO_CONTEXT_NOTE}"

        answer = await self._ollama_client.generate_completion(
            prompt=query, system=system_prompt
        )

        return {
            "query": query,
            "response": answer,
            "sources": [drug.nombre for drug in context_drugs],
            "source": search_result.source,
        }
