from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.database.sql_server import test_sql_server_connection
from app.schemas.rag_schema import (
    AskRequest,
    AskResponse,
    AskTextResponse,
    ChatHistoryPaginatedResponse,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SyncResponse,
)
from app.services.chat_history_service import ChatHistoryService
from app.services.meettrack_client_service import MeetTrackClientService
from app.services.openai_service import OpenAIService
from app.services.rag_service import RagService
from app.utils.question_guard import classify_question

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/rag",
    tags=["rag"],
)


def _save_chat_history_safe(
    username_fk: str,
    question: str,
    response_content: str,
    response_format: str = "markdown",
    response_status: str = "success",
) -> int | None:
    try:
        return ChatHistoryService.create_history(
            username_fk=username_fk,
            question=question,
            response_content=response_content,
            response_format=response_format,
            response_status=response_status,
        )

    except Exception as error:
        logger.exception("Error saving chatbot history: %s", str(error))
        return None


def _clip_text(value: str, max_chars: int = 4000) -> str:
    text = value or ""

    if len(text) <= max_chars:
        return text

    return text[-max_chars:]


def _build_conversation_context(payload: AskRequest) -> str:
    pre_guard = classify_question(
        question=payload.question,
        has_conversation_context=bool(payload.context_history_id),
        has_explicit_date_filter=bool(payload.date),
        has_explicit_year_month_filter=bool(payload.year_month),
        mode=payload.mode,
    )

    if not pre_guard.use_conversation_context:
        return ""

    blocks: list[str] = []

    try:
        selected_history_id = payload.context_history_id

        if selected_history_id:
            selected = ChatHistoryService.get_history_by_id(
                username_fk=payload.username_fk,
                id_history=selected_history_id,
            )

            if selected:
                blocks.append(
                    f"""
Mensaje seleccionado como contexto:
Pregunta anterior:
{_clip_text(selected["question"], 2000)}

Respuesta anterior:
{_clip_text(selected["response_content"], 6000)}
""".strip()
                )

        if payload.include_recent_history and payload.history_limit > 0:
            recent_items = ChatHistoryService.get_recent_history(
                username_fk=payload.username_fk,
                limit=payload.history_limit,
            )

            if recent_items:
                lines = ["Historial reciente de conversación:"]

                for item in recent_items:
                    if (
                        selected_history_id
                        and item.get("id_history") == selected_history_id
                    ):
                        continue

                    if item.get("response_status") == "error":
                        continue

                    lines.append(
                        f"""
Pregunta:
{_clip_text(item["question"], 1000)}

Respuesta:
{_clip_text(item["response_content"], 3000)}
""".strip()
                    )

                if len(lines) > 1:
                    blocks.append("\n\n---\n\n".join(lines))

    except Exception as error:
        logger.exception(
            "Error building conversation context: %s",
            str(error),
        )

    context = "\n\n==========\n\n".join(blocks)

    return context[-10000:]


@router.post("/ingest", response_model=IngestResponse)
def ingest_meettrack_data(
    reset: bool = Query(
        default=True,
        description=(
            "If true, resets everything when no filter is provided. "
            "If a filter is provided, only filtered documents are deleted and reindexed."
        ),
    ),
    date: str | None = Query(
        default=None,
        description="Exact date to index. Example: 2026-02-17.",
    ),
    start_date: str | None = Query(
        default=None,
        description="Start of the date range. Example: 2026-02-01.",
    ),
    end_date: str | None = Query(
        default=None,
        description="End of the date range. Example: 2026-02-29.",
    ),
    year_month: str | None = Query(
        default=None,
        description="Full month. Example: 2026-02 or February 2026.",
    ),
    date_scope: Literal["meeting", "related"] = Query(
        default="meeting",
        description=(
            "meeting = filters by meeting date. "
            "related = filters by meeting date, created notes, targetDate, or completedAt."
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
            message="Ingest completed in Chroma using month-year collections.",
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error indexing data: {str(error)}",
        )


@router.post("/sync", response_model=SyncResponse)
def sync_meettrack_data(
    date: str | None = Query(
        default=None,
        description="Exact date to sync. Example: 2026-02-17.",
    ),
    start_date: str | None = Query(
        default=None,
        description="Start of the date range. Example: 2026-02-01.",
    ),
    end_date: str | None = Query(
        default=None,
        description="End of the date range. Example: 2026-02-29.",
    ),
    year_month: str | None = Query(
        default=None,
        description="Full month. Example: 2026-02 or February 2026.",
    ),
    date_scope: Literal["meeting", "related"] = Query(
        default="meeting",
        description=(
            "meeting = filters by meeting date. "
            "related = filters by meeting date, created notes, targetDate, or completedAt."
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
            message=(
                "Sync completed. Existing documents for the affected meetings were refreshed."
            ),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing data: {str(error)}",
        )


@router.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest):
    try:
        conversation_context = _build_conversation_context(payload)

        service = RagService()
        result = service.ask(
            question=payload.question,
            top_k=payload.top_k,
            date_filter=payload.date,
            year_month_filter=payload.year_month,
            mode=payload.mode,
            conversation_context=conversation_context,
        )

        id_history = _save_chat_history_safe(
            username_fk=payload.username_fk,
            question=payload.question,
            response_content=result["answer"],
            response_format="markdown",
            response_status="success",
        )

        return AskResponse(
            answer=result["answer"],
            temporal_period=result["temporal_period"],
            temporal_date=result["temporal_date"],
            temporal_year_month=result["temporal_year_month"],
            sources=result["sources"],
            id_history=id_history,
        )

    except Exception as error:
        _save_chat_history_safe(
            username_fk=payload.username_fk,
            question=payload.question,
            response_content=str(error),
            response_format="markdown",
            response_status="error",
        )

        raise HTTPException(
            status_code=500,
            detail=f"Error querying the RAG: {str(error)}",
        )


@router.post("/ask-text", response_model=AskTextResponse)
def ask_question_text(payload: AskRequest):
    try:
        conversation_context = _build_conversation_context(payload)

        service = RagService()
        result = service.ask(
            question=payload.question,
            top_k=payload.top_k,
            date_filter=payload.date,
            year_month_filter=payload.year_month,
            mode=payload.mode,
            conversation_context=conversation_context,
        )

        id_history = _save_chat_history_safe(
            username_fk=payload.username_fk,
            question=payload.question,
            response_content=result["answer"],
            response_format="markdown",
            response_status="success",
        )

        return AskTextResponse(
            content=result["answer"],
            format="markdown",
            id_history=id_history,
        )

    except Exception as error:
        _save_chat_history_safe(
            username_fk=payload.username_fk,
            question=payload.question,
            response_content=str(error),
            response_format="markdown",
            response_status="error",
        )

        raise HTTPException(
            status_code=500,
            detail=f"Error querying the RAG: {str(error)}",
        )


@router.get("/chat-history", response_model=ChatHistoryPaginatedResponse)
def get_chat_history_by_user(
    username_fk: str = Query(
        ...,
        min_length=1,
        description="User who owns the history.",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number. Starts at 1.",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of records per page. Maximum 100.",
    ),
):
    try:
        return ChatHistoryService.get_paginated_history_by_user(
            username_fk=username_fk,
            page=page,
            page_size=page_size,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting chat history: {str(error)}",
        )


@router.get("/debug/connections")
def debug_connections():
    meettrack_result = MeetTrackClientService.test_connection()
    openai_result = OpenAIService().test_connection()
    sql_server_result = test_sql_server_connection()

    return {
        "meettrack": meettrack_result,
        "openai": openai_result,
        "sql_server": sql_server_result,
    }


@router.delete("/reset")
def reset_collection():
    try:
        service = RagService()
        return service.reset()

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting Chroma: {str(error)}",
        )
