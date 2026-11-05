import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from openai import AuthenticationError, RateLimitError, APIError, APITimeoutError
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
