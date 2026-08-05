"""Ejecuta el dataset de evaluación contra los agentes reales (Ollama/Gemini locales).

Mide, sobre datos sintéticos (ver [dataset.py](dataset.py)):
- `SafetyCheckAgent`: exactitud del veredicto (`apto`/`apto_con_precaucion`/
  `requiere_revision_medica`) y latencia, separando casos cubiertos por la base curada
  (deberían tener latencia ~0, sin llamada a Ollama) de casos que requieren razonamiento
  del LLM local.
- `PrescriptionAgent`: tasa de recuperación (recall) de nombres de fármaco esperados sobre
  imágenes de receta sintéticas (ver `generate_synthetic_prescriptions.py`), y latencia de
  la llamada a Gemini 1.5 Pro.

No es un test de `pytest` — requiere servicios reales corriendo (Ollama local con `llama3`
descargado y, opcionalmente, `GOOGLE_API_KEY` configurada para la parte de recetas) y no es
determinista (el LLM puede variar su respuesta entre ejecuciones), por lo que sus resultados
se registran como snapshot en [EVALUATION.md](../EVALUATION.md) en vez de aplicarse como gate
de CI. Uso: python -m evaluation.run_evaluation
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from evaluation.dataset import (
    PRESCRIPTION_DATASET,
    SAFETY_CHECK_DATASET,
    PrescriptionCase,
)
from evaluation.generate_synthetic_prescriptions import OUTPUT_DIR, generate_all
from src.application.agents.prescription_agent import PrescriptionAgent
from src.application.agents.safety_agent import SafetyCheckAgent
from src.infrastructure.external.gemini_client import GeminiClient
from src.infrastructure.external.ollama_client import OllamaClient

RESULTS_PATH = Path(__file__).parent / "results.json"


@dataclass
class SafetyCaseResult:
    case_id: str
    drugs: list[str]
    expected_verdict: str
    actual_verdict: str
    expected_source: str
    actual_sources: list[str]
    correct: bool
    latency_seconds: float


@dataclass
class PrescriptionCaseResult:
    case_id: str
    expected_drug_names: list[str]
    extracted_drug_names: list[str]
    recall: float
    latency_seconds: float


async def run_safety_check_evaluation(
    agent: SafetyCheckAgent,
) -> list[SafetyCaseResult]:
    results = []
    for case in SAFETY_CHECK_DATASET:
        start = time.perf_counter()
        outcome = await agent.check_interactions(case.drugs)
        elapsed = time.perf_counter() - start

        actual_sources = [
            interaction["source"] for interaction in outcome["interactions"]
        ]
        results.append(
            SafetyCaseResult(
                case_id=case.case_id,
                drugs=case.drugs,
                expected_verdict=case.expected_verdict,
                actual_verdict=outcome["verdict"],
                expected_source=case.expected_source,
                actual_sources=actual_sources,
                correct=outcome["verdict"] == case.expected_verdict,
                latency_seconds=round(elapsed, 3),
            )
        )
    return results


def _extract_drug_names(prescription_result: dict) -> list[str]:
    return [
        drug["farmaco"].lower()
        for drug in prescription_result.get("drugs", [])
        if drug.get("farmaco")
    ]


def _compute_recall(expected: list[str], extracted: list[str]) -> float:
    if not expected:
        return 1.0
    matched = sum(
        1
        for expected_name in expected
        if any(expected_name.lower() in extracted_name for extracted_name in extracted)
    )
    return round(matched / len(expected), 3)


async def run_prescription_evaluation(
    agent: PrescriptionAgent, cases: list[PrescriptionCase]
) -> list[PrescriptionCaseResult]:
    results = []
    for case in cases:
        image_path = OUTPUT_DIR / f"{case.case_id}.jpg"
        image_bytes = image_path.read_bytes()

        start = time.perf_counter()
        outcome = await agent.extract_prescription(image_bytes, mime_type="image/jpeg")
        elapsed = time.perf_counter() - start

        extracted = _extract_drug_names(outcome)
        results.append(
            PrescriptionCaseResult(
                case_id=case.case_id,
                expected_drug_names=case.expected_drug_names,
                extracted_drug_names=extracted,
                recall=_compute_recall(case.expected_drug_names, extracted),
                latency_seconds=round(elapsed, 3),
            )
        )
    return results


def _print_safety_summary(results: list[SafetyCaseResult]) -> None:
    correct = sum(1 for r in results if r.correct)
    print(f"\n=== SafetyCheckAgent: {correct}/{len(results)} veredictos correctos ===")
    for r in results:
        status = "OK" if r.correct else "FALLO"
        print(
            f"  [{status}] {r.case_id}: esperado={r.expected_verdict} "
            f"obtenido={r.actual_verdict} fuentes={r.actual_sources} "
            f"({r.latency_seconds}s)"
        )


def _print_prescription_summary(results: list[PrescriptionCaseResult]) -> None:
    if not results:
        print("\n=== PrescriptionAgent: omitido (sin GOOGLE_API_KEY configurada) ===")
        return
    avg_recall = round(sum(r.recall for r in results) / len(results), 3)
    print(f"\n=== PrescriptionAgent: recall medio = {avg_recall} ===")
    for r in results:
        print(
            f"  {r.case_id}: esperado={r.expected_drug_names} "
            f"extraido={r.extracted_drug_names} recall={r.recall} "
            f"({r.latency_seconds}s)"
        )


async def main() -> None:
    generate_all()

    async with OllamaClient() as ollama_client:
        safety_agent = SafetyCheckAgent(language_model=ollama_client)
        safety_results = await run_safety_check_evaluation(safety_agent)

    gemini_client = GeminiClient()
    prescription_results: list[PrescriptionCaseResult] = []
    if gemini_client._client is not None:
        prescription_agent = PrescriptionAgent(vision_client=gemini_client)
        prescription_results = await run_prescription_evaluation(
            prescription_agent, PRESCRIPTION_DATASET
        )

    _print_safety_summary(safety_results)
    _print_prescription_summary(prescription_results)

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "safety_check": [asdict(r) for r in safety_results],
                "prescription": [asdict(r) for r in prescription_results],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nResultados guardados en {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
