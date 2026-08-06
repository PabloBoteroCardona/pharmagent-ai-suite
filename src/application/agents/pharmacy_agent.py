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
    "en el contexto a continuación (nombre, principios activos, ficha técnica y prospecto). "
    "La ficha técnica contiene la información clínica completa para profesionales "
    "sanitarios (posología exacta, farmacocinética, contraindicaciones, interacciones, "
    "efectos adversos) — prefiérela sobre el prospecto para preguntas clínicas o de "
    "dosificación; el prospecto está en lenguaje divulgativo para el paciente. No completes "
    "con conocimiento general no verificado ni inventes datos que no estén en el contexto. "
    "Si el contexto no contiene información suficiente para responder con certeza, indica "
    "explícitamente que no dispones de información verificada y recomienda consultar a un "
    "profesional sanitario o farmacéutico. No emitas diagnósticos ni sustituyas el criterio "
    "médico."
)

NO_CONTEXT_NOTE = (
    "Contexto: no se encontró ningún medicamento relevante ni en la caché local ni en "
    "CIMA (AEMPS) en vivo para esta consulta."
)

# Groq (nivel gratuito, "on_demand") limita a 6000 tokens/minuto — con hasta 3 fármacos de
# contexto (`search_drugs_semantic(..., limit=3)`), una ficha técnica + prospecto sin
# truncar puede sumar 40-60k caracteres *por fármaco*, superando el límite con facilidad y
# degradando a una respuesta vacía sin aviso (verificado: una petición de 22.5k tokens fue
# rechazada por Groq con 413 "Request too large"/`rate_limit_exceeded`). Se trunca cada
# documento a este presupuesto de caracteres — con los 3 fármacos al límite de búsqueda,
# el prompt completo (ficha técnica + prospecto de cada uno, más `SYSTEM_PROMPT`) se queda
# en ~3000-3500 tokens, con margen para la respuesta generada dentro del límite de 6000.
MAX_CHARS_PER_DOCUMENT = 2500
TRUNCATION_MARKER = "\n[…contenido truncado por límite de tamaño…]"


def _truncated(text: str | None) -> str:
    if not text:
        return "no disponible"
    if len(text) <= MAX_CHARS_PER_DOCUMENT:
        return text
    return text[:MAX_CHARS_PER_DOCUMENT] + TRUNCATION_MARKER


class RAGPharmAgent:
    """Agente RAG que responde consultas farmacéuticas: caché semántica primero, CIMA
    en vivo como respaldo automático si la caché no tiene el fármaco."""

    def __init__(
        self, drug_service: DrugService, language_model: LanguageModelPort
    ) -> None:
        self._drug_service = drug_service
        self._language_model = language_model

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
                f"Ficha técnica: {_truncated(drug.ficha_tecnica_html)}\n"
                f"Prospecto: {_truncated(drug.prospecto_html)}"
                for drug in context_drugs
            )
            system_prompt = f"{SYSTEM_PROMPT}\n\n{context}"
        else:
            system_prompt = f"{SYSTEM_PROMPT}\n\n{NO_CONTEXT_NOTE}"

        # `temperature=0.0`: la respuesta cita datos clínicos (dosis, contraindicaciones)
        # extraídos textualmente del contexto — debe ser determinista para la misma
        # pregunta, no variar entre peticiones por muestreo del LLM (mismo razonamiento que
        # `SafetyCheckAgent._check_with_language_model`, ver `.memory/BUGS.md`).
        answer = await self._language_model.generate_completion(
            prompt=query, system=system_prompt, temperature=0.0
        )

        return {
            "query": query,
            "response": answer,
            "sources": [
                {
                    "nombre": drug.nombre,
                    "ficha_tecnica_url": drug.ficha_tecnica_url,
                    "prospecto_url": drug.prospecto_url,
                }
                for drug in context_drugs
            ],
            "source": search_result.source,
        }
