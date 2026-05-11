from __future__ import annotations

from collections import defaultdict
from typing import Literal

from app.database.chroma import (
    delete_all_rag_collections,
    get_all_rag_collections,
    get_collection_name_for_key,
    get_rag_collection,
)
from app.models.rag_models import RagDocument, RagSearchResult
from app.rag.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas.rag_schema import SourceItem
from app.services.document_builder_service import DocumentBuilderService
from app.services.meettrack_client_service import MeetTrackClientService
from app.services.openai_service import OpenAIService
from app.utils.settings import get_settings
from app.utils.text_utils import (
    build_date_range_filter,
    collection_key_from_year_month,
    extract_temporal_filter,
    meeting_matches_date_range,
    normalize_year_month,
)


class RagService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.openai_service = OpenAIService()

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
            self._delete_existing_documents(documents)

        collections_used = self._upsert_documents_grouped_by_collection(
            documents)

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

        grouped_documents = self._group_documents_by_collection_key(documents)

        new_documents_count = 0
        updated_documents_count = 0
        unchanged_documents_count = 0
        collections_used: list[str] = []

        for collection_key, docs in grouped_documents.items():
            collection = get_rag_collection(collection_key)
            collection_name = get_collection_name_for_key(collection_key)
            collections_used.append(collection_name)

            ids = [doc.id for doc in docs]

            existing = collection.get(
                ids=ids,
                include=["metadatas"],
            )

            existing_ids = existing.get("ids", [])
            existing_metadatas = existing.get("metadatas", [])

            existing_map = {
                doc_id: metadata or {}
                for doc_id, metadata in zip(existing_ids, existing_metadatas)
            }

            new_documents: list[RagDocument] = []
            updated_documents: list[RagDocument] = []

            for doc in docs:
                current_hash = doc.metadata.get("content_hash", "")
                previous_metadata = existing_map.get(doc.id)

                if previous_metadata is None:
                    new_documents.append(doc)
                    continue

                previous_hash = previous_metadata.get("content_hash", "")

                if previous_hash != current_hash:
                    updated_documents.append(doc)
                else:
                    unchanged_documents_count += 1

            docs_to_upsert = new_documents + updated_documents

            if docs_to_upsert:
                self._upsert_documents(
                    collection=collection, documents=docs_to_upsert)

            new_documents_count += len(new_documents)
            updated_documents_count += len(updated_documents)

        return {
            "total_records_from_api": api_response.get("totalRecords", 0),
            "total_meetings_filtered": len(filtered_response.get("data", [])),
            "total_documents_found": len(documents),
            "new_documents": new_documents_count,
            "updated_documents": updated_documents_count,
            "unchanged_documents": unchanged_documents_count,
            "total_collections_used": len(collections_used),
            "collections_used": sorted(collections_used),
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
                "La propiedad 'data' debe ser una lista de reuniones.")

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
            collection_key = str(doc.metadata.get(
                "collection_key") or "unknown")
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
            doc for doc in documents if doc.text and doc.text.strip()]

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

    def _delete_existing_documents(self, documents: list[RagDocument]) -> None:
        grouped_documents = self._group_documents_by_collection_key(documents)

        for collection_key, docs in grouped_documents.items():
            collection = get_rag_collection(collection_key)
            ids = [doc.id for doc in docs]

            try:
                collection.delete(ids=ids)
            except Exception:
                pass

    def ask(
        self,
        question: str,
        top_k: int = 10,
        date_filter: str | None = None,
        year_month_filter: str | None = None,
        mode: str = "auto",
    ) -> dict:
        temporal_filter = extract_temporal_filter(
            question=question,
            explicit_date=date_filter,
            explicit_year_month=year_month_filter,
        )

        if mode == "semantic":
            search_results = self.search(
                query=question,
                top_k=top_k,
                year_month=temporal_filter.year_month,
            )
        elif mode == "day":
            search_results = self.search_full_meeting_context_by_day(
                date_value=date_filter or temporal_filter.date,
                limit=top_k,
            )
        elif mode == "month":
            search_results = self.search_full_meeting_context_by_month(
                year_month=year_month_filter or temporal_filter.year_month,
                limit=top_k,
            )
        else:
            if temporal_filter.period == "day":
                search_results = self.search_full_meeting_context_by_day(
                    date_value=temporal_filter.date,
                    limit=top_k,
                )
            elif temporal_filter.period == "month":
                search_results = self.search_full_meeting_context_by_month(
                    year_month=temporal_filter.year_month,
                    limit=top_k,
                )
            else:
                search_results = self.search(
                    query=question,
                    top_k=top_k,
                )

        if not search_results:
            return {
                "answer": "No encontré información suficiente en Chroma para responder. Primero ejecuta /api/rag/ingest o /api/rag/sync.",
                "temporal_period": temporal_filter.period,
                "temporal_date": temporal_filter.date,
                "temporal_year_month": temporal_filter.year_month,
                "sources": [],
            }

        context = self._build_context(search_results)

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
                ),
            },
        ]

        answer = self.openai_service.chat(messages=messages)

        return {
            "answer": answer,
            "temporal_period": temporal_filter.period,
            "temporal_date": temporal_filter.date,
            "temporal_year_month": temporal_filter.year_month,
            "sources": [self._to_source_item(result) for result in search_results],
        }

    def search(
        self,
        query: str,
        top_k: int = 10,
        year_month: str | None = None,
    ) -> list[RagSearchResult]:
        query_embedding = self.openai_service.embed_query(query)

        collections = []

        if year_month:
            normalized_year_month = normalize_year_month(year_month)

            if normalized_year_month:
                collection_key = collection_key_from_year_month(
                    normalized_year_month)
                collections = [get_rag_collection(collection_key)]

        if not collections:
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
                results.append(
                    RagSearchResult(
                        id=doc_id,
                        text=documents[index],
                        metadata=metadatas[index] or {},
                        distance=distances[index] if distances else None,
                        collection_name=collection.name,
                    )
                )

        results.sort(
            key=lambda item: item.distance if item.distance is not None else 999999)

        return results[:top_k]

    def search_full_meeting_context_by_day(
        self,
        date_value: str,
        limit: int = 10,
    ) -> list[RagSearchResult]:
        temporal_filter = extract_temporal_filter(
            question="",
            explicit_date=date_value,
        )

        if temporal_filter.period != "day":
            return []

        collection = get_rag_collection(temporal_filter.collection_key)

        if collection.count() == 0:
            return []

        result = collection.get(
            where={
                "$and": [
                    {"document_type": "meeting_full_context"},
                    {"meeting_start_date": temporal_filter.date},
                ]
            },
            include=["documents", "metadatas"],
            limit=limit,
        )

        return self._collection_get_to_search_results(
            collection=collection,
            result=result,
        )

    def search_full_meeting_context_by_month(
        self,
        year_month: str,
        limit: int = 50,
    ) -> list[RagSearchResult]:
        normalized_year_month = normalize_year_month(year_month)

        if not normalized_year_month:
            return []

        collection_key = collection_key_from_year_month(normalized_year_month)
        collection = get_rag_collection(collection_key)

        if collection.count() == 0:
            return []

        result = collection.get(
            where={
                "$and": [
                    {"document_type": "meeting_full_context"},
                    {"meeting_year_month": normalized_year_month},
                ]
            },
            include=["documents", "metadatas"],
            limit=limit,
        )

        return self._collection_get_to_search_results(
            collection=collection,
            result=result,
        )

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

        return sorted(
            search_results,
            key=lambda item: (
                item.metadata.get("meeting_start_date", ""),
                self._safe_sort_value(item.metadata.get("meeting_id")),
            ),
        )

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
