from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_provider: Literal["farm", "openai"] = "farm"

    embedding_provider: Literal["local", "farm", "openai"] = "local"

    farm_base_url: Optional[str] = None
    farm_api_version: str = "2024-08-01-preview"
    farm_subscription_key: Optional[str] = None
    farm_subscription_header_name: str = "genaiplatform-farm-subscription-key"
    farm_dummy_api_key: str = "dummy"

    farm_deployment: Optional[str] = None
    farm_chat_deployment: Optional[str] = None

    farm_embedding_deployment: Optional[str] = None

    openai_api_key: Optional[str] = None
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    local_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    local_embedding_batch_size: int = 32
    local_embedding_normalize: bool = True

    openai_timeout_seconds: int = 120
    openai_max_retries: int = 2
    openai_verify_ssl: bool = True
    openai_ca_bundle: Optional[str] = None

    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    no_proxy: Optional[str] = None

    meettrack_train_data_url: str
    meettrack_x_ai_token: str
    meettrack_http_method: str = "GET"
    meettrack_timeout_seconds: int = 60
    meettrack_verify_ssl: bool = False

    chroma_path: str = "./chroma_db"
    chroma_collection_name: str = "meettrack_rag"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
