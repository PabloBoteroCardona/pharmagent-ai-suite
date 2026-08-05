"""Fixtures compartidas de los tests de integración de la API.

Sustituye las dependencias de infraestructura (CIMA, Ollama, PostgreSQL, Gemini) por
dobles en memoria vía `app.dependency_overrides`, para que la suite se ejecute de
forma determinista y sin red/Docker — igual que en CI. Cada doble satisface
estructuralmente el puerto de dominio correspondiente (`src/domain/ports/`).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.application.agents.safety_agent import LLM_SYSTEM_PROMPT
from src.infrastructure.api.main import app
from src.infrastructure.api.routers.pharmacy_router import (
    get_cima_client,
    get_drug_repository,
    get_gemini_client,
    get_ollama_client,
    get_prescription_record_repository,
)

FAKE_DRUG = SimpleNamespace(
    nregistro="12345",
    nombre="Ibuprofeno Test 600mg",
    pactivos="ibuprofeno",
    labtitular="Laboratorio Test S.A.",
    documento_html="Indicado para el alivio del dolor leve a moderado.",
)

FAKE_LIVE_DRUG_SEARCH_RESULT = {"nregistro": "99999", "nombre": "Paracetamol Test 1g"}
FAKE_LIVE_DRUG_DETAIL = {
    "nregistro": "99999",
    "nombre": "Paracetamol Test 1g",
    "pactivos": "paracetamol",
    "labtitular": "Laboratorio Live S.A.",
    "cpresc": "sin receta",
}
FAKE_LIVE_DRUG = SimpleNamespace(
    nregistro="99999",
    nombre="Paracetamol Test 1g",
    pactivos="paracetamol",
    labtitular="Laboratorio Live S.A.",
    documento_html="Prospecto de prueba en vivo.",
)

FAKE_RAG_RESPONSE_TEXT = "Respuesta simulada basada en el contexto de prueba."

FAKE_PRESCRIPTION_ANALYSIS = {
    "drugs": [
        {
            "farmaco": "Ibuprofeno",
            "dosificacion": "600 mg",
            "frecuencia": "cada 8 horas",
            "duracion": "5 días",
        }
    ],
    "advertencias": ["Tomar con alimentos."],
}


class FakeCimaClient:
    """Por defecto no encuentra nada (simula que CIMA tampoco tiene el fármaco). Pasar
    `search_results`/`medicamento_detail` para simular que CIMA sí lo encuentra en vivo."""

    def __init__(
        self,
        search_results: list[dict] | None = None,
        medicamento_detail: dict | None = None,
    ) -> None:
        self._search_results = search_results or []
        self._medicamento_detail = medicamento_detail

    async def search_medicamentos(self, nombre: str) -> list[dict]:
        return self._search_results

    async def get_medicamento_by_nregistro(self, nregistro: str) -> dict | None:
        if (
            self._medicamento_detail
            and self._medicamento_detail["nregistro"] == nregistro
        ):
            return self._medicamento_detail
        return None

    async def get_prospecto_html(self, nregistro: str) -> str | None:
        return "Prospecto de prueba en vivo." if self._medicamento_detail else None


class FakeOllamaClient:
    async def generate_embedding(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    async def generate_completion(self, prompt: str, system: str = "") -> str:
        if system == LLM_SYSTEM_PROMPT:
            # Camino de razonamiento de SafetyCheckAgent para combinaciones no cubiertas
            # por la base curada: simula que el modelo no encuentra ninguna interacción.
            return json.dumps({"interactions": [], "uncertain": False})
        return FAKE_RAG_RESPONSE_TEXT


class FakeDrugRepository:
    """Por defecto simula un acierto de caché (`[FAKE_DRUG]`). Pasar
    `cached_results=[]` para simular una caché vacía y ejercitar el respaldo de CIMA
    en vivo de `DrugService.search_drugs_semantic`."""

    def __init__(self, cached_results: list[SimpleNamespace] | None = None) -> None:
        self._cached_results = [FAKE_DRUG] if cached_results is None else cached_results
        self.saved_drugs: list[dict] = []

    async def save_drug(self, drug_data: dict) -> SimpleNamespace:
        self.saved_drugs.append(drug_data)
        return FAKE_LIVE_DRUG

    async def get_by_nregistro(self, nregistro: str) -> SimpleNamespace | None:
        return FAKE_DRUG

    async def search_similar_by_vector(
        self, embedding: list[float], limit: int = 5
    ) -> list[SimpleNamespace]:
        return self._cached_results


class FakeGeminiClient:
    async def analyze_prescription_image(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> dict:
        return FAKE_PRESCRIPTION_ANALYSIS


class FakePrescriptionRecordRepository:
    def __init__(self) -> None:
        self.saved_records: list[dict] = []

    async def save(
        self,
        drugs: list[dict],
        advertencias: list[str],
        safety_check: dict | None,
        patient_id: str | None = None,
    ) -> SimpleNamespace:
        record = {
            "drugs": drugs,
            "advertencias": advertencias,
            "safety_check": safety_check,
            "patient_id": patient_id,
        }
        self.saved_records.append(record)
        return SimpleNamespace(**record)


@pytest.fixture
def client() -> TestClient:
    """`TestClient` con las dependencias externas sustituidas por dobles en memoria."""
    app.dependency_overrides[get_cima_client] = lambda: FakeCimaClient()
    app.dependency_overrides[get_ollama_client] = lambda: FakeOllamaClient()
    app.dependency_overrides[get_drug_repository] = lambda: FakeDrugRepository()
    app.dependency_overrides[get_gemini_client] = lambda: FakeGeminiClient()
    app.dependency_overrides[get_prescription_record_repository] = lambda: (
        FakePrescriptionRecordRepository()
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
