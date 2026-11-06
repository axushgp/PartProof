import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from openai import AsyncOpenAI, AuthenticationError, RateLimitError, APIError, APIConnectionError, APITimeoutError
from app.core.config import settings
from app.services.inference.base import InferenceMetadata, InferenceResponse, ProviderHealth
from app.services.inference.exceptions import (
    InferenceAuthError,
    InferenceConfigurationError,
    InferenceError,
    InferenceProviderError,
    InferenceRateLimitError,
    InferenceTimeoutError,
)

logger = logging.getLogger("partproof.inference")


class VultrInferenceClient:
    """
    Asynchronous client for Vultr Serverless Inference (OpenAI-compatible endpoint).
    Provides bounded retries, latency telemetry, fallback model routing, and credential isolation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.VULTR_INFERENCE_API_KEY
        self.base_url = base_url or settings.VULTR_INFERENCE_BASE_URL
        self.primary_model = primary_model or settings.VULTR_INFERENCE_MODEL
        self.fallback_model = fallback_model or settings.VULTR_INFERENCE_FALLBACK_MODEL
        self.timeout = float(timeout_seconds or settings.VULTR_INFERENCE_TIMEOUT_SECONDS)
        self.max_retries = max_retries if max_retries is not None else settings.VULTR_INFERENCE_MAX_RETRIES

        self._client: Optional[AsyncOpenAI] = None
        self._closed: bool = False

    def _get_client(self) -> AsyncOpenAI:
        """Initializes and returns the AsyncOpenAI client instance."""
        if self._closed:
            raise InferenceError("VultrInferenceClient has been closed.")
        if not self.api_key:
            raise InferenceConfigurationError(
                "VULTR_INFERENCE_API_KEY is not configured on the backend."
            )
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """
        Explicitly closes the AsyncOpenAI client and its underlying httpx connection pool.
        Ensures HTTP connections are freed and no unclosed client warnings occur.
        """
        self._closed = True
        if self._client is not None:
            client = self._client
            self._client = None
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing AsyncOpenAI client: {e}")

    async def aclose(self) -> None:
        """Alias for close() to match httpx / async context convention."""
        await self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> InferenceResponse:
        """
        Calls Vultr Serverless Inference chat completion with bounded retries and fallback handling.
        """
        client = self._get_client()
        target_model = model or self.primary_model
        temp = temperature if temperature is not None else settings.VULTR_INFERENCE_TEMPERATURE
        format_spec = response_format or {"type": "json_object"}

        retries = 0
        current_model = target_model
        start_time = time.monotonic()

        while True:
            try:
                logger.info(f"Dispatching inference request to Vultr model: {current_model} (attempt {retries + 1})")
                
                resp = await client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    temperature=temp,
                    response_format=format_spec,
                )

                latency_ms = round((time.monotonic() - start_time) * 1000, 2)
                content = resp.choices[0].message.content or ""
                
                usage = resp.usage
                prompt_tokens = usage.prompt_tokens if usage else None
                completion_tokens = usage.completion_tokens if usage else None
                total_tokens = usage.total_tokens if usage else None

                metadata = InferenceMetadata(
                    provider="vultr",
                    model=current_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    retries=retries,
                )

                logger.info(
                    f"Vultr inference completed: model={current_model} latency={latency_ms}ms "
                    f"total_tokens={total_tokens} retries={retries}"
                )

                return InferenceResponse(content=content, metadata=metadata)

            except AuthenticationError as e:
                logger.error("Vultr Serverless Inference authentication failed (401/403).")
                raise InferenceAuthError(str(e), model=current_model) from e

            except RateLimitError as e:
                retries += 1
                if retries > self.max_retries:
                    logger.error(f"Rate limit exceeded after {self.max_retries} retries: {e}")
                    raise InferenceRateLimitError(str(e), model=current_model) from e
                
                delay = 1.0 * (2 ** (retries - 1))
                logger.warning(f"Rate limit hit. Retrying in {delay}s (retry {retries}/{self.max_retries})...")
                await asyncio.sleep(delay)

            except (APITimeoutError, httpx.TimeoutException) as e:
                retries += 1
                if retries > self.max_retries:
                    logger.error(f"Inference request timed out after {self.max_retries} retries: {e}")
                    raise InferenceTimeoutError(str(e), model=current_model) from e
                
                delay = 0.5 * (2 ** (retries - 1))
                logger.warning(f"Timeout on inference call. Retrying in {delay}s...")
                await asyncio.sleep(delay)

            except (APIConnectionError, httpx.NetworkError) as e:
                retries += 1
                if retries > self.max_retries:
                    logger.error(f"Network error connecting to Vultr inference endpoint: {e}")
                    raise InferenceProviderError(f"Connection error to Vultr endpoint: {e}", status_code=503, model=current_model) from e
                
                delay = 0.5 * (2 ** (retries - 1))
                logger.warning(f"Network error on inference call. Retrying in {delay}s...")
                await asyncio.sleep(delay)

            except APIError as e:
                # If provider returns 5xx error, check if fallback candidate is available
                if e.status_code and e.status_code >= 500 and current_model == self.primary_model and self.fallback_model:
                    logger.warning(f"Primary model {self.primary_model} failed with {e.status_code}. Switching to fallback {self.fallback_model}...")
                    current_model = self.fallback_model
                    retries += 1
                    await asyncio.sleep(0.5)
                    continue
                
                retries += 1
                if retries > self.max_retries:
                    logger.error(f"Vultr provider error: {e}")
                    raise InferenceProviderError(str(e), status_code=e.status_code or 502, model=current_model) from e
                
                delay = 0.5 * (2 ** (retries - 1))
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Unexpected error during inference request: {e}", exc_info=True)
                raise InferenceError(f"Unexpected inference error: {e}", model=current_model) from e

    async def check_health(self) -> ProviderHealth:
        """
        Performs an explicit connectivity check to the Vultr Serverless Inference API.
        Does not issue expensive completion requests on every call.
        """
        if not self.api_key:
            return ProviderHealth(
                status="not_configured",
                model=self.primary_model,
                message="VULTR_INFERENCE_API_KEY is not configured.",
            )

        start_time = time.monotonic()
        try:
            client = self._get_client()
            # Query models list to verify auth and connectivity
            await client.models.list()
            latency_ms = round((time.monotonic() - start_time) * 1000, 2)
            return ProviderHealth(
                status="reachable",
                model=self.primary_model,
                latency_ms=latency_ms,
                message="Vultr Serverless Inference connection active.",
            )
        except AuthenticationError:
            return ProviderHealth(
                status="auth_failed",
                model=self.primary_model,
                message="Vultr API key is invalid or unauthorized.",
            )
        except RateLimitError:
            return ProviderHealth(
                status="rate_limited",
                model=self.primary_model,
                message="Provider rate limit reached.",
            )
        except (APITimeoutError, httpx.TimeoutException):
            return ProviderHealth(
                status="unreachable",
                model=self.primary_model,
                message="Connection timed out reaching Vultr inference endpoint.",
            )
        except Exception as e:
            return ProviderHealth(
                status="degraded",
                model=self.primary_model,
                message=f"Provider check failed: {type(e).__name__}",
            )
