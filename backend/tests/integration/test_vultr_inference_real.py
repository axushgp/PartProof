import os
import pytest
from app.core.config import settings
from app.schemas.plan import TaskPlanSchema
from app.services.inference.planner import TaskPlanner
from app.services.inference.vultr_client import VultrInferenceClient

# This test requires a live Vultr Serverless Inference API key and explicit opt-in:
# RUN_VULTR_INFERENCE_INTEGRATION=1
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VULTR_INFERENCE_INTEGRATION") != "1" or not os.environ.get("VULTR_INFERENCE_API_KEY"),
    reason="Requires live Vultr Serverless Inference API key and RUN_VULTR_INFERENCE_INTEGRATION=1",
)


@pytest.mark.asyncio
async def test_live_vultr_inference_health():
    """
    Verifies live connectivity and authentication with Vultr Serverless Inference endpoint.
    Uses context manager for deterministic client closure before event loop termination.
    """
    async with VultrInferenceClient() as client:
        health = await client.check_health()

        assert health.status == "reachable", f"Vultr inference health check failed: {health.message}"
        assert health.latency_ms is not None
        assert health.latency_ms > 0


@pytest.mark.asyncio
async def test_live_vultr_task_planning_glm():
    """
    Validates end-to-end task planning via Vultr Serverless Inference with model glm-5.3:
    1. Authenticates against https://api.vultrinference.com/v1.
    2. Issues structured planning prompt for an offline engineering calculation.
    3. Receives GLM-5.3 completion.
    4. Parses JSON and verifies full Pydantic TaskPlanSchema compliance.
    5. Verifies token usage and latency telemetry.
    Uses async context managers for clean HTTP client teardown.
    """
    async with VultrInferenceClient() as client:
        async with TaskPlanner(client=client) as planner:
            task_description = (
                "Generate a Python program that calculates the first 10 prime numbers "
                "and writes them into a CSV file named '/workspace/output/primes.csv'."
            )

            plan, metadata = await planner.plan_task(task_description)

            # 1. Schema validation
            assert isinstance(plan, TaskPlanSchema)
            assert len(plan.title) > 0
            assert len(plan.steps) >= 1
            assert len(plan.steps) <= 3

            # 2. Step safety validation
            for step in plan.steps:
                assert step.execution_type == "python"
                assert len(step.code.strip()) > 0
                assert "def " in step.code or "print" in step.code or "with open" in step.code or "for " in step.code

            # 3. Artifact specification
            assert "primes.csv" in plan.expected_artifacts or any(a.endswith(".csv") for a in plan.expected_artifacts)

            # 4. Metadata verification
            assert metadata.provider == "vultr"
            assert metadata.model in [settings.VULTR_INFERENCE_MODEL, settings.VULTR_INFERENCE_FALLBACK_MODEL]
            assert metadata.latency_ms > 0
            assert metadata.total_tokens is not None and metadata.total_tokens > 0
