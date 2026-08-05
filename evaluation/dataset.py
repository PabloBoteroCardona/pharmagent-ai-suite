"""Dataset de evaluación sintético para `SafetyCheckAgent` y `PrescriptionAgent`.

Todos los casos son sintéticos (inventados para este dataset, no proceden de pacientes ni
recetas reales) — se marca explícitamente en cada caso y en [EVALUATION.md](../EVALUATION.md).
Las interacciones farmacológicas de referencia (`expected_verdict`) están basadas en
conocimiento farmacológico público y establecido (no en la base curada del propio
`SafetyCheckAgent`, para evitar una evaluación circular).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SafetyCheckCase:
    """Un caso de evaluación para `SafetyCheckAgent.check_interactions`."""

    case_id: str
    drugs: list[str]
    expected_verdict: str
    expected_source: str  # "curated" | "llm" | "any" (no aplica cuando expected_verdict="apto" sin match)
    rationale: str


@dataclass(frozen=True)
class PrescriptionCase:
    """Un caso de evaluación para `PrescriptionAgent.extract_prescription`.

    `prescription_text` es el texto que se renderiza en la imagen sintética de la
    receta (ver `generate_synthetic_prescriptions.py`) — sirve como *ground truth*
    aproximado: se espera que el nombre de cada fármaco en `expected_drug_names`
    aparezca (como subcadena, insensible a mayúsculas) en el campo `farmaco` de
    algún elemento de `drugs` en la respuesta del agente.
    """

    case_id: str
    prescription_lines: list[str]
    expected_drug_names: list[str]


# --- Casos cubiertos por la base curada de SafetyCheckAgent (fuente autoritativa) ---
CURATED_SAFETY_CASES: list[SafetyCheckCase] = [
    SafetyCheckCase(
        case_id="curated-warfarina-aspirina",
        drugs=["Warfarina", "Aspirina"],
        expected_verdict="requiere_revision_medica",
        expected_source="curated",
        rationale="Interacción anticoagulante/antiagregante grave, ampliamente documentada.",
    ),
    SafetyCheckCase(
        case_id="curated-ibuprofeno-aspirina",
        drugs=["Ibuprofeno", "Aspirina"],
        expected_verdict="apto_con_precaucion",
        expected_source="curated",
        rationale="El ibuprofeno interfiere con el efecto antiagregante de la aspirina.",
    ),
    SafetyCheckCase(
        case_id="curated-fluoxetina-tramadol",
        drugs=["Fluoxetina", "Tramadol"],
        expected_verdict="requiere_revision_medica",
        expected_source="curated",
        rationale="Riesgo de síndrome serotoninérgico, interacción grave conocida.",
    ),
]

# --- Casos NO cubiertos por la base curada — ejercitan el razonamiento del LLM local ---
# Interacciones de referencia establecidas en literatura farmacológica pública, elegidas
# deliberadamente para no solapar con `_KNOWN_INTERACTIONS` de `safety_agent.py`.
LLM_ASSISTED_SAFETY_CASES: list[SafetyCheckCase] = [
    SafetyCheckCase(
        case_id="llm-imao-isrs",
        drugs=["Fenelzina", "Sertralina"],
        expected_verdict="requiere_revision_medica",
        expected_source="llm",
        rationale=(
            "IMAO + ISRS: riesgo grave de síndrome serotoninérgico, contraindicación "
            "clásica en farmacología."
        ),
    ),
    SafetyCheckCase(
        case_id="llm-digoxina-amiodarona",
        drugs=["Digoxina", "Amiodarona"],
        expected_verdict="requiere_revision_medica",
        expected_source="llm",
        rationale=(
            "La amiodarona eleva los niveles plasmáticos de digoxina: riesgo de "
            "toxicidad digitálica, interacción bien documentada."
        ),
    ),
    SafetyCheckCase(
        case_id="llm-metformina-furosemida",
        drugs=["Metformina", "Furosemida"],
        expected_verdict="apto_con_precaucion",
        expected_source="llm",
        rationale=(
            "La furosemida puede alterar el control glucémico y la función renal, "
            "relevante para la dosis de metformina — interacción moderada conocida."
        ),
    ),
    SafetyCheckCase(
        case_id="llm-paracetamol-amoxicilina-no-interaction",
        drugs=["Paracetamol", "Amoxicilina"],
        expected_verdict="apto",
        expected_source="llm",
        rationale="Sin interacción clínicamente relevante documentada entre ambos.",
    ),
]

SAFETY_CHECK_DATASET: list[SafetyCheckCase] = (
    CURATED_SAFETY_CASES + LLM_ASSISTED_SAFETY_CASES
)


# --- Recetas sintéticas para PrescriptionAgent ---
# Cada línea sigue el formato "<fármaco> <dosis> - <frecuencia> - <duración>", renderizada
# como imagen por `generate_synthetic_prescriptions.py`. Nombres y dosis inventados —
# ninguno corresponde a una receta real.
PRESCRIPTION_DATASET: list[PrescriptionCase] = [
    PrescriptionCase(
        case_id="rx-single-drug",
        prescription_lines=["Ibuprofeno 600 mg - cada 8 horas - 5 dias"],
        expected_drug_names=["ibuprofeno"],
    ),
    PrescriptionCase(
        case_id="rx-two-drugs",
        prescription_lines=[
            "Amoxicilina 500 mg - cada 8 horas - 7 dias",
            "Paracetamol 1 g - cada 6 horas - 3 dias",
        ],
        expected_drug_names=["amoxicilina", "paracetamol"],
    ),
    PrescriptionCase(
        case_id="rx-three-drugs",
        prescription_lines=[
            "Omeprazol 20 mg - cada 24 horas - 14 dias",
            "Warfarina 5 mg - cada 24 horas - 30 dias",
            "Aspirina 100 mg - cada 24 horas - 30 dias",
        ],
        expected_drug_names=["omeprazol", "warfarina", "aspirina"],
    ),
]


@dataclass(frozen=True)
class EvaluationDataset:
    safety_cases: list[SafetyCheckCase] = field(
        default_factory=lambda: SAFETY_CHECK_DATASET
    )
    prescription_cases: list[PrescriptionCase] = field(
        default_factory=lambda: PRESCRIPTION_DATASET
    )
