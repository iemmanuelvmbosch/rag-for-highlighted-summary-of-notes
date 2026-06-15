from __future__ import annotations

from functools import lru_cache

from app.services.openai_service import OpenAIService


@lru_cache
def get_openai_service() -> OpenAIService:
    return OpenAIService()
