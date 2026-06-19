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
    username_fk: str = Field(
        ...,
        min_length=1,
        description="Username used to save the question history.",
    )

    question: str = Field(..., min_length=2)
    top_k: int = Field(default=10, ge=1, le=100)

    date: str | None = Field(
        default=None,
        description="Optional date to force a specific day. Example: 2026-02-17.",
    )

    year_month: str | None = Field(
        default=None,
        description="Optional month to force a collection. Example: 2026-02 or February 2026.",
    )

    mode: Literal["auto", "day", "month", "semantic"] = Field(
        default="auto",
        description=(
            "auto = detects day or month from the question. "
            "day = searches complete meetings for the day. "
            "month = searches complete meetings for the month. "
            "semantic = regular vector search."
        ),
    )

    context_history_id: int | None = Field(
        default=None,
        description=(
            "Optional id_history of a previous assistant response to use as context."
        ),
    )

    include_recent_history: bool = Field(
        default=True,
        description=(
            "If true, includes recent chat history from the same user."
        ),
    )

    history_limit: int = Field(
        default=6,
        ge=0,
        le=20,
        description="Number of recent history items to include as conversation context.",
    )


class AskTextResponse(BaseModel):
    content: str
    format: str = "markdown"
    id_history: int | None = None


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
    id_history: int | None = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=10, ge=1, le=100)

    year_month: str | None = Field(
        default=None,
        description="Optional. If provided, searches documents related to that month. Example: 2026-03.",
    )


class SearchResponse(BaseModel):
    results: list[SourceItem]


class DebugConnectionResponse(BaseModel):
    meettrack: dict
    openai: dict
    sql_server: dict


class ChatHistoryItem(BaseModel):
    id_history: int
    username_fk: str
    question: str
    response_content: str
    response_format: str
    response_status: str
    created_at: str
    updated_at: str


class ChatHistoryPaginatedResponse(BaseModel):
    items: list[ChatHistoryItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
