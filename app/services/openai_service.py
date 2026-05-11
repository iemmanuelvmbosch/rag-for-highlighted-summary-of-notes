from __future__ import annotations

from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from app.utils.settings import get_settings


class OpenAIService:
    def __init__(self) -> None:
        self.settings = get_settings()

        self.llm_provider = self.settings.llm_provider.lower().strip()
        self.embedding_provider = self.settings.embedding_provider.lower().strip()

        self.http_client = self._build_http_client()

        self.chat_client: OpenAI | None = None
        self.embedding_client: OpenAI | None = None

        self.chat_model = ""
        self.embedding_model = ""

        self.local_embedding_model = None

        self._configure_chat_client()
        self._configure_embedding_client()

    # -------------------------------------------------------------------------
    # Client configuration
    # -------------------------------------------------------------------------
    def _build_http_client(self) -> httpx.Client:
        timeout = httpx.Timeout(
            connect=30.0,
            read=float(self.settings.openai_timeout_seconds),
            write=30.0,
            pool=30.0,
        )

        verify: bool | str = self.settings.openai_verify_ssl

        if self.settings.openai_ca_bundle:
            verify = self.settings.openai_ca_bundle

        proxy_url = self.settings.https_proxy or self.settings.http_proxy or None

        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "verify": verify,
            "trust_env": True,
        }

        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        return httpx.Client(**client_kwargs)

    def _configure_chat_client(self) -> None:
        if self.llm_provider == "farm":
            self.chat_model = self._get_farm_chat_deployment()
            self.chat_client = self._build_farm_client(self.chat_model)
            return

        if self.llm_provider == "openai":
            self._validate_openai_api_key()
            self.chat_model = self.settings.openai_chat_model
            self.chat_client = OpenAI(
                api_key=self.settings.openai_api_key,
                http_client=self.http_client,
                timeout=float(self.settings.openai_timeout_seconds),
                max_retries=self.settings.openai_max_retries,
            )
            return

        raise ValueError("LLM_PROVIDER inválido. Usa 'farm' u 'openai'.")

    def _configure_embedding_client(self) -> None:
        if self.embedding_provider == "local":
            self.embedding_model = self.settings.local_embedding_model
            self.local_embedding_model = self._load_local_embedding_model()
            return

        if self.embedding_provider == "farm":
            self.embedding_model = self._get_farm_embedding_deployment()
            self.embedding_client = self._build_farm_client(
                self.embedding_model)
            return

        if self.embedding_provider == "openai":
            self._validate_openai_api_key()
            self.embedding_model = self.settings.openai_embedding_model
            self.embedding_client = OpenAI(
                api_key=self.settings.openai_api_key,
                http_client=self.http_client,
                timeout=float(self.settings.openai_timeout_seconds),
                max_retries=self.settings.openai_max_retries,
            )
            return

        raise ValueError(
            "EMBEDDING_PROVIDER inválido. Usa 'local', 'farm' u 'openai'."
        )

    def _build_farm_client(self, deployment: str) -> OpenAI:
        self._validate_farm_settings()

        base_url = (
            f"{self.settings.farm_base_url.rstrip('/')}"
            f"/api/openai/deployments/{deployment}"
        )

        return OpenAI(
            api_key=self.settings.farm_dummy_api_key,
            base_url=base_url,
            default_query={
                "api-version": self.settings.farm_api_version,
            },
            default_headers={
                self.settings.farm_subscription_header_name:
                self.settings.farm_subscription_key
            },
            http_client=self.http_client,
            timeout=float(self.settings.openai_timeout_seconds),
            max_retries=self.settings.openai_max_retries,
        )

    def _load_local_embedding_model(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "Falta instalar sentence-transformers. Ejecuta: "
                "pip install sentence-transformers torch"
            ) from error

        return SentenceTransformer(self.settings.local_embedding_model)

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    def _validate_farm_settings(self) -> None:
        missing_values: list[str] = []

        if not self.settings.farm_base_url:
            missing_values.append("FARM_BASE_URL")

        if not self.settings.farm_api_version:
            missing_values.append("FARM_API_VERSION")

        if not self.settings.farm_subscription_key:
            missing_values.append("FARM_SUBSCRIPTION_KEY")

        if missing_values:
            raise ValueError(
                "Faltan variables de entorno para FARM/Open Enterprise: "
                + ", ".join(missing_values)
            )

    def _validate_openai_api_key(self) -> None:
        if not self.settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY es requerido cuando usas OpenAI público."
            )

    def _get_farm_chat_deployment(self) -> str:
        deployment = (
            self.settings.farm_chat_deployment
            or self.settings.farm_deployment
            or ""
        ).strip()

        if not deployment:
            raise ValueError(
                "Falta FARM_DEPLOYMENT o FARM_CHAT_DEPLOYMENT."
            )

        return deployment

    def _get_farm_embedding_deployment(self) -> str:
        deployment = (self.settings.farm_embedding_deployment or "").strip()

        if not deployment:
            raise ValueError(
                "Falta FARM_EMBEDDING_DEPLOYMENT porque EMBEDDING_PROVIDER=farm. "
                "Como no tienes ese deployment, usa EMBEDDING_PROVIDER=local."
            )

        return deployment

    # -------------------------------------------------------------------------
    # Embeddings
    # -------------------------------------------------------------------------
    def embed_texts(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        clean_texts = [
            text.replace("\n", " ").strip()
            for text in texts
            if text and text.strip()
        ]

        if not clean_texts:
            return []

        if self.embedding_provider == "local":
            return self._embed_texts_local(clean_texts, batch_size=batch_size)

        return self._embed_texts_remote(clean_texts, batch_size=batch_size)

    def embed_query(self, query: str) -> list[float]:
        clean_query = query.replace("\n", " ").strip()

        if not clean_query:
            raise ValueError("La query para embeddings no puede estar vacía.")

        if self.embedding_provider == "local":
            embeddings = self._embed_texts_local([clean_query], batch_size=1)
            return embeddings[0]

        embeddings = self._embed_texts_remote([clean_query], batch_size=1)
        return embeddings[0]

    def _embed_texts_local(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        if self.local_embedding_model is None:
            raise RuntimeError(
                "El modelo local de embeddings no está cargado.")

        effective_batch_size = (
            batch_size
            or self.settings.local_embedding_batch_size
            or 32
        )

        try:
            embeddings = self.local_embedding_model.encode(
                texts,
                batch_size=effective_batch_size,
                normalize_embeddings=self.settings.local_embedding_normalize,
                show_progress_bar=False,
            )

            return embeddings.tolist()

        except Exception as error:
            raise RuntimeError(
                f"Error generando embeddings locales con "
                f"{self.settings.local_embedding_model}: {str(error)}"
            ) from error

    def _embed_texts_remote(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        if self.embedding_client is None:
            raise RuntimeError(
                "El cliente remoto de embeddings no está configurado.")

        effective_batch_size = batch_size or 32

        embeddings: list[list[float]] = []

        try:
            for start in range(0, len(texts), effective_batch_size):
                batch = texts[start:start + effective_batch_size]

                response = self.embedding_client.embeddings.create(
                    model=self.embedding_model,
                    input=batch,
                )

                embeddings.extend([item.embedding for item in response.data])

            return embeddings

        except APIConnectionError as error:
            raise RuntimeError(self._format_connection_error(error)) from error

        except APITimeoutError as error:
            raise RuntimeError(
                "Timeout al generar embeddings. Revisa red, proxy, VPN o timeout."
            ) from error

        except AuthenticationError as error:
            raise RuntimeError(self._format_authentication_error()) from error

        except RateLimitError as error:
            raise RuntimeError(
                "Rate limit al generar embeddings."
            ) from error

        except APIStatusError as error:
            raise RuntimeError(self._format_status_error(error)) from error

    # -------------------------------------------------------------------------
    # Chat
    # -------------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> str:
        if self.chat_client is None:
            raise RuntimeError("El cliente de chat no está configurado.")

        try:
            response = self.chat_client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
            )

            content = response.choices[0].message.content

            if not content:
                return "No pude generar una respuesta con la información disponible."

            return content

        except APIConnectionError as error:
            raise RuntimeError(self._format_connection_error(error)) from error

        except APITimeoutError as error:
            raise RuntimeError(
                "Timeout al generar respuesta."
            ) from error

        except AuthenticationError as error:
            raise RuntimeError(self._format_authentication_error()) from error

        except RateLimitError as error:
            raise RuntimeError(
                "Rate limit al generar respuesta."
            ) from error

        except APIStatusError as error:
            raise RuntimeError(self._format_status_error(error)) from error

    # -------------------------------------------------------------------------
    # Debug
    # -------------------------------------------------------------------------
    def test_connection(self) -> dict:
        result: dict[str, Any] = {
            "status": "unknown",
            "llm_provider": self.llm_provider,
            "embedding_provider": self.embedding_provider,
            "chat_model": self.chat_model,
            "embedding_model": self.embedding_model,
            "proxy_used": self.settings.https_proxy or self.settings.http_proxy or None,
            "verify_ssl": self.settings.openai_verify_ssl,
            "ca_bundle": self.settings.openai_ca_bundle,
        }

        result["embeddings"] = self._test_embeddings_connection()
        result["chat"] = self._test_chat_connection()

        if (
            result["embeddings"].get("status") == "ok"
            and result["chat"].get("status") == "ok"
        ):
            result["status"] = "ok"
        else:
            result["status"] = "error"

        return result

    def _test_embeddings_connection(self) -> dict:
        try:
            embedding = self.embed_query("connection test")

            return {
                "status": "ok",
                "provider": self.embedding_provider,
                "model": self.embedding_model,
                "embedding_dimensions": len(embedding),
            }

        except Exception as error:
            cause = getattr(error, "__cause__", None)

            return {
                "status": "error",
                "provider": self.embedding_provider,
                "model": self.embedding_model,
                "error_type": type(error).__name__,
                "error": str(error),
                "cause_type": type(cause).__name__ if cause else None,
                "cause": repr(cause) if cause else None,
            }

    def _test_chat_connection(self) -> dict:
        try:
            answer = self.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a connection test assistant.",
                    },
                    {
                        "role": "user",
                        "content": "Responde solamente: ok",
                    },
                ],
                temperature=0,
            )

            return {
                "status": "ok",
                "provider": self.llm_provider,
                "model": self.chat_model,
                "response_preview": answer[:100],
            }

        except Exception as error:
            cause = getattr(error, "__cause__", None)

            return {
                "status": "error",
                "provider": self.llm_provider,
                "model": self.chat_model,
                "error_type": type(error).__name__,
                "error": str(error),
                "cause_type": type(cause).__name__ if cause else None,
                "cause": repr(cause) if cause else None,
            }

    # -------------------------------------------------------------------------
    # Error formatting
    # -------------------------------------------------------------------------
    def _format_connection_error(self, error: APIConnectionError) -> str:
        cause = getattr(error, "__cause__", None)

        if self.llm_provider == "farm" or self.embedding_provider == "farm":
            return (
                "FARM/Open Enterprise connection error. "
                "Revisa VPN, red interna Bosch, proxy corporativo, firewall, "
                "certificado SSL o FARM_BASE_URL. "
                f"Cause type: {type(cause).__name__ if cause else None}. "
                f"Cause: {repr(cause) if cause else None}"
            )

        return (
            "OpenAI connection error. "
            "Revisa proxy corporativo, certificado SSL, firewall o salida a api.openai.com. "
            f"Cause type: {type(cause).__name__ if cause else None}. "
            f"Cause: {repr(cause) if cause else None}"
        )

    def _format_authentication_error(self) -> str:
        if self.llm_provider == "farm" or self.embedding_provider == "farm":
            return (
                "FARM/Open Enterprise authentication error. "
                "Revisa FARM_SUBSCRIPTION_KEY, el header "
                f"'{self.settings.farm_subscription_header_name}', "
                "el deployment y permisos del recurso."
            )

        return "OpenAI authentication error. Revisa OPENAI_API_KEY."

    def _format_status_error(self, error: APIStatusError) -> str:
        if self.llm_provider == "farm" or self.embedding_provider == "farm":
            return (
                "FARM/Open Enterprise API status error: "
                f"{error.status_code} - {error.message}"
            )

        return (
            "OpenAI API status error: "
            f"{error.status_code} - {error.message}"
        )
