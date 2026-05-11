from __future__ import annotations

import re

import chromadb

from app.utils.settings import get_settings


def get_chroma_client() -> chromadb.PersistentClient:
    settings = get_settings()
    return chromadb.PersistentClient(path=settings.chroma_path)


def sanitize_collection_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    name = re.sub(r"^[^a-zA-Z0-9]+", "", name)
    name = re.sub(r"[^a-zA-Z0-9]+$", "", name)

    if len(name) < 3:
        name = f"rag_{name}"

    if len(name) > 63:
        name = name[:63]
        name = re.sub(r"[^a-zA-Z0-9]+$", "", name)

    return name


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

    return [client.get_collection(name=name) for name in collection_names]


def delete_all_rag_collections() -> int:
    client = get_chroma_client()
    collection_names = list_rag_collection_names()

    deleted = 0

    for name in collection_names:
        try:
            client.delete_collection(name)
            deleted += 1
        except Exception:
            pass

    return deleted


def reset_rag_collection(collection_key: str):
    client = get_chroma_client()
    collection_name = get_collection_name_for_key(collection_key)

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    return get_rag_collection(collection_key)
