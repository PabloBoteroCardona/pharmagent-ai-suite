"""Tests unitarios de `SafetyCheckAgent` (interacciones farmacológicas conocidas)."""

from __future__ import annotations

from src.application.agents.safety_agent import SafetyCheckAgent
from src.domain.models.drug_interaction import DrugInteraction, InteractionSeverity


class TestSafetyCheckAgent:
    def test_detects_severe_interaction_requires_medical_review(self) -> None:
        agent = SafetyCheckAgent()

        result = agent.check_interactions(["Warfarina 5mg", "Aspirina 100mg"])

        assert result["verdict"] == "requiere_revision_medica"
        assert len(result["interactions"]) == 1
        assert result["interactions"][0]["severity"] == "SEVERE"

    def test_detects_medium_interaction_fit_with_caution(self) -> None:
        agent = SafetyCheckAgent()

        result = agent.check_interactions(["Ibuprofeno", "Aspirina"])

        assert result["verdict"] == "apto_con_precaucion"
        assert len(result["interactions"]) == 1
        assert result["interactions"][0]["severity"] == "MEDIUM"

    def test_no_known_interaction_is_fit(self) -> None:
        agent = SafetyCheckAgent()

        result = agent.check_interactions(["Paracetamol", "Omeprazol"])

        assert result["verdict"] == "apto"
        assert result["interactions"] == []

    def test_matching_is_case_insensitive_and_substring_based(self) -> None:
        agent = SafetyCheckAgent()

        result = agent.check_interactions(
            ["WARFARINA Sódica 5 MG", "  Aspirina Infantil  "]
        )

        assert result["verdict"] == "requiere_revision_medica"
        assert len(result["interactions"]) == 1

    def test_severe_interaction_never_downgraded_by_extra_safe_drug(self) -> None:
        agent = SafetyCheckAgent()

        result = agent.check_interactions(["Fluoxetina", "Tramadol", "Paracetamol"])

        assert result["verdict"] == "requiere_revision_medica"
        assert any(i["severity"] == "SEVERE" for i in result["interactions"])

    def test_uses_injected_known_interactions(self) -> None:
        custom_interaction = DrugInteraction(
            primary_drug="drogax",
            secondary_drug="drogay",
            severity=InteractionSeverity.LOW,
            description="Interacción de prueba.",
            clinical_recommendation="Ninguna acción necesaria.",
        )
        agent = SafetyCheckAgent(known_interactions=(custom_interaction,))

        result = agent.check_interactions(["DrogaX", "DrogaY"])

        assert result["verdict"] == "apto_con_precaucion"
        assert result["interactions"][0]["primary_drug"] == "drogax"
