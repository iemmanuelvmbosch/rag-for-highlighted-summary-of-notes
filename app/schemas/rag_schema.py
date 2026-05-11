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
        description="Optional. If provided, searches only in that monthly collection. Example: 2026-03.",
    )


class SearchResponse(BaseModel):
    results: list[SourceItem]


class DebugConnectionResponse(BaseModel):
    meettrack: dict
    openai: dict
