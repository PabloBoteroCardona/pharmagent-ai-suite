"""Endpoints REST de farmacia: búsqueda semántica y consulta al `RAGPharmAgent`."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.agents import PrescriptionAgent, RAGPharmAgent, SafetyCheckAgent
from src.application.services import DrugService
from src.infrastructure.api.schemas.drug_schemas import (
    ConsultationRequest,
    ConsultationResponse,
    DrugSearchQuery,
    InteractionCheckRequest,
    InteractionCheckResponse,
    PrescriptionAnalysisResponse,
    ProcessPrescriptionResponse,
)
from src.infrastructure.api.security import verify_api_key
from src.infrastructure.database import get_db_session
from src.infrastructure.external.cima_client import CimaAPIClient
from src.infrastructure.external.gemini_client import GeminiClient
from src.infrastructure.external.ollama_client import OllamaClient
from src.infrastructure.repositories import DrugRepository, PrescriptionRecordRepository
from src.use_cases.consult_drug_rag import ConsultDrugRAGUseCase
from src.use_cases.process_prescription import ProcessPrescriptionUseCase

router = APIRouter(
    prefix="/api/v1/pharmacy",
    tags=["pharmacy"],
    dependencies=[Depends(verify_api_key)],
)


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


def get_gemini_client() -> GeminiClient:
    return GeminiClient()


def get_prescription_agent(
    gemini_client: GeminiClient = Depends(get_gemini_client),  # noqa: B008
) -> PrescriptionAgent:
    return PrescriptionAgent(vision_client=gemini_client)


def get_safety_check_agent(
    ollama_client: OllamaClient = Depends(get_ollama_client),  # noqa: B008
) -> SafetyCheckAgent:
    return SafetyCheckAgent(language_model=ollama_client)


def get_prescription_record_repository(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> PrescriptionRecordRepository:
    return PrescriptionRecordRepository(session)


def get_process_prescription_use_case(
    prescription_agent: PrescriptionAgent = Depends(get_prescription_agent),  # noqa: B008
    safety_agent: SafetyCheckAgent = Depends(get_safety_check_agent),  # noqa: B008
    record_repository: PrescriptionRecordRepository = Depends(  # noqa: B008
        get_prescription_record_repository
    ),
) -> ProcessPrescriptionUseCase:
    return ProcessPrescriptionUseCase(
        prescription_agent=prescription_agent,
        safety_agent=safety_agent,
        record_repository=record_repository,
    )


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


@router.post("/analyze-prescription", response_model=PrescriptionAnalysisResponse)
async def analyze_prescription(
    file: UploadFile = File(...),  # noqa: B008
    agent: PrescriptionAgent = Depends(get_prescription_agent),  # noqa: B008
) -> PrescriptionAnalysisResponse:
    image_bytes = await file.read()
    result = await agent.extract_prescription(
        image_bytes, mime_type=file.content_type or "image/jpeg"
    )
    return PrescriptionAnalysisResponse(**result)


@router.post("/check-interactions", response_model=InteractionCheckResponse)
async def check_interactions(
    payload: InteractionCheckRequest,
    agent: SafetyCheckAgent = Depends(get_safety_check_agent),  # noqa: B008
) -> InteractionCheckResponse:
    result = await agent.check_interactions(payload.drugs)
    return InteractionCheckResponse(**result)


@router.post("/process-prescription", response_model=ProcessPrescriptionResponse)
async def process_prescription(
    file: UploadFile = File(...),  # noqa: B008
    use_case: ProcessPrescriptionUseCase = Depends(  # noqa: B008
        get_process_prescription_use_case
    ),
) -> ProcessPrescriptionResponse:
    """Flujo completo: extrae los fármacos de la imagen de la receta y, si hay 2 o más,
    verifica automáticamente sus interacciones conocidas."""
    image_bytes = await file.read()
    result = await use_case.execute(
        image_bytes, mime_type=file.content_type or "image/jpeg"
    )
    return ProcessPrescriptionResponse(**result)
