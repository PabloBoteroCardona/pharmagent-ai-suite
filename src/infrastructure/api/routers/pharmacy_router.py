"""Endpoints REST de farmacia: búsqueda semántica y consulta al `RAGPharmAgent`."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.agents import RAGPharmAgent
from src.application.services import DrugService
from src.infrastructure.api.schemas.drug_schemas import (
    ConsultationRequest,
    ConsultationResponse,
    DrugSearchQuery,
)
from src.infrastructure.database import get_db_session
from src.infrastructure.external.cima_client import CimaAPIClient
from src.infrastructure.external.ollama_client import OllamaClient
from src.infrastructure.repositories import DrugRepository
from src.use_cases.consult_drug_rag import ConsultDrugRAGUseCase

router = APIRouter(prefix="/api/v1/pharmacy", tags=["pharmacy"])


async def get_cima_client() -> AsyncGenerator[CimaAPIClient, None]:
    async with CimaAPIClient() as client:
        yield client


async def get_ollama_client() -> AsyncGenerator[OllamaClient, None]:
    async with OllamaClient() as client:
        yield client


def get_drug_repository(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> DrugRepository:
    return DrugRepository(session)


def get_drug_service(
    cima_client: CimaAPIClient = Depends(get_cima_client),  # noqa: B008
    ollama_client: OllamaClient = Depends(get_ollama_client),  # noqa: B008
    drug_repo: DrugRepository = Depends(get_drug_repository),  # noqa: B008
) -> DrugService:
    return DrugService(
        cima_client=cima_client, ollama_client=ollama_client, drug_repo=drug_repo
    )


def get_rag_pharm_agent(
    drug_service: DrugService = Depends(get_drug_service),  # noqa: B008
    ollama_client: OllamaClient = Depends(get_ollama_client),  # noqa: B008
) -> RAGPharmAgent:
    return RAGPharmAgent(drug_service=drug_service, ollama_client=ollama_client)


def get_consult_drug_rag_use_case(
    agent: RAGPharmAgent = Depends(get_rag_pharm_agent),  # noqa: B008
) -> ConsultDrugRAGUseCase:
    return ConsultDrugRAGUseCase(rag_agent=agent)


@router.post("/search")
async def search_drugs(
    payload: DrugSearchQuery,
    drug_service: DrugService = Depends(get_drug_service),  # noqa: B008
) -> list[dict]:
    drugs = await drug_service.search_drugs_semantic(payload.query, limit=payload.limit)
    return [
        {
            "nregistro": drug.nregistro,
            "nombre": drug.nombre,
            "pactivos": drug.pactivos,
            "labtitular": drug.labtitular,
        }
        for drug in drugs
    ]


@router.post("/consult", response_model=ConsultationResponse)
async def consult(
    payload: ConsultationRequest,
    use_case: ConsultDrugRAGUseCase = Depends(get_consult_drug_rag_use_case),  # noqa: B008
) -> ConsultationResponse:
    result = await use_case.execute(payload.query)
    return ConsultationResponse(**result)
