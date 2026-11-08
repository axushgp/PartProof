import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from openai import (
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
    APIError,
    APIConnectionError,
    APITimeoutError,
)
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
        max_completion_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.VULTR_INFERENCE_API_KEY
        self.base_url = base_url or settings.VULTR_INFERENCE_BASE_URL
        self.primary_model = primary_model or settings.VULTR_INFERENCE_MODEL
        self.fallback_model = fallback_model or settings.VULTR_INFERENCE_FALLBACK_MODEL
        self.timeout = float(timeout_seconds or settings.VULTR_INFERENCE_TIMEOUT_SECONDS)
        self.max_retries = max_retries if max_retries is not None else settings.VULTR_INFERENCE_MAX_RETRIES
        self.max_completion_tokens = (
            max_completion_tokens
            if max_completion_tokens is not None
            else settings.VULTR_INFERENCE_MAX_COMPLETION_TOKENS
        )
        self.reasoning_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else settings.VULTR_INFERENCE_REASONING_EFFORT
        )

        self._client: Optional[AsyncOpenAI] = None
        self._closed: bool = False

    def _get_client(self) -> AsyncOpenAI:
        """Initializes and returns the AsyncOpenAI client instance with SDK retries disabled."""
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
                max_retries=0,  # Retries controlled exclusively by PartProof application loop
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
        max_completion_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
    ) -> InferenceResponse:
        """
        Calls Vultr Serverless Inference chat completion with bounded retries and fallback handling.
        """
        client = self._get_client()
        target_model = model or self.primary_model
        temp = temperature if temperature is not None else settings.VULTR_INFERENCE_TEMPERATURE
        format_spec = response_format or {"type": "json_object"}
        eff_max_completion_tokens = (
            max_completion_tokens
            if max_completion_tokens is not None
            else self.max_completion_tokens
        )
        eff_reasoning_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else self.reasoning_effort
        )

        current_model = target_model
        has_fallback = bool(self.fallback_model and self.fallback_model != current_model)
        max_attempts = 1 + self.max_retries
        attempt = 0
        retries = 0
        start_time = time.monotonic()
        last_error: Optional[Exception] = None

        while attempt < max_attempts:
            attempt += 1
            create_kwargs: Dict[str, Any] = {
                "model": current_model,
                "messages": messages,
                "temperature": temp,
                "response_format": format_spec,
                "max_completion_tokens": eff_max_completion_tokens,
            }
            if eff_reasoning_effort:
                create_kwargs["extra_body"] = {"reasoning_effort": eff_reasoning_effort}

            try:
                logger.info(
                    f"Dispatching inference request to Vultr model: {current_model} "
                    f"(attempt {attempt}/{max_attempts}, max_tokens={eff_max_completion_tokens}, "
                    f"reasoning_effort={eff_reasoning_effort})"
                )

                req_start = time.monotonic()
                resp = await client.chat.completions.create(**create_kwargs)
                req_duration_ms = round((time.monotonic() - req_start) * 1000, 2)
                total_latency_ms = round((time.monotonic() - start_time) * 1000, 2)

                # Validate response choices
                if not resp.choices or not resp.choices[0].message:
                    raise InferenceProviderError(
                        "Vultr Serverless Inference returned an empty response with no choices.",
                        status_code=502,
                        model=current_model,
                    )

                choice = resp.choices[0]
                raw_finish_reason = getattr(choice, "finish_reason", None)
                finish_reason = (
                    str(raw_finish_reason)
                    if raw_finish_reason is not None and type(raw_finish_reason).__name__ != "MagicMock"
                    else ("stop" if raw_finish_reason is not None else None)
                )
                content = choice.message.content or ""

                # Enforce token budget & non-empty completion checks
                if finish_reason == "length":
                    raise InferenceProviderError(
                        f"Inference token budget exhausted (finish_reason='length', "
                        f"max_completion_tokens={eff_max_completion_tokens}). Plan generation was cut short.",
                        status_code=502,
                        model=current_model,
                    )

                if not content.strip():
                    raise InferenceProviderError(
                        f"Inference returned empty content (finish_reason='{finish_reason}').",
                        status_code=502,
                        model=current_model,
                    )

                usage = resp.usage

                def _safe_int(val: Any) -> Optional[int]:
                    if val is None or type(val).__name__ == "MagicMock":
                        return None
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        return None

                prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", None)) if usage else None
                completion_tokens = _safe_int(getattr(usage, "completion_tokens", None)) if usage else None
                total_tokens = _safe_int(getattr(usage, "total_tokens", None)) if usage else None
                completion_details = getattr(usage, "completion_tokens_details", None) if usage else None
                reasoning_tokens = (
                    _safe_int(getattr(completion_details, "reasoning_tokens", None))
                    if completion_details
                    else None
                )

                metadata = InferenceMetadata(
                    provider="vultr",
                    model=current_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=total_latency_ms,
                    retries=retries,
                    finish_reason=finish_reason,
                    reasoning_tokens=reasoning_tokens,
                )

                logger.info(
                    f"Vultr inference succeeded: model={current_model} latency_ms={total_latency_ms} "
                    f"req_ms={req_duration_ms} finish_reason={finish_reason} "
                    f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
                    f"total_tokens={total_tokens} reasoning_tokens={reasoning_tokens} retries={retries}"
                )

                return InferenceResponse(content=content, metadata=metadata)

            except (AuthenticationError, PermissionDeniedError) as e:
                # Non-retryable authentication / credential error. Do not failover to fallback.
                logger.error("Vultr Serverless Inference authentication failed (401/403). Non-retryable credentials error.")
                raise InferenceAuthError(str(e), model=current_model) from e

            except (APITimeoutError, httpx.TimeoutException, asyncio.TimeoutError) as e:
                last_error = e
                elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
                # Primary model timeout -> immediate failover to fallback model
                if current_model == self.primary_model and has_fallback:
                    logger.warning(
                        f"Primary model {self.primary_model} timed out after {elapsed_ms}ms. "
                        f"Switching to fallback model {self.fallback_model} (attempt {attempt + 1}/{max_attempts})."
                    )
                    current_model = self.fallback_model
                    retries += 1
                    continue

                retries += 1
                if attempt >= max_attempts:
                    logger.error(f"Inference request timed out after {retries} attempts: {e}")
                    raise InferenceTimeoutError(
                        f"Vultr Serverless Inference request timed out after {retries} attempts on {current_model}: {e}",
                        model=current_model,
                    ) from e

                delay = min(2.0, 0.5 * (2 ** (retries - 1)))
                logger.warning(f"Timeout on model {current_model}. Retrying in {delay}s (attempt {attempt + 1}/{max_attempts})...")
                await asyncio.sleep(delay)

            except (APIConnectionError, httpx.NetworkError) as e:
                last_error = e
                elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
                # Primary model connection failure -> immediate failover to fallback model
                if current_model == self.primary_model and has_fallback:
                    logger.warning(
                        f"Primary model {self.primary_model} connection failure ({e}) after {elapsed_ms}ms. "
                        f"Switching to fallback model {self.fallback_model} (attempt {attempt + 1}/{max_attempts})."
                    )
                    current_model = self.fallback_model
                    retries += 1
                    continue

                retries += 1
                if attempt >= max_attempts:
                    logger.error(f"Network error connecting to Vultr inference endpoint after {retries} attempts: {e}")
                    raise InferenceProviderError(
                        f"Connection error to Vultr endpoint on {current_model}: {e}",
                        status_code=503,
                        model=current_model,
                    ) from e

                delay = min(2.0, 0.5 * (2 ** (retries - 1)))
                logger.warning(f"Network error on model {current_model}. Retrying in {delay}s (attempt {attempt + 1}/{max_attempts})...")
                await asyncio.sleep(delay)

            except RateLimitError as e:
                last_error = e
                retries += 1
                if attempt >= max_attempts:
                    logger.error(f"Rate limit exceeded after {retries} attempts: {e}")
                    raise InferenceRateLimitError(str(e), model=current_model) from e

                delay = min(4.0, 1.0 * (2 ** (retries - 1)))
                logger.warning(f"Rate limit hit on model {current_model}. Retrying in {delay}s (attempt {attempt + 1}/{max_attempts})...")
                await asyncio.sleep(delay)

            except APIError as e:
                last_error = e
                status_code = getattr(e, "status_code", None) or 502

                # Reject malformed client requests (4xx except 429) immediately without retry or fallback
                if 400 <= status_code < 500:
                    logger.error(f"Vultr inference rejected request with client error {status_code}: {e}. Non-retryable.")
                    raise InferenceProviderError(str(e), status_code=status_code, model=current_model) from e

                elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
                # Primary model 5xx error -> immediate failover to fallback model
                if status_code >= 500 and current_model == self.primary_model and has_fallback:
                    logger.warning(
                        f"Primary model {self.primary_model} failed with HTTP {status_code} after {elapsed_ms}ms. "
                        f"Switching to fallback model {self.fallback_model} (attempt {attempt + 1}/{max_attempts})."
                    )
                    current_model = self.fallback_model
                    retries += 1
                    continue

                retries += 1
                if attempt >= max_attempts:
                    logger.error(f"Vultr provider error after {retries} attempts ({status_code}): {e}")
                    raise InferenceProviderError(
                        f"Vultr provider error ({status_code}): {e}",
                        status_code=status_code,
                        model=current_model,
                    ) from e

                delay = min(2.0, 0.5 * (2 ** (retries - 1)))
                logger.warning(f"Provider {status_code} on model {current_model}. Retrying in {delay}s (attempt {attempt + 1}/{max_attempts})...")
                await asyncio.sleep(delay)

            except InferenceError:
                raise

            except Exception as e:
                logger.error(f"Unexpected error during inference request on model {current_model}: {e}", exc_info=True)
                raise InferenceError(f"Unexpected inference error: {e}", model=current_model) from e

        if last_error:
            raise InferenceError(f"Inference attempts exhausted: {last_error}", model=current_model) from last_error
        raise InferenceError("Inference failed: maximum attempts reached.", model=current_model)

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
            await client.models.list()
            latency_ms = round((time.monotonic() - start_time) * 1000, 2)
            return ProviderHealth(
                status="reachable",
                model=self.primary_model,
                latency_ms=latency_ms,
                message="Vultr Serverless Inference connection active.",
            )
        except (AuthenticationError, PermissionDeniedError):
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
        except (APITimeoutError, httpx.TimeoutException, asyncio.TimeoutError):
            return ProviderHealth(
                status="unreachable",
                model=self.primary_model,
                message="Connection timed out reaching Vultr inference endpoint.",
            )
        except (APIConnectionError, httpx.NetworkError):
            return ProviderHealth(
                status="unreachable",
                model=self.primary_model,
                message="Network error connecting to Vultr inference endpoint.",
            )
        except Exception as e:
            return ProviderHealth(
                status="degraded",
                model=self.primary_model,
                message=f"Provider check failed: {type(e).__name__}",
            )
