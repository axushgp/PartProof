import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import Execution, Task, User
from app.core.security import get_password_hash
from app.schemas.plan import PlanStepSchema, TaskPlanSchema
from app.services.inference.base import InferenceMetadata

MOCK_VALID_PLAN = TaskPlanSchema(
    title="Structural Fastener Audit",
    summary="Audits bolts and torque specifications",
    reasoning_summary="Reconciles ERP part counts with vendor quotation quantities",
    steps=[
        PlanStepSchema(
            step_id="step_1",
            description="Calculate torque requirements",
            execution_type="python",
            code="print('Calculating torque')",
            expected_output="Done",
        )
    ],
    required_capabilities=["math_computation"],
    network_required=False,
    success_criteria=["Torque computed"],
    expected_artifacts=["torque.csv"],
)

MOCK_METADATA = InferenceMetadata(
    provider="vultr",
    model="glm-5.3",
    prompt_tokens=100,
    completion_tokens=150,
    total_tokens=250,
    latency_ms=120.0,
    retries=0,
)


async def _create_test_task_awaiting_approval(client: AsyncClient, headers: dict) -> str:
    """Helper creating a task in awaiting_approval state."""
    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        new=AsyncMock(return_value=(MOCK_VALID_PLAN, MOCK_METADATA)),
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": "Audit supplier brackets and bolts"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["task"]["status"] == "awaiting_approval"
        return data["task"]["id"]


@pytest.mark.asyncio
async def test_cancellation_from_awaiting_approval(client: AsyncClient):
    """Cancelling a task in awaiting_approval safely marks both task and plan as cancelled."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # Cancel task
    cancel_resp = await client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={"reason": "User aborted before review"},
        headers=headers,
    )

    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["task"]["status"] == "cancelled"
    assert data["plan"]["approval_status"] == "cancelled"
    assert data["latest_execution"] is None


@pytest.mark.asyncio
async def test_cancellation_from_queued_cancels_execution(client: AsyncClient):
    """Cancelling a queued task atomically marks both the task and its queued Execution as cancelled."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # Approve task to move into queued state
    approve_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved"},
        headers=headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["task"]["status"] == "queued"
    assert approve_resp.json()["latest_execution"]["status"] == "queued"

    # Cancel task while queued
    cancel_resp = await client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={"reason": "Audit superseded by new procurement doc"},
        headers=headers,
    )

    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["task"]["status"] == "cancelled"
    assert data["latest_execution"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancellation_from_running_sets_cancel_requested(client: AsyncClient, db_session: AsyncSession):
    """Cancelling an active/running task sets cancel_requested without falsely claiming process stopped."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # Approve
    await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved"},
        headers=headers,
    )

    # Simulate worker picking up task and marking it running in database
    t = await db_session.get(Task, task_id)
    t.status = "running"
    result = await db_session.execute(
        select(Execution).where(Execution.task_id == task_id)
    )
    e = result.scalar_one()
    e.status = "running"
    e.started_at = datetime.now(timezone.utc)
    await db_session.commit()

    # Submit cancellation while running
    cancel_resp = await client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={"reason": "Operator abort command"},
        headers=headers,
    )

    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    # Invariant: Must report cancel_requested, NOT finished/cancelled
    assert data["task"]["status"] == "cancel_requested"
    assert data["latest_execution"]["status"] == "cancel_requested"


@pytest.mark.asyncio
async def test_cancellation_idempotent_on_cancelled_and_cancel_requested(client: AsyncClient):
    """Repeated cancellations on cancelled or cancel_requested tasks return 200 idempotently."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # Cancel once
    resp1 = await client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        headers=headers,
    )
    assert resp1.status_code == 200
    assert resp1.json()["task"]["status"] == "cancelled"

    # Cancel second time (idempotent repeat)
    resp2 = await client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["task"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancellation_terminal_states_rejected(client: AsyncClient, db_session: AsyncSession):
    """Tasks in terminal states (succeeded, failed, timed_out, rejected) cannot be cancelled."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    terminal_states = ["succeeded", "failed", "timed_out", "rejected"]

    for term_state in terminal_states:
        task_id = await _create_test_task_awaiting_approval(client, headers)

        # Set terminal state in DB
        t = await db_session.get(Task, task_id)
        t.status = term_state
        await db_session.commit()

        # Attempt to cancel
        cancel_resp = await client.post(
            f"/api/v1/tasks/{task_id}/cancel",
            headers=headers,
        )

        assert cancel_resp.status_code == 409
        assert "terminal state" in cancel_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cancellation_unauthorized_user_forbidden(client: AsyncClient, db_session: AsyncSession):
    """Users cannot cancel tasks belonging to another user."""
    # User 1 creates task
    login_resp1 = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token1 = login_resp1.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    task_id = await _create_test_task_awaiting_approval(client, headers1)

    # User 2 created in DB
    user2 = User(
        email="intruder2@partproof.io",
        password_hash=get_password_hash("IntruderPass2026!"),
        role="auditor",
        is_active=True,
    )
    db_session.add(user2)
    await db_session.commit()

    login_resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "intruder2@partproof.io", "password": "IntruderPass2026!"},
    )
    token2 = login_resp2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # User 2 attempts to cancel User 1's task
    forbidden_resp = await client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        headers=headers2,
    )
    assert forbidden_resp.status_code == 403
    assert "access denied" in forbidden_resp.json()["detail"].lower()
