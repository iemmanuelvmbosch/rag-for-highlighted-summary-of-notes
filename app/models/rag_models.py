from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RagDocument:
    id: str
    text: str
    metadata: dict[str, Any]


@dataclass
class RagSearchResult:
    id: str
    text: str
    metadata: dict[str, Any]
    distance: float | None = None
    collection_name: str | None = None
