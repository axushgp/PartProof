import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from openai import (
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
    APIError,
    APITimeoutError,
    APIConnectionError,
)
from app.services.inference.exceptions import (
    InferenceAuthError,
    InferenceConfigurationError,
    InferenceError,
    InferenceProviderError,
    InferenceRateLimitError,
    InferenceTimeoutError,
)
from app.services.inference.vultr_client import VultrInferenceClient


@pytest.mark.asyncio
async def test_missing_api_key_raises_configuration_error():
    client = VultrInferenceClient(api_key="")
    with pytest.raises(InferenceConfigurationError, match="VULTR_INFERENCE_API_KEY is not configured"):
        await client.chat_completion([{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
async def test_successful_chat_completion():
    client = VultrInferenceClient(api_key="vultr-mock-key")

    mock_choice = MagicMock()
    mock_choice.message.content = '{"title": "Test Plan", "steps": []}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 15
    mock_response.usage.completion_tokens = 25
    mock_response.usage.total_tokens = 40

    mock_create = AsyncMock(return_value=mock_response)

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        resp = await client.chat_completion([{"role": "user", "content": "Audit BOM"}])

        assert resp.content == '{"title": "Test Plan", "steps": []}'
        assert resp.metadata.provider == "vultr"
        assert resp.metadata.model == "glm-5.3"
        assert resp.metadata.total_tokens == 40
        assert resp.metadata.retries == 0
        assert resp.metadata.latency_ms >= 0


@pytest.mark.asyncio
async def test_authentication_failure_raises_immediately():
    client = VultrInferenceClient(api_key="invalid-key", max_retries=3)

    mock_response = MagicMock(status_code=401, headers={})
    mock_create = AsyncMock(
        side_effect=AuthenticationError("Invalid API key", response=mock_response, body=None)
    )

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        with pytest.raises(InferenceAuthError, match="Invalid API key"):
            await client.chat_completion([{"role": "user", "content": "Audit BOM"}])

        # Authentication errors must not be retried
        assert mock_create.call_count == 1


@pytest.mark.asyncio
async def test_rate_limit_retry_and_exceeded():
    client = VultrInferenceClient(api_key="vultr-key", max_retries=2)

    mock_response = MagicMock(status_code=429, headers={})
    mock_create = AsyncMock(
        side_effect=RateLimitError("Rate limit reached", response=mock_response, body=None)
    )

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        with pytest.raises(InferenceRateLimitError, match="Rate limit"):
            await client.chat_completion([{"role": "user", "content": "Audit BOM"}])

        # Initial call + 2 retries = 3 total attempts
        assert mock_create.call_count == 3


@pytest.mark.asyncio
async def test_timeout_retry_and_exceeded():
    client = VultrInferenceClient(api_key="vultr-key", max_retries=1)

    mock_create = AsyncMock(
        side_effect=APITimeoutError(request=MagicMock())
    )

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        with pytest.raises(InferenceTimeoutError, match="timed out"):
            await client.chat_completion([{"role": "user", "content": "Audit BOM"}])

        assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_fallback_model_routing_on_5xx_error():
    client = VultrInferenceClient(
        api_key="vultr-key",
        primary_model="glm-5.3",
        fallback_model="glm-5.3-flash",
        max_retries=2,
    )

    mock_err_response = MagicMock(status_code=503, headers={})
    error_503 = APIError("Service Unavailable", request=MagicMock(), body=None)
    error_503.status_code = 503

    mock_success = MagicMock()
    mock_success.choices = [MagicMock(message=MagicMock(content='{"status": "ok"}'))]
    mock_success.usage.total_tokens = 20

    # First attempt fails with 503 on primary model; second attempt succeeds with fallback
    mock_create = AsyncMock(side_effect=[error_503, mock_success])

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        resp = await client.chat_completion([{"role": "user", "content": "Plan"}])

        assert resp.content == '{"status": "ok"}'
        assert resp.metadata.model == "glm-5.3-flash"
        assert resp.metadata.retries == 1
        assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_check_health_unconfigured():
    client = VultrInferenceClient(api_key="")
    health = await client.check_health()
    assert health.status == "not_configured"


@pytest.mark.asyncio
async def test_check_health_reachable():
    client = VultrInferenceClient(api_key="vultr-key")

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.models.list = AsyncMock(return_value=[])
        mock_get_client.return_value = mock_openai

        health = await client.check_health()
        assert health.status == "reachable"
        assert health.latency_ms is not None


@pytest.mark.asyncio
async def test_sdk_retries_disabled():
    """Verifies AsyncOpenAI client is instantiated with max_retries=0 so PartProof controls retries."""
    client = VultrInferenceClient(api_key="vultr-test-key")
    sdk_client = client._get_client()
    assert sdk_client.max_retries == 0
    await client.close()


@pytest.mark.asyncio
async def test_max_completion_tokens_and_reasoning_effort_passed_to_sdk():
    """Verifies max_completion_tokens and extra_body reasoning_effort are passed to chat.completions.create."""
    client = VultrInferenceClient(
        api_key="vultr-test-key",
        max_completion_tokens=8192,
        reasoning_effort="low",
    )

    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = '{"plan": "ok"}'
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 50
    mock_resp.usage.completion_tokens = 100
    mock_resp.usage.total_tokens = 150
    mock_resp.usage.completion_tokens_details.reasoning_tokens = 0

    mock_create = AsyncMock(return_value=mock_resp)

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        # 1. Test defaults passed
        await client.chat_completion([{"role": "user", "content": "test"}])
        assert mock_create.call_count == 1
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 8192
        assert call_kwargs["extra_body"] == {"reasoning_effort": "low"}

        # 2. Test overrides passed
        await client.chat_completion(
            [{"role": "user", "content": "test2"}],
            max_completion_tokens=4096,
            reasoning_effort="medium",
        )
        assert mock_create.call_count == 2
        call2_kwargs = mock_create.call_args.kwargs
        assert call2_kwargs["max_completion_tokens"] == 4096
        assert call2_kwargs["extra_body"] == {"reasoning_effort": "medium"}


@pytest.mark.asyncio
async def test_primary_timeout_followed_by_successful_flash_fallback():
    """Verifies that when primary GLM-5.3 times out, it immediately fails over to GLM-5.3-flash."""
    client = VultrInferenceClient(
        api_key="vultr-key",
        primary_model="glm-5.3",
        fallback_model="glm-5.3-flash",
        max_retries=2,
    )

    timeout_err = APITimeoutError(request=MagicMock())

    mock_success = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = '{"title": "Fallback Success"}'
    mock_success.choices = [mock_choice]
    mock_success.usage.prompt_tokens = 20
    mock_success.usage.completion_tokens = 30
    mock_success.usage.total_tokens = 50

    mock_create = AsyncMock(side_effect=[timeout_err, mock_success])

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        resp = await client.chat_completion([{"role": "user", "content": "Plan"}])

        assert mock_create.call_count == 2
        assert mock_create.call_args_list[0].kwargs["model"] == "glm-5.3"
        assert mock_create.call_args_list[1].kwargs["model"] == "glm-5.3-flash"
        assert resp.content == '{"title": "Fallback Success"}'
        assert resp.metadata.model == "glm-5.3-flash"
        assert resp.metadata.retries == 1


@pytest.mark.asyncio
async def test_primary_connection_error_followed_by_successful_flash_fallback():
    """Verifies that when primary GLM-5.3 has connection failure, it immediately fails over to GLM-5.3-flash."""
    client = VultrInferenceClient(
        api_key="vultr-key",
        primary_model="glm-5.3",
        fallback_model="glm-5.3-flash",
        max_retries=2,
    )

    conn_err = APIConnectionError(request=MagicMock())

    mock_success = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = '{"title": "Connection Fallback Success"}'
    mock_success.choices = [mock_choice]
    mock_success.usage.prompt_tokens = 15
    mock_success.usage.completion_tokens = 25
    mock_success.usage.total_tokens = 40

    mock_create = AsyncMock(side_effect=[conn_err, mock_success])

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        resp = await client.chat_completion([{"role": "user", "content": "Plan"}])

        assert mock_create.call_count == 2
        assert mock_create.call_args_list[0].kwargs["model"] == "glm-5.3"
        assert mock_create.call_args_list[1].kwargs["model"] == "glm-5.3-flash"
        assert resp.metadata.model == "glm-5.3-flash"
        assert resp.metadata.retries == 1


@pytest.mark.asyncio
async def test_no_fallback_on_403_permission_denied():
    """Verifies that 403 Forbidden is non-retryable and never attempts the fallback model."""
    client = VultrInferenceClient(
        api_key="vultr-key",
        primary_model="glm-5.3",
        fallback_model="glm-5.3-flash",
        max_retries=3,
    )

    mock_response = MagicMock(status_code=403, headers={})
    mock_create = AsyncMock(
        side_effect=PermissionDeniedError("Forbidden", response=mock_response, body=None)
    )

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        with pytest.raises(InferenceAuthError, match="Forbidden"):
            await client.chat_completion([{"role": "user", "content": "Plan"}])

        assert mock_create.call_count == 1


@pytest.mark.asyncio
async def test_empty_content_raises_inference_error():
    """Verifies that an empty completion content raises InferenceProviderError instead of invalid JSON parse."""
    client = VultrInferenceClient(api_key="vultr-key", max_retries=0)

    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = "   "
    mock_resp.choices = [mock_choice]
    mock_resp.usage.total_tokens = 10

    mock_create = AsyncMock(return_value=mock_resp)

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        with pytest.raises(InferenceProviderError, match="empty content"):
            await client.chat_completion([{"role": "user", "content": "Plan"}])


@pytest.mark.asyncio
async def test_token_budget_exhaustion_raises_inference_error():
    """Verifies that finish_reason='length' produces a clear token budget exhaustion error."""
    client = VultrInferenceClient(api_key="vultr-key", max_retries=0)

    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "length"
    mock_choice.message.content = '{"title": "Truncated...'
    mock_resp.choices = [mock_choice]
    mock_resp.usage.total_tokens = 8192

    mock_create = AsyncMock(return_value=mock_resp)

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        with pytest.raises(InferenceProviderError, match="token budget exhausted"):
            await client.chat_completion([{"role": "user", "content": "Plan"}])


@pytest.mark.asyncio
async def test_metadata_identifies_winning_model():
    """Verifies that metadata identifies the model that actually succeeded."""
    client = VultrInferenceClient(
        api_key="vultr-key",
        primary_model="glm-5.3",
        fallback_model="glm-5.3-flash",
    )

    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = '{"status": "ok"}'
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 20
    mock_resp.usage.total_tokens = 30
    mock_resp.usage.completion_tokens_details.reasoning_tokens = 0

    mock_create = AsyncMock(return_value=mock_resp)

    with patch.object(client, "_get_client") as mock_get_client:
        mock_openai = MagicMock()
        mock_openai.chat.completions.create = mock_create
        mock_get_client.return_value = mock_openai

        resp = await client.chat_completion([{"role": "user", "content": "Plan"}])
        assert resp.metadata.model == "glm-5.3"
        assert resp.metadata.finish_reason == "stop"
