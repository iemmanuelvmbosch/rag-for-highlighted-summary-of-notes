from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    success: bool
    total_records_from_api: int
    total_meetings_filtered: int
    total_documents_indexed: int
    total_collections_used: int
    collections_used: list[str]
    filter_applied: bool
    filter_start_date: str | None = None
    filter_end_date: str | None = None
    date_scope: str
    message: str


class SyncResponse(BaseModel):
    success: bool
    total_records_from_api: int
    total_meetings_filtered: int
    total_documents_found: int
    new_documents: int
    updated_documents: int
    unchanged_documents: int
    total_collections_used: int
    collections_used: list[str]
    filter_applied: bool
    filter_start_date: str | None = None
    filter_end_date: str | None = None
    date_scope: str
    message: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2)
    top_k: int = Field(default=10, ge=1, le=100)

    date: str | None = Field(
        default=None,
        description="Fecha opcional para forzar día. Ejemplo: 2026-02-17.",
    )

    year_month: str | None = Field(
        default=None,
        description="Mes opcional para forzar colección. Ejemplo: 2026-02 o febrero de 2026.",
    )

    mode: Literal["auto", "day", "month", "semantic"] = Field(
        default="auto",
        description=(
            "auto = detecta día o mes desde la pregunta. "
            "day = busca reuniones completas del día. "
            "month = busca reuniones completas del mes. "
            "semantic = búsqueda vectorial normal."
        ),
    )


class AskTextResponse(BaseModel):
    content: str
    format: str = "markdown"


class SourceItem(BaseModel):
    id: str
    collection_name: str | None = None
    collection_key: str | None = None
    document_type: str | None = None
    meeting_id: int | None = None
    meeting_title: str | None = None
    meeting_status: str | None = None
    meeting_start_date: str | None = None
    meeting_year_month: str | None = None
    topic_name: str | None = None
    note_type: str | None = None
    activity_status: str | None = None
    distance: float | None = None
    text_preview: str


class AskResponse(BaseModel):
    answer: str
    temporal_period: str | None = None
    temporal_date: str | None = None
    temporal_year_month: str | None = None
    sources: list[SourceItem]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=10, ge=1, le=100)

    year_month: str | None = Field(
        default=None,
        description="Opcional. Si se manda, busca solo en esa colección mensual. Ejemplo: 2026-03.",
    )


class SearchResponse(BaseModel):
    results: list[SourceItem]


class HealthResponse(BaseModel):
    status: str
    total_collections: int
    collections: list[dict]


class DebugConnectionResponse(BaseModel):
    meettrack: dict
    openai: dict
