"""Tests unitarios de `SafetyCheckAgent` (interacciones farmacológicas conocidas +
razonamiento LLM opcional para combinaciones no cubiertas por la base curada)."""

from __future__ import annotations

import json

import pytest

from src.application.agents.safety_agent import SafetyCheckAgent
from src.domain.models.drug_interaction import DrugInteraction, InteractionSeverity


class FakeLanguageModel:
    """Doble de `LanguageModelPort` que devuelve una respuesta fija a `generate_completion`."""

    def __init__(self, completion_response: str) -> None:
        self._completion_response = completion_response
        self.received_prompts: list[tuple[str, str]] = []
        self.received_temperatures: list[float | None] = []

    async def generate_embedding(self, text: str) -> list[float]:
        raise NotImplementedError

    async def generate_completion(
        self, prompt: str, system: str = "", temperature: float | None = None
    ) -> str:
        self.received_prompts.append((prompt, system))
        self.received_temperatures.append(temperature)
        return self._completion_response


class TestSafetyCheckAgentCuratedTable:
    @pytest.mark.asyncio
    async def test_detects_severe_interaction_requires_medical_review(self) -> None:
        agent = SafetyCheckAgent()

        result = await agent.check_interactions(["Warfarina 5mg", "Aspirina 100mg"])

        assert result["verdict"] == "requiere_revision_medica"
        assert len(result["interactions"]) == 1
        assert result["interactions"][0]["severity"] == "SEVERE"
        assert result["interactions"][0]["source"] == "curated"

    @pytest.mark.asyncio
    async def test_detects_medium_interaction_fit_with_caution(self) -> None:
        agent = SafetyCheckAgent()

        result = await agent.check_interactions(["Ibuprofeno", "Aspirina"])

        assert result["verdict"] == "apto_con_precaucion"
        assert len(result["interactions"]) == 1
        assert result["interactions"][0]["severity"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_no_known_interaction_and_no_llm_configured_is_fit(self) -> None:
        agent = SafetyCheckAgent()

        result = await agent.check_interactions(["Paracetamol", "Omeprazol"])

        assert result["verdict"] == "apto"
        assert result["interactions"] == []

    @pytest.mark.asyncio
    async def test_matching_is_case_insensitive_and_substring_based(self) -> None:
        agent = SafetyCheckAgent()

        result = await agent.check_interactions(
            ["WARFARINA Sódica 5 MG", "  Aspirina Infantil  "]
        )

        assert result["verdict"] == "requiere_revision_medica"
        assert len(result["interactions"]) == 1

    @pytest.mark.asyncio
    async def test_severe_interaction_never_downgraded_by_extra_safe_drug(self) -> None:
        agent = SafetyCheckAgent()

        result = await agent.check_interactions(
            ["Fluoxetina", "Tramadol", "Paracetamol"]
        )

        assert result["verdict"] == "requiere_revision_medica"
        assert any(i["severity"] == "SEVERE" for i in result["interactions"])

    @pytest.mark.asyncio
    async def test_uses_injected_known_interactions(self) -> None:
        custom_interaction = DrugInteraction(
            primary_drug="drogax",
            secondary_drug="drogay",
            severity=InteractionSeverity.LOW,
            description="Interacción de prueba.",
            clinical_recommendation="Ninguna acción necesaria.",
        )
        agent = SafetyCheckAgent(known_interactions=(custom_interaction,))

        result = await agent.check_interactions(["DrogaX", "DrogaY"])

        assert result["verdict"] == "apto_con_precaucion"
        assert result["interactions"][0]["primary_drug"] == "drogax"

    @pytest.mark.asyncio
    async def test_curated_match_never_consults_language_model(self) -> None:
        language_model = FakeLanguageModel(completion_response='{"interactions": []}')
        agent = SafetyCheckAgent(language_model=language_model)

        await agent.check_interactions(["Warfarina", "Aspirina"])

        assert language_model.received_prompts == []


class TestSafetyCheckAgentLLMAssisted:
    @pytest.mark.asyncio
    async def test_no_language_model_configured_defaults_to_fit_for_unknown_pair(
        self,
    ) -> None:
        agent = SafetyCheckAgent(language_model=None)

        result = await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert result == {"interactions": [], "verdict": "apto"}

    @pytest.mark.asyncio
    async def test_llm_reports_no_interaction_is_fit(self) -> None:
        language_model = FakeLanguageModel(
            completion_response=json.dumps({"interactions": [], "uncertain": False})
        )
        agent = SafetyCheckAgent(language_model=language_model)

        result = await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert result == {"interactions": [], "verdict": "apto"}

    @pytest.mark.asyncio
    async def test_llm_reports_severe_interaction_requires_medical_review(self) -> None:
        response = json.dumps(
            {
                "interactions": [
                    {
                        "primary_drug": "farmacox",
                        "secondary_drug": "farmacoy",
                        "severity": "SEVERE",
                        "description": "Interacción grave hipotética.",
                        "clinical_recommendation": "Evitar la combinación.",
                    }
                ],
                "uncertain": False,
            }
        )
        agent = SafetyCheckAgent(language_model=FakeLanguageModel(response))

        result = await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert result["verdict"] == "requiere_revision_medica"
        assert result["interactions"][0]["source"] == "llm"
        assert result["interactions"][0]["severity"] == "SEVERE"

    @pytest.mark.asyncio
    async def test_llm_reports_low_severity_is_fit_with_caution(self) -> None:
        response = json.dumps(
            {
                "interactions": [
                    {
                        "primary_drug": "farmacox",
                        "secondary_drug": "farmacoy",
                        "severity": "LOW",
                        "description": "Interacción leve hipotética.",
                        "clinical_recommendation": "Sin acción especial.",
                    }
                ],
                "uncertain": False,
            }
        )
        agent = SafetyCheckAgent(language_model=FakeLanguageModel(response))

        result = await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert result["verdict"] == "apto_con_precaucion"

    @pytest.mark.asyncio
    async def test_llm_uncertain_forces_medical_review_even_without_interactions(
        self,
    ) -> None:
        response = json.dumps({"interactions": [], "uncertain": True})
        agent = SafetyCheckAgent(language_model=FakeLanguageModel(response))

        result = await agent.check_interactions(["FarmacoRaroX", "FarmacoRaroY"])

        assert result["verdict"] == "requiere_revision_medica"

    @pytest.mark.asyncio
    async def test_malformed_llm_json_defaults_to_medical_review(self) -> None:
        agent = SafetyCheckAgent(language_model=FakeLanguageModel("esto no es JSON"))

        result = await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert result["verdict"] == "requiere_revision_medica"
        assert result["interactions"] == []

    @pytest.mark.asyncio
    async def test_empty_llm_response_defaults_to_medical_review(self) -> None:
        agent = SafetyCheckAgent(language_model=FakeLanguageModel(""))

        result = await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert result["verdict"] == "requiere_revision_medica"

    @pytest.mark.asyncio
    async def test_llm_entry_with_invalid_severity_is_discarded(self) -> None:
        response = json.dumps(
            {
                "interactions": [
                    {
                        "primary_drug": "farmacox",
                        "secondary_drug": "farmacoy",
                        "severity": "GRAVISIMA",
                        "description": "Severidad inventada, fuera del enum.",
                        "clinical_recommendation": "N/A",
                    }
                ],
                "uncertain": False,
            }
        )
        agent = SafetyCheckAgent(language_model=FakeLanguageModel(response))

        result = await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert result == {"interactions": [], "verdict": "apto"}

    @pytest.mark.asyncio
    async def test_single_drug_never_consults_language_model(self) -> None:
        language_model = FakeLanguageModel('{"interactions": []}')
        agent = SafetyCheckAgent(language_model=language_model)

        result = await agent.check_interactions(["Paracetamol"])

        assert language_model.received_prompts == []
        assert result == {"interactions": [], "verdict": "apto"}

    @pytest.mark.asyncio
    async def test_forwards_drug_names_and_system_prompt_to_language_model(
        self,
    ) -> None:
        language_model = FakeLanguageModel('{"interactions": []}')
        agent = SafetyCheckAgent(language_model=language_model)

        await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert len(language_model.received_prompts) == 1
        prompt, system = language_model.received_prompts[0]
        assert "FarmacoX" in prompt
        assert "FarmacoY" in prompt
        assert "seguridad farmacológica" in system

    @pytest.mark.asyncio
    async def test_requests_deterministic_output_from_language_model(self) -> None:
        """Regresión: sin `temperature=0.0`, Groq muestrea la respuesta y la misma consulta
        de interacciones puede devolver severidad/descripción distintas en cada petición —
        inaceptable para un veredicto de seguridad clínica (bug real reportado por el
        usuario con Heparina/Lixiana/Aspirina, ver .memory/BUGS.md)."""
        language_model = FakeLanguageModel('{"interactions": []}')
        agent = SafetyCheckAgent(language_model=language_model)

        await agent.check_interactions(["FarmacoX", "FarmacoY"])

        assert language_model.received_temperatures == [0.0]

    @pytest.mark.asyncio
    async def test_same_drug_set_produces_identical_prompt_regardless_of_input_order(
        self,
    ) -> None:
        language_model = FakeLanguageModel('{"interactions": []}')
        agent = SafetyCheckAgent(language_model=language_model)

        await agent.check_interactions(["Heparina", "Lixiana", "Aspirina"])
        await agent.check_interactions(["Aspirina", "Heparina", "Lixiana"])

        prompt_a, _ = language_model.received_prompts[0]
        prompt_b, _ = language_model.received_prompts[1]
        assert prompt_a == prompt_b

    @pytest.mark.asyncio
    async def test_llm_pair_order_is_canonicalized_alphabetically(self) -> None:
        """El modelo puede etiquetar cualquiera de los dos fármacos como "primary_drug" de
        forma arbitraria (no tiene significado causal) — se normaliza para que la misma
        pareja siempre se muestre en el mismo orden, en vez de "voltearse" visualmente entre
        peticiones idénticas."""
        response = json.dumps(
            {
                "interactions": [
                    {
                        "primary_drug": "lixiana",
                        "secondary_drug": "heparina",
                        "severity": "HIGH",
                        "description": "Interacción hipotética.",
                        "clinical_recommendation": "Evitar la combinación.",
                    }
                ],
                "uncertain": False,
            }
        )
        agent = SafetyCheckAgent(language_model=FakeLanguageModel(response))

        result = await agent.check_interactions(["Heparina", "Lixiana"])

        assert result["interactions"][0]["primary_drug"] == "heparina"
        assert result["interactions"][0]["secondary_drug"] == "lixiana"

    @pytest.mark.asyncio
    async def test_llm_interactions_list_is_sorted_for_stable_display_order(
        self,
    ) -> None:
        response = json.dumps(
            {
                "interactions": [
                    {
                        "primary_drug": "lixiana",
                        "secondary_drug": "aspirina",
                        "severity": "LOW",
                        "description": "d1",
                        "clinical_recommendation": "r1",
                    },
                    {
                        "primary_drug": "heparina",
                        "secondary_drug": "aspirina",
                        "severity": "LOW",
                        "description": "d2",
                        "clinical_recommendation": "r2",
                    },
                ],
                "uncertain": False,
            }
        )
        agent = SafetyCheckAgent(language_model=FakeLanguageModel(response))

        result = await agent.check_interactions(["Heparina", "Lixiana", "Aspirina"])

        pairs = [
            (i["primary_drug"], i["secondary_drug"]) for i in result["interactions"]
        ]
        assert pairs == sorted(pairs)
