"""Tests de integración de los endpoints REST de `pharmacy_router.py`.

Ejercitan la aplicación FastAPI real (`TestClient`) con las dependencias de
infraestructura sustituidas por dobles en memoria (ver `conftest.py`) — validan el
cableado completo de rutas, esquemas Pydantic y capas de aplicación, sin depender de
CIMA, Ollama, PostgreSQL ni Gemini reales.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.conftest import FAKE_DRUG, FAKE_RAG_RESPONSE_TEXT


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSearchEndpoint:
    def test_search_returns_matching_drugs(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/pharmacy/search", json={"query": "dolor de cabeza", "limit": 3}
        )

        assert response.status_code == 200
        body = response.json()
        assert body == [
            {
                "nregistro": FAKE_DRUG.nregistro,
                "nombre": FAKE_DRUG.nombre,
                "pactivos": FAKE_DRUG.pactivos,
                "labtitular": FAKE_DRUG.labtitular,
            }
        ]

    def test_search_rejects_empty_query(self, client: TestClient) -> None:
        response = client.post("/api/v1/pharmacy/search", json={"query": ""})

        assert response.status_code == 422


class TestConsultEndpoint:
    def test_consult_returns_grounded_answer(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/pharmacy/consult",
            json={"query": "¿cómo se toma el ibuprofeno?"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "¿cómo se toma el ibuprofeno?"
        assert body["response"] == FAKE_RAG_RESPONSE_TEXT
        assert body["sources"] == [FAKE_DRUG.nombre]

    def test_consult_rejects_empty_query(self, client: TestClient) -> None:
        response = client.post("/api/v1/pharmacy/consult", json={"query": ""})

        assert response.status_code == 422


class TestCheckInteractionsEndpoint:
    def test_detects_severe_interaction(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/pharmacy/check-interactions",
            json={"drugs": ["Warfarina", "Aspirina"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "requiere_revision_medica"
        assert len(body["interactions"]) == 1

    def test_no_interaction_is_fit(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/pharmacy/check-interactions",
            json={"drugs": ["Paracetamol", "Omeprazol"]},
        )

        assert response.status_code == 200
        assert response.json() == {"interactions": [], "verdict": "apto"}

    def test_rejects_single_drug(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/pharmacy/check-interactions", json={"drugs": ["Paracetamol"]}
        )

        assert response.status_code == 422


class TestAnalyzePrescriptionEndpoint:
    def test_analyzes_uploaded_image(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/pharmacy/analyze-prescription",
            files={"file": ("receta.jpg", b"fake-image-bytes", "image/jpeg")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["drugs"] == [
            {
                "farmaco": "Ibuprofeno",
                "dosificacion": "600 mg",
                "frecuencia": "cada 8 horas",
                "duracion": "5 días",
            }
        ]
        assert body["advertencias"] == ["Tomar con alimentos."]

    def test_requires_a_file(self, client: TestClient) -> None:
        response = client.post("/api/v1/pharmacy/analyze-prescription")

        assert response.status_code == 422
