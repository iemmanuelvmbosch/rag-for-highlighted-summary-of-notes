from __future__ import annotations

import logging
import re
import sys

try:
    import pysqlite3

    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

import chromadb

from app.utils.settings import get_settings

logger = logging.getLogger(__name__)


def get_chroma_client() -> chromadb.PersistentClient:
    settings = get_settings()
    return chromadb.PersistentClient(path=settings.chroma_path)


def sanitize_collection_name(name: str) -> str:
    clean_name = str(name or "").strip().lower()

    clean_name = re.sub(r"[^a-zA-Z0-9._-]", "_", clean_name)
    clean_name = re.sub(r"^[^a-zA-Z0-9]+", "", clean_name)
    clean_name = re.sub(r"[^a-zA-Z0-9]+$", "", clean_name)

    if not clean_name:
        clean_name = "rag_unknown"

    if len(clean_name) < 3:
        clean_name = f"rag_{clean_name}"

    if len(clean_name) > 63:
        clean_name = clean_name[:63]
        clean_name = re.sub(r"[^a-zA-Z0-9]+$", "", clean_name)

    if not clean_name:
        clean_name = "rag_unknown"

    if len(clean_name) < 3:
        clean_name = "rag"

    return clean_name


def get_collection_name_for_key(collection_key: str) -> str:
    settings = get_settings()

    base_name = sanitize_collection_name(settings.chroma_collection_name)
    key = sanitize_collection_name(collection_key or "unknown")

    if key == "unknown":
        return sanitize_collection_name(f"{base_name}_unknown")

    return sanitize_collection_name(f"{base_name}_{key}")


def get_rag_collection(collection_key: str):
    client = get_chroma_client()
    collection_name = get_collection_name_for_key(collection_key)

    return client.get_or_create_collection(
        name=collection_name,
        metadata={
            "description": f"MeetTrack RAG monthly collection {collection_key}",
            "collection_key": collection_key,
        },
    )


def get_existing_rag_collection(collection_key: str):
    client = get_chroma_client()
    collection_name = get_collection_name_for_key(collection_key)

    try:
        return client.get_collection(name=collection_name)
    except Exception:
        return None


def list_rag_collection_names() -> list[str]:
    settings = get_settings()
    client = get_chroma_client()
    base_name = sanitize_collection_name(settings.chroma_collection_name)

    collections = client.list_collections()
    names: list[str] = []

    for collection in collections:
        if hasattr(collection, "name"):
            name = collection.name
        else:
            name = str(collection)

        if name == base_name or name.startswith(f"{base_name}_"):
            names.append(name)

    return sorted(names)


def get_all_rag_collections():
    client = get_chroma_client()
    collection_names = list_rag_collection_names()

    collections = []

    for name in collection_names:
        try:
            collections.append(client.get_collection(name=name))
        except Exception as error:
            logger.exception(
                "Error getting Chroma collection %s: %s",
                name,
                str(error),
            )

    return collections


def delete_all_rag_collections() -> int:
    client = get_chroma_client()
    collection_names = list_rag_collection_names()

    deleted = 0

    for name in collection_names:
        try:
            client.delete_collection(name)
            deleted += 1
        except Exception as error:
            logger.exception(
                "Error deleting Chroma collection %s: %s",
                name,
                str(error),
            )

    return deleted


def reset_rag_collection(collection_key: str):
    client = get_chroma_client()
    collection_name = get_collection_name_for_key(collection_key)

    try:
        client.delete_collection(collection_name)
    except Exception as error:
        logger.warning(
            "Could not delete Chroma collection %s before reset: %s",
            collection_name,
            str(error),
        )

    return get_rag_collection(collection_key)
