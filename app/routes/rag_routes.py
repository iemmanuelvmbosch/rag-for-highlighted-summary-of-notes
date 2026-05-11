from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.schemas.rag_schema import (
    AskRequest,
    AskResponse,
    AskTextResponse,
    HealthResponse,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SyncResponse,
)
from app.services.meettrack_client_service import MeetTrackClientService
from app.services.openai_service import OpenAIService
from app.services.rag_service import RagService

router = APIRouter(
    prefix="/api/rag",
    tags=["rag"],
)


@router.post("/ingest", response_model=IngestResponse)
def ingest_meettrack_data(
    reset: bool = Query(
        default=True,
        description="Si es true, reinicia todo cuando no hay filtro. Si hay filtro, solo borra/reindexa documentos filtrados.",
    ),
    date: str | None = Query(
        default=None,
        description="Fecha exacta para indexar. Ejemplo: 2026-02-17.",
    ),
    start_date: str | None = Query(
        default=None,
        description="Inicio del rango. Ejemplo: 2026-02-01.",
    ),
    end_date: str | None = Query(
        default=None,
        description="Fin del rango. Ejemplo: 2026-02-29.",
    ),
    year_month: str | None = Query(
        default=None,
        description="Mes completo. Ejemplo: 2026-02 o febrero de 2026.",
    ),
    date_scope: Literal["meeting", "related"] = Query(
        default="meeting",
        description=(
            "meeting = filtra por fecha de la reunión. "
            "related = filtra por fecha de reunión, notas creadas, targetDate o completedAt."
        ),
    ),
):
    try:
        service = RagService()
        result = service.ingest_from_meettrack(
            reset=reset,
            date=date,
            start_date=start_date,
            end_date=end_date,
            year_month=year_month,
            date_scope=date_scope,
        )

        return IngestResponse(
            success=True,
            total_records_from_api=result["total_records_from_api"],
            total_meetings_filtered=result["total_meetings_filtered"],
            total_documents_indexed=result["total_documents_indexed"],
            total_collections_used=result["total_collections_used"],
            collections_used=result["collections_used"],
            filter_applied=result["filter_applied"],
            filter_start_date=result["filter_start_date"],
            filter_end_date=result["filter_end_date"],
            date_scope=result["date_scope"],
            message="Ingest completado en Chroma usando colecciones por mes-año.",
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error al indexar datos: {str(error)}",
        )


@router.post("/sync", response_model=SyncResponse)
def sync_meettrack_data(
    date: str | None = Query(
        default=None,
        description="Fecha exacta para sincronizar. Ejemplo: 2026-02-17.",
    ),
    start_date: str | None = Query(
        default=None,
        description="Inicio del rango. Ejemplo: 2026-02-01.",
    ),
    end_date: str | None = Query(
        default=None,
        description="Fin del rango. Ejemplo: 2026-02-29.",
    ),
    year_month: str | None = Query(
        default=None,
        description="Mes completo. Ejemplo: 2026-02 o febrero de 2026.",
    ),
    date_scope: Literal["meeting", "related"] = Query(
        default="meeting",
        description=(
            "meeting = filtra por fecha de la reunión. "
            "related = filtra por fecha de reunión, notas creadas, targetDate o completedAt."
        ),
    ),
):
    try:
        service = RagService()
        result = service.sync_from_meettrack(
            date=date,
            start_date=start_date,
            end_date=end_date,
            year_month=year_month,
            date_scope=date_scope,
        )

        return SyncResponse(
            success=True,
            total_records_from_api=result["total_records_from_api"],
            total_meetings_filtered=result["total_meetings_filtered"],
            total_documents_found=result["total_documents_found"],
            new_documents=result["new_documents"],
            updated_documents=result["updated_documents"],
            unchanged_documents=result["unchanged_documents"],
            total_collections_used=result["total_collections_used"],
            collections_used=result["collections_used"],
            filter_applied=result["filter_applied"],
            filter_start_date=result["filter_start_date"],
            filter_end_date=result["filter_end_date"],
            date_scope=result["date_scope"],
            message="Sync completado. Solo se procesaron documentos nuevos o modificados dentro del filtro indicado.",
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error al sincronizar datos: {str(error)}",
        )


@router.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest):
    try:
        service = RagService()
        result = service.ask(
            question=payload.question,
            top_k=payload.top_k,
            date_filter=payload.date,
            year_month_filter=payload.year_month,
            mode=payload.mode,
        )

        return AskResponse(
            answer=result["answer"],
            temporal_period=result["temporal_period"],
            temporal_date=result["temporal_date"],
            temporal_year_month=result["temporal_year_month"],
            sources=result["sources"],
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error al consultar el RAG: {str(error)}",
        )


@router.post("/ask-text", response_model=AskTextResponse)
def ask_question_text(payload: AskRequest):
    try:
        service = RagService()
        result = service.ask(
            question=payload.question,
            top_k=payload.top_k,
            date_filter=payload.date,
            year_month_filter=payload.year_month,
            mode=payload.mode,
        )

        return AskTextResponse(
            content=result["answer"],
            format="markdown",
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error al consultar el RAG: {str(error)}",
        )


@router.post("/search", response_model=SearchResponse)
def search_documents(payload: SearchRequest):
    try:
        service = RagService()
        results = service.search(
            query=payload.query,
            top_k=payload.top_k,
            year_month=payload.year_month,
        )

        return SearchResponse(
            results=[service._to_source_item(result) for result in results]
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error al buscar documentos en Chroma: {str(error)}",
        )


@router.get("/health", response_model=HealthResponse)
def health():
    try:
        service = RagService()
        result = service.health()

        return HealthResponse(
            status=result["status"],
            total_collections=result["total_collections"],
            collections=result["collections"],
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error en health check del RAG: {str(error)}",
        )


@router.get("/debug/connections")
def debug_connections():
    meettrack_result = MeetTrackClientService.test_connection()
    openai_result = OpenAIService().test_connection()

    return {
        "meettrack": meettrack_result,
        "openai": openai_result,
    }


@router.delete("/reset")
def reset_collection():
    try:
        service = RagService()
        return service.reset()

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error al reiniciar Chroma: {str(error)}",
        )
