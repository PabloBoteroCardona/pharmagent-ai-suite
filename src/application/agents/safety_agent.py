"""Agente de verificación de seguridad: interacciones farmacológicas conocidas.

Ver [AGENTS.md](../../../AGENTS.md#2-safetycheckagent) para el contrato de
comportamiento. Usa la entidad de dominio `DrugInteraction`
([drug_interaction.py](../../domain/models/drug_interaction.py)).

Diseño híbrido: la base curada (`_KNOWN_INTERACTIONS`) es la fuente **autoritativa** —
si cubre la combinación de fármacos dada, su resultado se devuelve tal cual y nunca se
consulta al modelo de lenguaje. Solo cuando ningún par de la base curada aplica, y se ha
inyectado un `LanguageModelPort` (Ollama local, nunca un proveedor externo — ver
[DECISIONS.md](../../../.memory/DECISIONS.md)), el agente consulta al modelo para razonar
sobre combinaciones no cubiertas. La respuesta del modelo nunca puede contradecir ni
sustituir a la base curada, solo complementarla; cada interacción devuelta lleva un campo
`source` (`"curated"` / `"llm"`) para que el consumidor distinga el nivel de confianza. Ante
un fallo de parseo o incertidumbre explícita del modelo, el veredicto por defecto es
`requiere_revision_medica` — nunca una aprobación silenciosa (ver AGENTS.md).

Limitación aceptada: `_KNOWN_INTERACTIONS` es una base curada mínima, con fines
demostrativos (TFM) — no sustituye una base de datos de interacciones clínica completa. El
razonamiento del LLM sobre combinaciones no cubiertas es un mecanismo de asistencia, no una
fuente clínica verificada — no hay *grounding* en una base de datos real para ese camino.
"""

from __future__ import annotations

import json

from src.domain.models.drug_interaction import DrugInteraction, InteractionSeverity
from src.domain.ports import LanguageModelPort

_KNOWN_INTERACTIONS: tuple[DrugInteraction, ...] = (
    DrugInteraction(
        primary_drug="warfarina",
        secondary_drug="aspirina",
        severity=InteractionSeverity.SEVERE,
        description=(
            "Efecto anticoagulante/antiagregante combinado: aumenta significativamente "
            "el riesgo de hemorragia."
        ),
        clinical_recommendation=(
            "Evitar la combinación salvo indicación médica expresa; si es necesaria, "
            "monitorizar INR estrechamente."
        ),
    ),
    DrugInteraction(
        primary_drug="ibuprofeno",
        secondary_drug="aspirina",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "El ibuprofeno puede interferir con el efecto antiagregante cardioprotector "
            "de la aspirina y aumenta el riesgo de sangrado gastrointestinal."
        ),
        clinical_recommendation=(
            "Espaciar la administración (aspirina al menos 2 horas antes del ibuprofeno) "
            "y valorar gastroprotección."
        ),
    ),
    DrugInteraction(
        primary_drug="enalapril",
        secondary_drug="espironolactona",
        severity=InteractionSeverity.HIGH,
        description=(
            "Ambos fármacos retienen potasio por mecanismos distintos: riesgo de "
            "hiperpotasemia clínicamente relevante."
        ),
        clinical_recommendation="Monitorizar potasio sérico y función renal periódicamente.",
    ),
    DrugInteraction(
        primary_drug="fluoxetina",
        secondary_drug="tramadol",
        severity=InteractionSeverity.SEVERE,
        description=(
            "Ambos aumentan la actividad serotoninérgica: riesgo de síndrome "
            "serotoninérgico."
        ),
        clinical_recommendation=(
            "Evitar la combinación; si es imprescindible, vigilar signos de síndrome "
            "serotoninérgico (agitación, hipertermia, hiperreflexia)."
        ),
    ),
    DrugInteraction(
        primary_drug="simvastatina",
        secondary_drug="claritromicina",
        severity=InteractionSeverity.HIGH,
        description=(
            "La claritromicina inhibe el CYP3A4, elevando los niveles plasmáticos de "
            "simvastatina y el riesgo de rabdomiólisis."
        ),
        clinical_recommendation=(
            "Suspender temporalmente la simvastatina durante el tratamiento con "
            "claritromicina o sustituir por un antibiótico alternativo."
        ),
    ),
    DrugInteraction(
        primary_drug="paracetamol",
        secondary_drug="warfarina",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "El uso prolongado de paracetamol a dosis altas puede potenciar el efecto "
            "anticoagulante de la warfarina."
        ),
        clinical_recommendation=(
            "Evitar el uso crónico a dosis altas sin control de INR; puntual y a dosis "
            "bajas es generalmente seguro."
        ),
    ),
)

_REVIEW_SEVERITIES = frozenset({InteractionSeverity.HIGH, InteractionSeverity.SEVERE})
_REVIEW_SEVERITY_VALUES = frozenset(severity.value for severity in _REVIEW_SEVERITIES)
_VALID_SEVERITY_VALUES = frozenset(severity.value for severity in InteractionSeverity)

_REQUIRED_ENTRY_FIELDS = (
    "primary_drug",
    "secondary_drug",
    "description",
    "clinical_recommendation",
)

LLM_SYSTEM_PROMPT = (
    "Eres un sistema de verificación de seguridad farmacológica. Tu prioridad absoluta es "
    "la seguridad del paciente sobre la conveniencia. Se te da una lista de fármacos que no "
    "coincide con ninguna interacción de la base curada interna. Analiza si existe alguna "
    "interacción farmacológica clínicamente relevante y conocida entre ellos, basándote "
    "únicamente en conocimiento farmacológico establecido — nunca inventes ni extrapoles una "
    "interacción de la que no tengas certeza razonable. Responde EXCLUSIVAMENTE con un JSON, "
    'sin texto adicional, con esta forma exacta: {"interactions": [{"primary_drug": string, '
    '"secondary_drug": string, "severity": "LOW"|"MEDIUM"|"HIGH"|"SEVERE", '
    '"description": string, "clinical_recommendation": string}], "uncertain": boolean}. '
    'Fija "uncertain": true si no tienes evidencia farmacológica suficiente para '
    "pronunciarte con confianza sobre alguno de los fármacos listados; en ese caso el "
    "sistema tratará el caso como pendiente de revisión médica, así que no marques "
    "`uncertain` solo por prudencia excesiva si realmente conoces la respuesta."
)


class SafetyCheckAgent:
    """Verifica interacciones farmacológicas: base curada (autoritativa) + LLM local
    opcional para combinaciones no cubiertas por la base curada."""

    def __init__(
        self,
        known_interactions: tuple[DrugInteraction, ...] = _KNOWN_INTERACTIONS,
        language_model: LanguageModelPort | None = None,
    ) -> None:
        self._known_interactions = known_interactions
        self._language_model = language_model

    async def check_interactions(self, drug_names: list[str]) -> dict:
        """Evalúa `drug_names`: primero contra la base curada; si no aplica ninguna y hay
        un modelo de lenguaje configurado, consulta al modelo. Devuelve
        `{"interactions": [...], "verdict": ...}`."""
        normalized = [name.strip().lower() for name in drug_names if name.strip()]

        curated_found = [
            interaction
            for interaction in self._known_interactions
            if self._interaction_applies(interaction, normalized)
        ]
        if curated_found:
            return {
                "interactions": [
                    self._serialize_curated(interaction)
                    for interaction in curated_found
                ],
                "verdict": self._determine_curated_verdict(curated_found),
            }

        if self._language_model is not None and len(normalized) >= 2:
            return await self._check_with_language_model(drug_names)

        return {"interactions": [], "verdict": "apto"}

    async def _check_with_language_model(self, drug_names: list[str]) -> dict:
        # `sorted()` normaliza el orden de entrada: el mismo conjunto de fármacos siempre
        # produce el mismo prompt exacto, sin importar el orden en que el usuario los añadió
        # en la UI. `temperature=0.0` fuerza salida determinista (muestreo greedy) — sin
        # esto, Groq usa su temperatura por omisión y la misma consulta puede devolver
        # severidad, descripción o incluso qué fármaco es "primary_drug" distintos en cada
        # petición: inaceptable para un veredicto de seguridad clínica (bug real reportado
        # por el usuario, ver .memory/BUGS.md).
        prompt = "Fármacos a evaluar: " + ", ".join(sorted(drug_names))
        raw_response = await self._language_model.generate_completion(
            prompt=prompt, system=LLM_SYSTEM_PROMPT, temperature=0.0
        )
        parsed = self._parse_llm_response(raw_response)

        if parsed is None:
            # Fallo de parseo (respuesta vacía, JSON inválido o forma inesperada): sin
            # evidencia interpretable, se trata como incertidumbre — nunca como "apto".
            return {"interactions": [], "verdict": "requiere_revision_medica"}

        entries, uncertain = parsed
        # Orden del par canonicalizado alfabéticamente (no el que el modelo eligiera como
        # "primary"/"secondary", que no tiene significado causal — `_interaction_applies`
        # ya trata los pares curados como no ordenados) y lista completa ordenada por par:
        # así la misma combinación de fármacos siempre se presenta en el mismo orden visual,
        # incluso si el modelo reporta las interacciones en un orden distinto entre
        # peticiones.
        serialized = sorted(
            (self._serialize_llm_entry(entry) for entry in entries),
            key=lambda item: (item["primary_drug"], item["secondary_drug"]),
        )

        if uncertain:
            return {"interactions": serialized, "verdict": "requiere_revision_medica"}
        if not entries:
            return {"interactions": [], "verdict": "apto"}

        severities_found = {entry["severity"] for entry in entries}
        verdict = (
            "requiere_revision_medica"
            if severities_found & _REVIEW_SEVERITY_VALUES
            else "apto_con_precaucion"
        )
        return {"interactions": serialized, "verdict": verdict}

    @staticmethod
    def _parse_llm_response(raw_response: str) -> tuple[list[dict], bool] | None:
        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None

        raw_entries = data.get("interactions", [])
        if not isinstance(raw_entries, list):
            return None

        valid_entries = [
            entry for entry in raw_entries if SafetyCheckAgent._is_valid_entry(entry)
        ]
        return valid_entries, bool(data.get("uncertain", False))

    @staticmethod
    def _is_valid_entry(entry: object) -> bool:
        if not isinstance(entry, dict):
            return False
        if entry.get("severity") not in _VALID_SEVERITY_VALUES:
            return False
        return all(
            isinstance(entry.get(field), str) and entry.get(field)
            for field in _REQUIRED_ENTRY_FIELDS
        )

    @staticmethod
    def _interaction_applies(
        interaction: DrugInteraction, normalized_drugs: list[str]
    ) -> bool:
        primary_present = any(
            interaction.primary_drug in drug for drug in normalized_drugs
        )
        secondary_present = any(
            interaction.secondary_drug in drug for drug in normalized_drugs
        )
        return primary_present and secondary_present

    @staticmethod
    def _determine_curated_verdict(found: list[DrugInteraction]) -> str:
        if any(interaction.severity in _REVIEW_SEVERITIES for interaction in found):
            return "requiere_revision_medica"
        return "apto_con_precaucion"

    @staticmethod
    def _serialize_curated(interaction: DrugInteraction) -> dict:
        return {
            "primary_drug": interaction.primary_drug,
            "secondary_drug": interaction.secondary_drug,
            "severity": interaction.severity.value,
            "description": interaction.description,
            "clinical_recommendation": interaction.clinical_recommendation,
            "source": "curated",
        }

    @staticmethod
    def _serialize_llm_entry(entry: dict) -> dict:
        primary_drug, secondary_drug = sorted(
            (entry["primary_drug"], entry["secondary_drug"])
        )
        return {
            "primary_drug": primary_drug,
            "secondary_drug": secondary_drug,
            "severity": entry["severity"],
            "description": entry["description"],
            "clinical_recommendation": entry["clinical_recommendation"],
            "source": "llm",
        }
