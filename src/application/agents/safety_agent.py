"""Agente de verificación de seguridad: interacciones farmacológicas conocidas.

Ver [AGENTS.md](../../../AGENTS.md#2-safetycheckagent) para el contrato de
comportamiento. Usa la entidad de dominio `DrugInteraction`
([drug_interaction.py](../../domain/models/drug_interaction.py)).

Limitación aceptada: `_KNOWN_INTERACTIONS` es una base curada mínima, en memoria, con
fines demostrativos (TFM) — no sustituye una base de datos de interacciones clínica
completa (p. ej. un servicio externo curado). Ampliar esta base o sustituirla por una
fuente real queda fuera de alcance de este bloque.
"""

from __future__ import annotations

from src.domain.models.drug_interaction import DrugInteraction, InteractionSeverity

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


class SafetyCheckAgent:
    """Verifica interacciones farmacológicas conocidas entre una lista de fármacos."""

    def __init__(
        self, known_interactions: tuple[DrugInteraction, ...] = _KNOWN_INTERACTIONS
    ) -> None:
        self._known_interactions = known_interactions

    def check_interactions(self, drug_names: list[str]) -> dict:
        """Evalúa `drug_names` contra la base curada y devuelve interacciones + veredicto."""
        normalized = [name.strip().lower() for name in drug_names if name.strip()]
        found = [
            interaction
            for interaction in self._known_interactions
            if self._interaction_applies(interaction, normalized)
        ]

        return {
            "interactions": [
                {
                    "primary_drug": interaction.primary_drug,
                    "secondary_drug": interaction.secondary_drug,
                    "severity": interaction.severity.value,
                    "description": interaction.description,
                    "clinical_recommendation": interaction.clinical_recommendation,
                }
                for interaction in found
            ],
            "verdict": self._determine_verdict(found),
        }

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
    def _determine_verdict(found: list[DrugInteraction]) -> str:
        if not found:
            return "apto"
        if any(interaction.severity in _REVIEW_SEVERITIES for interaction in found):
            return "requiere_revision_medica"
        return "apto_con_precaucion"
