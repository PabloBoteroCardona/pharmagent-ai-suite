"""Tests de integración de los endpoints REST de `pharmacy_router.py`.

Ejercitan la aplicación FastAPI real (`TestClient`) con las dependencias de
infraestructura sustituidas por dobles en memoria (ver `conftest.py`) — validan el
cableado completo de rutas, esquemas Pydantic y capas de aplicación, sin depender de
CIMA, Ollama, PostgreSQL ni Gemini reales.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.api import security
from src.infrastructure.api.main import app
from src.infrastructure.api.routers.pharmacy_router import (
    get_cima_client,
    get_drug_repository,
)
from tests.integration.conftest import (
    FAKE_DRUG,
    FAKE_LIVE_DRUG_DETAIL,
    FAKE_LIVE_DRUG_SEARCH_RESULT,
    FAKE_RAG_RESPONSE_TEXT,
    FakeCimaClient,
    FakeDrugRepository,
)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSearchEndpoint:
    def test_search_returns_matching_drugs_from_cache(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/pharmacy/search", json={"query": "dolor de cabeza", "limit": 3}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "cache"
        assert body["results"] == [
            {
                "nregistro": FAKE_DRUG.nregistro,
                "nombre": FAKE_DRUG.nombre,
                "pactivos": FAKE_DRUG.pactivos,
                "labtitular": FAKE_DRUG.labtitular,
            }
        ]

    def test_search_falls_back_to_live_cima_when_cache_is_empty(
        self, client: TestClient
    ) -> None:
        """Con la caché vacía (fármaco no indexado todavía), `/search` debe consultar
        CIMA en vivo automáticamente en vez de devolver una lista vacía."""
        app.dependency_overrides[get_drug_repository] = lambda: FakeDrugRepository(
            cached_results=[]
        )
        app.dependency_overrides[get_cima_client] = lambda: FakeCimaClient(
            search_results=[FAKE_LIVE_DRUG_SEARCH_RESULT],
            medicamento_detail=FAKE_LIVE_DRUG_DETAIL,
        )

        response = client.post(
            "/api/v1/pharmacy/search", json={"query": "paracetamol", "limit": 3}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "live"
        assert body["results"] == [
            {
                "nregistro": FAKE_LIVE_DRUG_DETAIL["nregistro"],
                "nombre": FAKE_LIVE_DRUG_DETAIL["nombre"],
                "pactivos": FAKE_LIVE_DRUG_DETAIL["pactivos"],
                "labtitular": FAKE_LIVE_DRUG_DETAIL["labtitular"],
            }
        ]

    def test_search_returns_none_source_when_neither_cache_nor_cima_have_it(
        self, client: TestClient
    ) -> None:
        app.dependency_overrides[get_drug_repository] = lambda: FakeDrugRepository(
            cached_results=[]
        )
        app.dependency_overrides[get_cima_client] = lambda: FakeCimaClient(
            search_results=[]
        )

        response = client.post(
            "/api/v1/pharmacy/search",
            json={"query": "farmacoinexistentexyz", "limit": 3},
        )

        assert response.status_code == 200
        body = response.json()
        assert body == {"results": [], "source": "none"}

    def test_search_rejects_empty_query(self, client: TestClient) -> None:
        response = client.post("/api/v1/pharmacy/search", json={"query": ""})

        assert response.status_code == 422


class TestConsultEndpoint:
    def test_consult_returns_grounded_answer_from_cache(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/pharmacy/consult",
            json={"query": "¿cómo se toma el ibuprofeno?"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "¿cómo se toma el ibuprofeno?"
        assert body["response"] == FAKE_RAG_RESPONSE_TEXT
        assert body["sources"] == [FAKE_DRUG.nombre]
        assert body["source"] == "cache"

    def test_consult_falls_back_to_live_cima_using_drug_name(
        self, client: TestClient
    ) -> None:
        """Sin el fármaco en caché, pero indicando `drug_name`, `/consult` debe
        encontrarlo en vivo en CIMA y usarlo como contexto de la respuesta."""
        app.dependency_overrides[get_drug_repository] = lambda: FakeDrugRepository(
            cached_results=[]
        )
        app.dependency_overrides[get_cima_client] = lambda: FakeCimaClient(
            search_results=[FAKE_LIVE_DRUG_SEARCH_RESULT],
            medicamento_detail=FAKE_LIVE_DRUG_DETAIL,
        )

        response = client.post(
            "/api/v1/pharmacy/consult",
            json={
                "query": "¿qué dosis es adecuada?",
                "drug_name": "paracetamol",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "live"
        assert body["sources"] == [FAKE_LIVE_DRUG_DETAIL["nombre"]]

    def test_consult_rejects_empty_query(self, client: TestClient) -> None:
        response = client.post("/api/v1/pharmacy/consult", json={"query": ""})

        assert response.status_code == 422


class TestCheckInteractionsEndpoint:
    def test_detects_severe_interaction_from_curated_table(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/pharmacy/check-interactions",
            json={"drugs": ["Warfarina", "Aspirina"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "requiere_revision_medica"
        assert len(body["interactions"]) == 1
        assert body["interactions"][0]["source"] == "curated"

    def test_uncovered_pair_falls_back_to_llm_and_is_fit(
        self, client: TestClient
    ) -> None:
        """`Paracetamol`+`Omeprazol` no está en la base curada — el fake de Ollama en
        conftest.py simula que el modelo no encuentra ninguna interacción."""
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


class TestProcessPrescriptionEndpoint:
    """El fake `GeminiClient` (ver conftest.py) siempre devuelve un único fármaco
    (Ibuprofeno), así que aquí no se dispara la verificación de interacciones
    automática (requiere 2+) — ese camino ya se cubre a nivel unitario en
    `tests/unit/test_process_prescription_use_case.py`."""

    def test_processes_uploaded_image_without_triggering_safety_check(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/pharmacy/process-prescription",
            files={"file": ("receta.jpg", b"fake-image-bytes", "image/jpeg")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["prescription"]["drugs"] == [
            {
                "farmaco": "Ibuprofeno",
                "dosificacion": "600 mg",
                "frecuencia": "cada 8 horas",
                "duracion": "5 días",
            }
        ]
        assert body["safety_check"] is None

    def test_requires_a_file(self, client: TestClient) -> None:
        response = client.post("/api/v1/pharmacy/process-prescription")

        assert response.status_code == 422


class TestApiKeyAuthentication:
    """Con `settings.api_key` configurada, los endpoints de `pharmacy_router` exigen
    la cabecera `X-API-Key`. `/health` queda fuera del router protegido a propósito
    (usado por *healthchecks* de infraestructura sin credenciales)."""

    def test_rejects_request_without_api_key(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(security.settings, "api_key", "secret-key")

        response = client.post(
            "/api/v1/pharmacy/check-interactions",
            json={"drugs": ["Paracetamol", "Omeprazol"]},
        )

        assert response.status_code == 401

    def test_rejects_request_with_wrong_api_key(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(security.settings, "api_key", "secret-key")

        response = client.post(
            "/api/v1/pharmacy/check-interactions",
            json={"drugs": ["Paracetamol", "Omeprazol"]},
            headers={"X-API-Key": "wrong-key"},
        )

        assert response.status_code == 401

    def test_accepts_request_with_correct_api_key(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(security.settings, "api_key", "secret-key")

        response = client.post(
            "/api/v1/pharmacy/check-interactions",
            json={"drugs": ["Paracetamol", "Omeprazol"]},
            headers={"X-API-Key": "secret-key"},
        )

        assert response.status_code == 200

    def test_health_endpoint_never_requires_api_key(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(security.settings, "api_key", "secret-key")

        response = client.get("/health")

        assert response.status_code == 200
