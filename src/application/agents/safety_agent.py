"""Agente de verificación de seguridad: interacciones farmacológicas conocidas.

Ver [AGENTES.md](../../../docs/AGENTES.md#2-safetycheckagent) para el contrato de
comportamiento. Usa la entidad de dominio `DrugInteraction`
([drug_interaction.py](../../domain/models/drug_interaction.py)).

Diseño híbrido: la base curada (`_KNOWN_INTERACTIONS`) es la fuente **autoritativa** —
si cubre la combinación de fármacos dada, su resultado se devuelve tal cual y nunca se
consulta al modelo de lenguaje. Solo cuando ningún par de la base curada aplica, y se ha
inyectado un `LanguageModelPort` (Groq en la nube desde la migración por latencia; antes
Ollama local), el agente consulta al modelo para razonar
sobre combinaciones no cubiertas. La respuesta del modelo nunca puede contradecir ni
sustituir a la base curada, solo complementarla; cada interacción devuelta lleva un campo
`source` (`"curated"` / `"llm"`) para que el consumidor distinga el nivel de confianza. Ante
un fallo de parseo o incertidumbre explícita del modelo, el veredicto por defecto es
`requiere_revision_medica` — nunca una aprobación silenciosa (ver docs/AGENTES.md).

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
    DrugInteraction(
        primary_drug="sildenafilo",
        secondary_drug="nitroglicerina",
        severity=InteractionSeverity.SEVERE,
        description=(
            "Ambos potencian la vía del óxido nítrico/GMPc: riesgo de hipotensión severa "
            "potencialmente mortal."
        ),
        clinical_recommendation=(
            "Contraindicado. No administrar sildenafilo (ni otros inhibidores de PDE5) a "
            "pacientes en tratamiento con nitratos, en ninguna forma o pauta."
        ),
    ),
    DrugInteraction(
        primary_drug="metformina",
        secondary_drug="contraste",
        severity=InteractionSeverity.HIGH,
        description=(
            "El contraste yodado puede deteriorar la función renal, reduciendo la "
            "eliminación de metformina y aumentando el riesgo de acidosis láctica."
        ),
        clinical_recommendation=(
            "Suspender la metformina antes de la administración de contraste yodado y "
            "reanudarla solo tras confirmar función renal normal (habitualmente 48 h "
            "después)."
        ),
    ),
    DrugInteraction(
        primary_drug="litio",
        secondary_drug="ibuprofeno",
        severity=InteractionSeverity.HIGH,
        description=(
            "Los AINE reducen la excreción renal de litio, elevando la litemia y el "
            "riesgo de toxicidad (temblor, confusión, insuficiencia renal)."
        ),
        clinical_recommendation=(
            "Evitar la combinación si es posible; si es necesaria, monitorizar litemia y "
            "función renal estrechamente."
        ),
    ),
    DrugInteraction(
        primary_drug="digoxina",
        secondary_drug="amiodarona",
        severity=InteractionSeverity.HIGH,
        description=(
            "La amiodarona inhibe la glicoproteína P y reduce el aclaramiento de "
            "digoxina, elevando sus niveles plasmáticos y el riesgo de toxicidad "
            "digitálica."
        ),
        clinical_recommendation=(
            "Reducir la dosis de digoxina (habitualmente a la mitad) al iniciar "
            "amiodarona y monitorizar niveles plasmáticos y síntomas de toxicidad."
        ),
    ),
    DrugInteraction(
        primary_drug="warfarina",
        secondary_drug="rifampicina",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "La rifampicina es un inductor enzimático potente (CYP2C9) que acelera el "
            "metabolismo de la warfarina, reduciendo su efecto anticoagulante."
        ),
        clinical_recommendation=(
            "Monitorizar INR con mayor frecuencia al iniciar o suspender rifampicina y "
            "ajustar la dosis de warfarina según respuesta."
        ),
    ),
    DrugInteraction(
        primary_drug="metronidazol",
        secondary_drug="alcohol",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "Reacción de tipo disulfiram (náuseas, vómitos, rubefacción, taquicardia) por "
            "inhibición de la aldehído deshidrogenasa."
        ),
        clinical_recommendation=(
            "Evitar el consumo de alcohol durante el tratamiento con metronidazol y hasta "
            "48 horas después de finalizarlo."
        ),
    ),
    DrugInteraction(
        primary_drug="enalapril",
        secondary_drug="ibuprofeno",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "Los AINE pueden reducir el efecto antihipertensivo de los IECA y, "
            "especialmente combinados con diuréticos, aumentar el riesgo de deterioro de "
            "la función renal."
        ),
        clinical_recommendation=(
            "Usar la dosis eficaz más baja de AINE durante el menor tiempo posible y "
            "vigilar presión arterial y función renal, sobre todo en tratamiento crónico."
        ),
    ),
    DrugInteraction(
        primary_drug="clopidogrel",
        secondary_drug="omeprazol",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "El omeprazol inhibe el CYP2C19, reduciendo la conversión de clopidogrel a su "
            "metabolito activo y disminuyendo su efecto antiagregante."
        ),
        clinical_recommendation=(
            "Si se necesita protección gástrica, valorar un IBP con menor interacción "
            "(p. ej. pantoprazol) o espaciar la administración."
        ),
    ),
    DrugInteraction(
        primary_drug="amoxicilina",
        secondary_drug="alopurinol",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "La combinación aumenta la incidencia de erupción cutánea (rash "
            "maculopapular), especialmente en tratamientos prolongados."
        ),
        clinical_recommendation=(
            "Informar al paciente del riesgo de erupción cutánea; valorar alternativa si "
            "hay antecedente de hipersensibilidad a penicilinas."
        ),
    ),
    DrugInteraction(
        primary_drug="amoxicilina",
        secondary_drug="metotrexato",
        severity=InteractionSeverity.HIGH,
        description=(
            "La amoxicilina reduce la eliminación renal de metotrexato, aumentando el "
            "riesgo de toxicidad hematológica y gastrointestinal."
        ),
        clinical_recommendation=(
            "Evitar la combinación si es posible; si es necesaria, monitorizar niveles de "
            "metotrexato y hemograma estrechamente."
        ),
    ),
    DrugInteraction(
        primary_drug="amoxicilina",
        secondary_drug="warfarina",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "Los antibióticos de amplio espectro pueden potenciar el efecto anticoagulante "
            "al alterar la flora intestinal productora de vitamina K."
        ),
        clinical_recommendation=(
            "Monitorizar INR con mayor frecuencia durante el tratamiento antibiótico y tras "
            "finalizarlo."
        ),
    ),
    DrugInteraction(
        primary_drug="paracetamol",
        secondary_drug="alcohol",
        severity=InteractionSeverity.HIGH,
        description=(
            "El consumo crónico de alcohol induce el CYP2E1, aumentando la formación del "
            "metabolito hepatotóxico de paracetamol y el riesgo de daño hepático incluso a "
            "dosis terapéuticas."
        ),
        clinical_recommendation=(
            "Evitar dosis altas o uso prolongado de paracetamol en consumidores habituales "
            "de alcohol; no superar 2 g/día en ese caso."
        ),
    ),
    DrugInteraction(
        primary_drug="ibuprofeno",
        secondary_drug="prednisona",
        severity=InteractionSeverity.MEDIUM,
        description=(
            "El uso combinado de AINE y corticoides aumenta significativamente el riesgo de "
            "úlcera y hemorragia digestiva."
        ),
        clinical_recommendation=(
            "Evitar la combinación si es posible; si es necesaria, valorar gastroprotección "
            "con un IBP."
        ),
    ),
    DrugInteraction(
        primary_drug="omeprazol",
        secondary_drug="metotrexato",
        severity=InteractionSeverity.HIGH,
        description=(
            "Los IBP reducen la eliminación renal de metotrexato a dosis altas, aumentando "
            "el riesgo de toxicidad."
        ),
        clinical_recommendation=(
            "En pautas de metotrexato a dosis altas, valorar suspender temporalmente el IBP "
            "o sustituirlo por un antagonista H2."
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
        # petición: inaceptable para un veredicto de seguridad clínica (bug real de
        # producción, corregido fijando la temperatura a 0).
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
