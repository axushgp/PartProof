import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from app.core.config import settings
from app.schemas.plan import TaskPlanSchema
from app.services.inference.base import InferenceMetadata

MOCK_VALID_PLAN = TaskPlanSchema(
    title="Automated BOM Audit",
    summary="Audits parts and pricing",
    reasoning_summary="Statistical variance check across supplier quotations",
    steps=[
        {
            "step_id": "step_1",
            "description": "Calculate variance",
            "execution_type": "python",
            "code": "print('Variance calculated')",
            "expected_output": "Variance output",
        }
    ],
    required_capabilities=["math_computation"],
    network_required=False,
    success_criteria=["Variance computed within 0.01 tolerance"],
    expected_artifacts=["audit_report.csv"],
)

MOCK_METADATA = InferenceMetadata(
    provider="vultr",
    model="glm-5.3",
    prompt_tokens=120,
    completion_tokens=180,
    total_tokens=300,
    latency_ms=185.0,
    retries=0,
)


@pytest.mark.asyncio
async def test_task_creation_unauthenticated_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/tasks",
        json={"description": "Audit supplier quote"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_task_creation_and_plan_generation(client: AsyncClient):
    # 1. Login to acquire bearer token
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Mock TaskPlanner.plan_task to isolate from live Vultr API during unit tests
    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        new=AsyncMock(return_value=(MOCK_VALID_PLAN, MOCK_METADATA)),
    ):
        create_resp = await client.post(
            "/api/v1/tasks",
            json={"description": "Audit supplier quote A and B against engineering master BOM"},
            headers=headers,
        )

        assert create_resp.status_code == 201
        data = create_resp.json()
        assert data["task"]["status"] == "awaiting_approval"
        assert data["task"]["title"] == "Automated BOM Audit"
        assert data["plan"] is not None
        assert data["plan"]["model"] == "glm-5.3"
        assert data["plan"]["approval_status"] == "pending"
        assert data["plan"]["policy_result"]["allowed"] is True
        assert data["plan"]["policy_result"]["network_mode"] == "none"
        # Invariant: Planning MUST NOT trigger automatic code execution
        assert data["latest_execution"] is None

        task_id = data["task"]["id"]

        # 3. Retrieve task detail via GET /tasks/{task_id}
        get_resp = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
        assert get_resp.status_code == 200
        detail = get_resp.json()
        assert detail["task"]["id"] == task_id
        assert detail["plan"]["plan_json"]["title"] == "Automated BOM Audit"

        # 4. Retrieve plan directly via GET /tasks/{task_id}/plan
        plan_resp = await client.get(f"/api/v1/tasks/{task_id}/plan", headers=headers)
        assert plan_resp.status_code == 200
        plan_data = plan_resp.json()
        assert plan_data["task_id"] == task_id
        assert len(plan_data["plan_json"]["steps"]) == 1


@pytest.mark.asyncio
async def test_plan_regeneration(client: AsyncClient):
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        new=AsyncMock(return_value=(MOCK_VALID_PLAN, MOCK_METADATA)),
    ):
        create_resp = await client.post(
            "/api/v1/tasks",
            json={"description": "Original task description"},
            headers=headers,
        )
        task_id = create_resp.json()["task"]["id"]

    # Re-plan with updated mock plan
    updated_plan = MOCK_VALID_PLAN.model_copy()
    updated_plan.title = "Regenerated Audit Plan"

    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        new=AsyncMock(return_value=(updated_plan, MOCK_METADATA)),
    ):
        regen_resp = await client.post(f"/api/v1/tasks/{task_id}/plan", headers=headers)
        assert regen_resp.status_code == 200
        assert regen_resp.json()["plan_json"]["title"] == "Regenerated Audit Plan"


@pytest.mark.asyncio
async def test_task_not_found_returns_404(client: AsyncClient):
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/tasks/nonexistent-task-id", headers=headers)
    assert resp.status_code == 404
