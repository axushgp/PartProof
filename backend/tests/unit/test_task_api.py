import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.entities import Approval, Execution, Task, TaskPlan
from app.schemas.plan import TaskPlanSchema
from app.services.inference.base import InferenceMetadata
from app.services.inference.exceptions import (
    InferenceAuthError,
    InferenceProviderError,
    InferenceTimeoutError,
    PlanValidationError,
)

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


@pytest.mark.asyncio
async def test_plan_regeneration_prohibited_when_approved_or_queued(client: AsyncClient):
    """Regeneration must be rejected with 409 once a plan has been approved and queued."""
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

    # Approve task
    approve_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved"},
        headers=headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["task"]["status"] == "queued"

    # Attempt to regenerate plan after approval
    regen_resp = await client.post(
        f"/api/v1/tasks/{task_id}/plan",
        headers=headers,
    )
    assert regen_resp.status_code == 409
    assert "already been approved" in regen_resp.json()["detail"].lower() or "execution" in regen_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_plan_regeneration_prohibited_when_in_flight_or_terminal(
    client: AsyncClient, db_session: AsyncSession
):
    """Regeneration must be rejected when task is running, succeeded, or cancelled."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    non_plannable_states = ["running", "succeeded", "cancelled"]

    for st in non_plannable_states:
        with patch(
            "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
            new=AsyncMock(return_value=(MOCK_VALID_PLAN, MOCK_METADATA)),
        ):
            create_resp = await client.post(
                "/api/v1/tasks",
                json={"description": f"Test task for state {st}"},
                headers=headers,
            )
            task_id = create_resp.json()["task"]["id"]

        # Mutate task to non-plannable status
        t = await db_session.get(Task, task_id)
        t.status = st
        await db_session.commit()

        # Attempt regeneration
        regen_resp = await client.post(f"/api/v1/tasks/{task_id}/plan", headers=headers)
        assert regen_resp.status_code == 409
        assert "cannot regenerate plan" in regen_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_plan_regeneration_allowed_after_rejection(client: AsyncClient, db_session: AsyncSession):
    """
    When a plan is rejected, regeneration is explicitly permitted.
    The new plan receives a new canonical hash and returns task to awaiting_approval,
    while prior rejection records in Approval are safely preserved.
    """
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
            json={"description": "Task to be rejected and replanned"},
            headers=headers,
        )
        task_id = create_resp.json()["task"]["id"]

    # Reject the initial plan
    reject_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "rejected", "reason": "Auditor rejected initial approach"},
        headers=headers,
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["task"]["status"] == "rejected"
    assert reject_resp.json()["plan"]["approval_status"] == "rejected"

    # Regenerate with a new revised plan
    revised_plan = MOCK_VALID_PLAN.model_copy()
    revised_plan.title = "Revised Audit Approach After Rejection"

    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        new=AsyncMock(return_value=(revised_plan, MOCK_METADATA)),
    ):
        regen_resp = await client.post(f"/api/v1/tasks/{task_id}/plan", headers=headers)
        assert regen_resp.status_code == 200
        new_plan = regen_resp.json()
        assert new_plan["plan_json"]["title"] == "Revised Audit Approach After Rejection"
        assert new_plan["approval_status"] == "pending"

    # Verify task state is now awaiting_approval
    detail_resp = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["task"]["status"] == "awaiting_approval"

    # Verify original rejection Approval record remains preserved in PostgreSQL/SQLite
    appr_res = await db_session.execute(select(Approval).where(Approval.task_id == task_id))
    approvals = appr_res.scalars().all()
    assert len(approvals) == 1
    assert approvals[0].decision == "rejected"
    assert approvals[0].reason == "Auditor rejected initial approach"


@pytest.mark.asyncio
async def test_plan_regeneration_rejected_when_already_planning(
    client: AsyncClient, db_session: AsyncSession
):
    """If a task is already undergoing planning, concurrent regeneration returns 409 Conflict."""
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
            json={"description": "Task for concurrent planning test"},
            headers=headers,
        )
        task_id = create_resp.json()["task"]["id"]

    # Manually mark task as planning
    t = await db_session.get(Task, task_id)
    t.status = "planning"
    await db_session.commit()

    # Attempt regeneration
    regen_resp = await client.post(f"/api/v1/tasks/{task_id}/plan", headers=headers)
    assert regen_resp.status_code == 409
    assert "currently undergoing planning" in regen_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_task_creation_inference_timeout_returns_504(client: AsyncClient):
    """Verifies that an InferenceTimeoutError during task creation maps to 504 Gateway Timeout."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        side_effect=InferenceTimeoutError("Vultr inference request timed out after fallback", model="glm-5.3-flash"),
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": "Task that triggers inference timeout"},
            headers=headers,
        )
        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_task_creation_connection_error_returns_503(client: AsyncClient):
    """Verifies that a provider network connection error maps to 503 Service Unavailable."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        side_effect=InferenceProviderError("Connection error to Vultr endpoint", status_code=503, model="glm-5.3"),
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": "Task that triggers connection error"},
            headers=headers,
        )
        assert resp.status_code == 503
        assert "Connection error" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_task_creation_auth_error_returns_502(client: AsyncClient):
    """Verifies that an upstream provider auth failure maps to 502 Bad Gateway without logging out user."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        side_effect=InferenceAuthError("Invalid API key", model="glm-5.3"),
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": "Task that triggers provider auth failure"},
            headers=headers,
        )
        assert resp.status_code == 502
        assert "Upstream AI inference authentication" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_task_creation_validation_error_returns_422(client: AsyncClient):
    """Verifies that PlanValidationError maps to 422 Unprocessable Entity."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        side_effect=PlanValidationError("Step code violates safety constraints"),
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": "Task with plan validation failure"},
            headers=headers,
        )
        assert resp.status_code == 422
        assert "Task planning failed" in resp.json()["detail"]
