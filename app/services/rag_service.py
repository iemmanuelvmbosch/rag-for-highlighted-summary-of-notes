from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Literal

from app.database.chroma import (
    delete_all_rag_collections,
    get_all_rag_collections,
    get_collection_name_for_key,
    get_existing_rag_collection,
    get_rag_collection,
)
from app.models.rag_models import RagDocument, RagSearchResult
from app.rag.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas.rag_schema import SourceItem
from app.services.document_builder_service import DocumentBuilderService
from app.services.meettrack_client_service import MeetTrackClientService
from app.services.service_factory import get_openai_service
from app.utils.settings import get_settings
from app.utils.text_utils import (
    build_date_range_filter,
    collection_key_from_year_month,
    extract_temporal_filter,
    meeting_matches_date_range,
    normalize_date,
    normalize_year_month,
)
from app.utils.question_guard import (
    build_out_of_scope_answer,
    classify_question,
)

logger = logging.getLogger(__name__)


class RagService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.openai_service = get_openai_service()

    def ingest_from_meettrack(
        self,
        reset: bool = True,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        year_month: str | None = None,
        date_scope: Literal["meeting", "related"] = "meeting",
    ) -> dict:
        api_response = MeetTrackClientService.fetch_train_data()

        filtered_response, filter_info = self._filter_api_response_by_date_range(
            api_response=api_response,
            date=date,
            start_date=start_date,
            end_date=end_date,
            year_month=year_month,
            date_scope=date_scope,
        )

        documents = DocumentBuilderService.build_documents(filtered_response)

        if reset and not filter_info["filter_applied"]:
            delete_all_rag_collections()

        if reset and filter_info["filter_applied"] and documents:
            self._delete_documents_for_meetings(documents)

        collections_used = self._upsert_documents_grouped_by_collection(
            documents
        )

        return {
            "total_records_from_api": api_response.get("totalRecords", 0),
            "total_meetings_filtered": len(filtered_response.get("data", [])),
            "total_documents_indexed": len(documents),
            "total_collections_used": len(collections_used),
            "collections_used": collections_used,
            "filter_applied": filter_info["filter_applied"],
            "filter_start_date": filter_info["filter_start_date"],
            "filter_end_date": filter_info["filter_end_date"],
            "date_scope": date_scope,
        }

    def sync_from_meettrack(
        self,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        year_month: str | None = None,
        date_scope: Literal["meeting", "related"] = "meeting",
    ) -> dict:
        api_response = MeetTrackClientService.fetch_train_data()

        filtered_response, filter_info = self._filter_api_response_by_date_range(
            api_response=api_response,
            date=date,
            start_date=start_date,
            end_date=end_date,
            year_month=year_month,
            date_scope=date_scope,
        )

        documents = DocumentBuilderService.build_documents(filtered_response)

        if not documents:
            return {
                "total_records_from_api": api_response.get("totalRecords", 0),
                "total_meetings_filtered": len(filtered_response.get("data", [])),
                "total_documents_found": 0,
                "new_documents": 0,
                "updated_documents": 0,
                "unchanged_documents": 0,
                "total_collections_used": 0,
                "collections_used": [],
                "filter_applied": filter_info["filter_applied"],
                "filter_start_date": filter_info["filter_start_date"],
                "filter_end_date": filter_info["filter_end_date"],
                "date_scope": date_scope,
            }

        self._delete_documents_for_meetings(documents)

        collections_used = self._upsert_documents_grouped_by_collection(
            documents
        )

        return {
            "total_records_from_api": api_response.get("totalRecords", 0),
            "total_meetings_filtered": len(filtered_response.get("data", [])),
            "total_documents_found": len(documents),
            "new_documents": len(documents),
            "updated_documents": 0,
            "unchanged_documents": 0,
            "total_collections_used": len(collections_used),
            "collections_used": collections_used,
            "filter_applied": filter_info["filter_applied"],
            "filter_start_date": filter_info["filter_start_date"],
            "filter_end_date": filter_info["filter_end_date"],
            "date_scope": date_scope,
        }

    def _filter_api_response_by_date_range(
        self,
        api_response: dict,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        year_month: str | None = None,
        date_scope: Literal["meeting", "related"] = "meeting",
    ) -> tuple[dict, dict]:
        meetings = api_response.get("data", [])

        if not isinstance(meetings, list):
            raise ValueError(
                "La propiedad 'data' debe ser una lista de reuniones."
            )

        date_filter = build_date_range_filter(
            date=date,
            start_date=start_date,
            end_date=end_date,
            year_month=year_month,
        )

        if not date_filter.filter_applied:
            return api_response, {
                "filter_applied": False,
                "filter_start_date": None,
                "filter_end_date": None,
            }

        filtered_meetings = [
            meeting
            for meeting in meetings
            if meeting_matches_date_range(
                meeting=meeting,
                date_filter=date_filter,
                date_scope=date_scope,
            )
        ]

        filtered_response = {
            **api_response,
            "totalRecords": len(filtered_meetings),
            "data": filtered_meetings,
        }

        return filtered_response, {
            "filter_applied": True,
            "filter_start_date": date_filter.start_date,
            "filter_end_date": date_filter.end_date,
        }

    def _group_documents_by_collection_key(
        self,
        documents: list[RagDocument],
    ) -> dict[str, list[RagDocument]]:
        grouped: dict[str, list[RagDocument]] = defaultdict(list)

        for doc in documents:
            collection_key = str(
                doc.metadata.get("collection_key") or "unknown"
            )
            grouped[collection_key].append(doc)

        return grouped

    def _upsert_documents_grouped_by_collection(
        self,
        documents: list[RagDocument],
    ) -> list[str]:
        if not documents:
            return []

        grouped_documents = self._group_documents_by_collection_key(documents)

        collections_used: list[str] = []

        for collection_key, docs in grouped_documents.items():
            collection = get_rag_collection(collection_key)
            collection_name = get_collection_name_for_key(collection_key)

            self._upsert_documents(collection=collection, documents=docs)
            collections_used.append(collection_name)

        return sorted(collections_used)

    def _upsert_documents(self, collection, documents: list[RagDocument]) -> None:
        valid_documents = [
            doc for doc in documents if doc.text and doc.text.strip()
        ]

        if not valid_documents:
            return

        ids = [doc.id for doc in valid_documents]
        texts = [doc.text for doc in valid_documents]
        metadatas = [doc.metadata for doc in valid_documents]

        embeddings = self.openai_service.embed_texts(texts)

        if len(embeddings) != len(valid_documents):
            raise ValueError(
                "La cantidad de embeddings generados no coincide con la cantidad de documentos."
            )

        collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def _delete_documents_for_meetings(
        self,
        documents: list[RagDocument],
    ) -> int:
        meeting_ids = {
            doc.metadata.get("meeting_id")
            for doc in documents
            if doc.metadata.get("meeting_id") not in ("", None)
        }

        if not meeting_ids:
            return 0

        deleted = 0
        collections = get_all_rag_collections()

        for collection in collections:
            for meeting_id in meeting_ids:
                try:
                    result = collection.get(
                        where={"meeting_id": meeting_id},
                    )
                    ids = result.get("ids", [])

                    if ids:
                        collection.delete(ids=ids)
                        deleted += len(ids)

                except Exception as error:
                    logger.exception(
                        "Error deleting documents for meeting_id=%s in collection=%s: %s",
                        meeting_id,
                        getattr(collection, "name", ""),
                        str(error),
                    )

        return deleted

    def ask(
        self,
        question: str,
        top_k: int = 10,
        date_filter: str | None = None,
        year_month_filter: str | None = None,
        mode: str = "auto",
        conversation_context: str | None = None,
    ) -> dict:
        guard = classify_question(
            question=question,
            has_conversation_context=bool(conversation_context),
            has_explicit_date_filter=bool(date_filter),
            has_explicit_year_month_filter=bool(year_month_filter),
            mode=mode,
        )

        if guard.intent == "out_of_scope":
            return {
                "answer": build_out_of_scope_answer(),
                "temporal_period": None,
                "temporal_date": None,
                "temporal_year_month": None,
                "sources": [],
            }

        effective_conversation_context = (
            conversation_context
            if guard.use_conversation_context
            else None
        )

        temporal_filter = extract_temporal_filter(
            question=question,
            explicit_date=date_filter,
            explicit_year_month=year_month_filter,
        )

        temporal_day_limit = max(top_k, 50)
        temporal_month_limit = max(top_k, 100)

        semantic_query = self._build_semantic_query(
            question=question,
            conversation_context=effective_conversation_context,
        )

        search_results: list[RagSearchResult] = []

        if guard.use_chroma:
            if mode == "semantic":
                search_results = self.search(
                    query=semantic_query,
                    top_k=top_k,
                    year_month=temporal_filter.year_month,
                )

            elif mode == "day":
                search_results = self.search_full_meeting_context_by_day(
                    date_value=date_filter or temporal_filter.date,
                    limit=temporal_day_limit,
                )

            elif mode == "month":
                search_results = self.search_full_meeting_context_by_month(
                    year_month=year_month_filter or temporal_filter.year_month,
                    limit=temporal_month_limit,
                )

            else:
                if temporal_filter.period == "day":
                    search_results = self.search_full_meeting_context_by_day(
                        date_value=temporal_filter.date,
                        limit=temporal_day_limit,
                    )

                elif temporal_filter.period == "month":
                    search_results = self.search_full_meeting_context_by_month(
                        year_month=temporal_filter.year_month,
                        limit=temporal_month_limit,
                    )

                else:
                    search_results = self.search(
                        query=semantic_query,
                        top_k=top_k,
                    )

        if not search_results and not effective_conversation_context:
            return {
                "answer": "No encontré información suficiente en Chroma para responder. Primero ejecuta /api/rag/ingest o /api/rag/sync.",
                "temporal_period": temporal_filter.period,
                "temporal_date": temporal_filter.date,
                "temporal_year_month": temporal_filter.year_month,
                "sources": [],
            }

        context = self._build_context(search_results) if search_results else ""

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": build_user_prompt(
                    question=question,
                    context=context,
                    conversation_context=effective_conversation_context,
                ),
            },
        ]

        answer = self.openai_service.chat(messages=messages)

        return {
            "answer": answer,
            "temporal_period": temporal_filter.period,
            "temporal_date": temporal_filter.date,
            "temporal_year_month": temporal_filter.year_month,
            "sources": [
                self._to_source_item(result)
                for result in search_results
            ],
        }

    def _build_semantic_query(
        self,
        question: str,
        conversation_context: str | None = None,
    ) -> str:
        if not conversation_context or not conversation_context.strip():
            return question

        return f"""
Contexto conversacional:
{conversation_context}

Pregunta actual:
{question}
""".strip()

    def search(
        self,
        query: str,
        top_k: int = 10,
        year_month: str | None = None,
    ) -> list[RagSearchResult]:
        query_embedding = self.openai_service.embed_query(query)

        normalized_year_month = (
            normalize_year_month(year_month) if year_month else ""
        )

        collections = get_all_rag_collections()

        results: list[RagSearchResult] = []

        for collection in collections:
            if collection.count() == 0:
                continue

            query_result = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            ids = query_result.get("ids", [[]])[0]
            documents = query_result.get("documents", [[]])[0]
            metadatas = query_result.get("metadatas", [[]])[0]
            distances = query_result.get("distances", [[]])[0]

            for index, doc_id in enumerate(ids):
                metadata = metadatas[index] or {}

                if normalized_year_month and not self._metadata_matches_year_month(
                    metadata=metadata,
                    year_month=normalized_year_month,
                ):
                    continue

                results.append(
                    RagSearchResult(
                        id=doc_id,
                        text=documents[index],
                        metadata=metadata,
                        distance=distances[index] if distances else None,
                        collection_name=collection.name,
                    )
                )

        results.sort(
            key=lambda item: item.distance
            if item.distance is not None
            else 999999
        )

        return results[:top_k]

    def search_full_meeting_context_by_day(
        self,
        date_value: str,
        limit: int = 50,
    ) -> list[RagSearchResult]:
        temporal_filter = extract_temporal_filter(
            question="",
            explicit_date=date_value,
        )

        if temporal_filter.period != "day":
            return []

        collections = get_all_rag_collections()
        results: list[RagSearchResult] = []

        for collection in collections:
            if collection.count() == 0:
                continue

            get_limit = max(limit, min(collection.count(), 5000))

            result = collection.get(
                where={"document_type": "meeting_full_context"},
                include=["documents", "metadatas"],
                limit=get_limit,
            )

            collection_results = self._collection_get_to_search_results(
                collection=collection,
                result=result,
            )

            for item in collection_results:
                if self._metadata_matches_date(
                    metadata=item.metadata,
                    date_value=temporal_filter.date,
                ):
                    results.append(item)

        return self._sort_temporal_results(results)[:limit]

    def search_full_meeting_context_by_month(
        self,
        year_month: str,
        limit: int = 100,
    ) -> list[RagSearchResult]:
        normalized_year_month = normalize_year_month(year_month)

        if not normalized_year_month:
            return []

        collection_key = collection_key_from_year_month(normalized_year_month)
        preferred_collection = get_existing_rag_collection(collection_key)

        collections = get_all_rag_collections()

        if preferred_collection is not None:
            collections = sorted(
                collections,
                key=lambda collection: 0
                if collection.name == preferred_collection.name
                else 1,
            )

        results: list[RagSearchResult] = []

        for collection in collections:
            if collection.count() == 0:
                continue

            get_limit = max(limit, min(collection.count(), 5000))

            result = collection.get(
                where={"document_type": "meeting_full_context"},
                include=["documents", "metadatas"],
                limit=get_limit,
            )

            collection_results = self._collection_get_to_search_results(
                collection=collection,
                result=result,
            )

            for item in collection_results:
                if self._metadata_matches_year_month(
                    metadata=item.metadata,
                    year_month=normalized_year_month,
                ):
                    results.append(item)

        return self._sort_temporal_results(results)[:limit]

    def _collection_get_to_search_results(
        self,
        collection,
        result: dict,
    ) -> list[RagSearchResult]:
        ids = result.get("ids", [])
        documents = result.get("documents", [])
        metadatas = result.get("metadatas", [])

        search_results: list[RagSearchResult] = []

        for index, doc_id in enumerate(ids):
            text = documents[index] if index < len(documents) else ""
            metadata = metadatas[index] if index < len(metadatas) else {}

            search_results.append(
                RagSearchResult(
                    id=doc_id,
                    text=text,
                    metadata=metadata or {},
                    distance=None,
                    collection_name=collection.name,
                )
            )

        return search_results

    def _build_context(self, results: list[RagSearchResult]) -> str:
        blocks: list[str] = []

        for index, result in enumerate(results, start=1):
            metadata = result.metadata

            block = f"""
[FUENTE {index}]
Colección: {result.collection_name or ""}
Tipo: {metadata.get("document_type", "")}
Reunión ID: {metadata.get("meeting_id", "")}
Título reunión: {metadata.get("meeting_title", "")}
Estado reunión: {metadata.get("meeting_status", "")}
Fecha reunión: {metadata.get("meeting_start_date", "")}
Mes-año reunión: {metadata.get("meeting_year_month", "")}
Fechas relacionadas: {metadata.get("related_dates", "")}
Meses relacionados: {metadata.get("related_year_months", "")}
Tópico: {metadata.get("topic_name", "")}

Contenido:
{result.text}
""".strip()

            blocks.append(block)

        return "\n\n---\n\n".join(blocks)

    def _to_source_item(self, result: RagSearchResult) -> SourceItem:
        metadata = result.metadata

        return SourceItem(
            id=result.id,
            collection_name=result.collection_name,
            collection_key=metadata.get("collection_key"),
            document_type=metadata.get("document_type"),
            meeting_id=self._safe_int(metadata.get("meeting_id")),
            meeting_title=metadata.get("meeting_title"),
            meeting_status=metadata.get("meeting_status"),
            meeting_start_date=metadata.get("meeting_start_date"),
            meeting_year_month=metadata.get("meeting_year_month"),
            topic_name=metadata.get("topic_name"),
            note_type=metadata.get("note_type"),
            activity_status=metadata.get("activity_status"),
            distance=result.distance,
            text_preview=result.text[:500],
        )

    @staticmethod
    def _split_metadata_values(value: Any) -> set[str]:
        if value in ("", None):
            return set()

        if isinstance(value, list):
            return {str(item).strip() for item in value if str(item).strip()}

        text = str(value)
        parts = []

        for separator in ["|", ",", ";"]:
            if separator in text:
                parts = text.split(separator)
                break

        if not parts:
            parts = [text]

        return {part.strip() for part in parts if part.strip()}

    def _metadata_matches_year_month(
        self,
        metadata: dict,
        year_month: str,
    ) -> bool:
        if not year_month:
            return True

        related_year_months = self._split_metadata_values(
            metadata.get("related_year_months")
        )

        if year_month in related_year_months:
            return True

        direct_values = [
            metadata.get("meeting_year_month"),
            str(metadata.get("meeting_start_date", ""))[:7],
            str(metadata.get("meeting_end_date", ""))[:7],
            str(metadata.get("note_created_date", ""))[:7],
            str(metadata.get("activity_target_date", ""))[:7],
            str(metadata.get("activity_completed_date", ""))[:7],
        ]

        return year_month in direct_values

    def _metadata_matches_date(
        self,
        metadata: dict,
        date_value: str,
    ) -> bool:
        normalized_date = normalize_date(date_value)

        if not normalized_date:
            return True

        related_dates = self._split_metadata_values(
            metadata.get("related_dates")
        )

        if normalized_date in related_dates:
            return True

        direct_values = [
            metadata.get("meeting_start_date"),
            metadata.get("meeting_end_date"),
            metadata.get("note_created_date"),
            metadata.get("activity_target_date"),
            metadata.get("activity_completed_date"),
        ]

        return normalized_date in {
            normalize_date(value)
            for value in direct_values
            if normalize_date(value)
        }

    def _sort_temporal_results(
        self,
        results: list[RagSearchResult],
    ) -> list[RagSearchResult]:
        return sorted(
            results,
            key=lambda item: (
                item.metadata.get("meeting_start_date", ""),
                self._safe_sort_value(item.metadata.get("meeting_id")),
            ),
        )

    @staticmethod
    def _safe_int(value) -> int | None:
        try:
            if value in ("", None):
                return None
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _safe_sort_value(value) -> int:
        try:
            if value in ("", None):
                return 0
            return int(value)
        except Exception:
            return 0

    def reset(self) -> dict:
        deleted = delete_all_rag_collections()

        return {
            "status": "reset_done",
            "deleted_collections": deleted,
        }
