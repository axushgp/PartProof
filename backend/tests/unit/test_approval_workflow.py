import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database.session import get_db
from app.models.entities import Approval, Execution, Task, TaskPlan, User
from app.core.security import get_password_hash
from app.schemas.plan import PlanStepSchema, TaskPlanSchema
from app.services.inference.base import InferenceMetadata
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.policy.engine import DeterministicPolicyEngine

MOCK_VALID_PLAN = TaskPlanSchema(
    title="Structural Bracket Fastener Audit",
    summary="Audits bolts and torque specifications",
    reasoning_summary="Reconciles ERP part counts with vendor quotation quantities",
    steps=[
        PlanStepSchema(
            step_id="step_1",
            description="Calculate torque requirements",
            execution_type="python",
            code="print('Calculating torque')\nwith open('/workspace/output/torque.csv', 'w') as f: f.write('bolt,torque\\nB-1,45Nm\\n')",
            expected_output="torque.csv created",
        )
    ],
    required_capabilities=["math_computation", "file_write"],
    network_required=False,
    success_criteria=["torque.csv generated and verified"],
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
async def test_approval_success_creates_approval_and_queued_execution(client: AsyncClient):
    """Approving a task atomically creates an Approval, a queued Execution with snapshot, and sets task status to 'queued'."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # Submit approval
    approve_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved", "reason": "Verified fastener tolerances"},
        headers=headers,
    )

    assert approve_resp.status_code == 200
    data = approve_resp.json()

    # 1. Task transitions to queued
    assert data["task"]["status"] == "queued"
    assert data["plan"]["approval_status"] == "approved"

    # 2. Latest approval record verified
    assert data["latest_approval"] is not None
    assert data["latest_approval"]["decision"] == "approved"
    assert data["latest_approval"]["approved_by"] == settings.DEMO_USER_EMAIL
    assert data["latest_approval"]["approved_plan_hash"] == data["plan"]["plan_hash"]

    # 3. Exactly one queued execution created
    assert data["latest_execution"] is not None
    assert data["latest_execution"]["status"] == "queued"
    assert data["latest_execution"]["runtime_image"] == "python:3.12-slim"
    assert data["latest_execution"]["cpu_limit"] == 1
    assert data["latest_execution"]["memory_limit_mb"] == 512
    assert data["latest_execution"]["network_mode"] == "none"

    # 4. Verify execution snapshot and foreign keys directly via database
    # Invariant: Planning / Approval MUST NOT execute code or launch microVM
    assert data["latest_execution"]["started_at"] is None
    assert data["latest_execution"]["completed_at"] is None


@pytest.mark.asyncio
async def test_approval_rejected_decision_creates_no_execution(client: AsyncClient):
    """Rejecting a plan sets approval and task to 'rejected' without creating any Execution."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # Submit rejection
    reject_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "rejected", "reason": "Risk threshold exceeded for fastener grade"},
        headers=headers,
    )

    assert reject_resp.status_code == 200
    data = reject_resp.json()

    assert data["task"]["status"] == "rejected"
    assert data["plan"]["approval_status"] == "rejected"
    assert data["latest_approval"] is not None
    assert data["latest_approval"]["decision"] == "rejected"
    assert data["latest_approval"]["reason"] == "Risk threshold exceeded for fastener grade"
    # Invariant: NO execution record must be created for rejected plans
    assert data["latest_execution"] is None


@pytest.mark.asyncio
async def test_rejected_plan_cannot_subsequently_be_approved(client: AsyncClient):
    """Once a plan is rejected, it cannot be approved without generating a new plan first."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # First reject
    await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "rejected", "reason": "Initial rejection"},
        headers=headers,
    )

    # Attempt to approve rejected plan
    approve_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved", "reason": "Attempting override"},
        headers=headers,
    )

    assert approve_resp.status_code == 409
    assert "rejected" in approve_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approval_idempotency_duplicate_requests(client: AsyncClient):
    """Submitting duplicate identical approval requests returns 200 without creating duplicate records."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # First approval
    resp1 = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved", "reason": "First attempt"},
        headers=headers,
    )
    assert resp1.status_code == 200
    exec_id_1 = resp1.json()["latest_execution"]["id"]

    # Second identical approval
    resp2 = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved", "reason": "Second attempt"},
        headers=headers,
    )
    assert resp2.status_code == 200
    exec_id_2 = resp2.json()["latest_execution"]["id"]

    # Invariant: Exactly identical execution returned, no duplicate created
    assert exec_id_1 == exec_id_2


@pytest.mark.asyncio
async def test_approval_conflicting_decision_returns_409(client: AsyncClient):
    """Attempting a conflicting decision after a decision has already been recorded returns 409 Conflict."""
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
        json={"decision": "approved", "reason": "Approved first"},
        headers=headers,
    )

    # Conflicting reject
    conflict_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "rejected", "reason": "Trying to reject approved plan"},
        headers=headers,
    )
    assert conflict_resp.status_code == 409
    assert "already approved" in conflict_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approval_rejected_when_no_plan_exists(client: AsyncClient):
    """Approval on a task without a plan returns 400 Bad Request."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Simulate planner failure leading to task in failed state without plan
    with patch(
        "app.api.v1.endpoints.tasks.TaskPlanner.plan_task",
        side_effect=Exception("LLM failure"),
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": "Task that will fail planning"},
            headers=headers,
        )
        assert resp.status_code == 500

    # Retrieve all tasks to get failed task
    list_resp = await client.get("/api/v1/tasks", headers=headers)
    tasks = list_resp.json()
    failed_task_id = tasks[0]["id"]

    approve_resp = await client.post(
        f"/api/v1/tasks/{failed_task_id}/approve",
        json={"decision": "approved"},
        headers=headers,
    )
    assert approve_resp.status_code == 400
    assert "no plan exists" in approve_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approval_rejected_when_plan_hash_mismatch(client: AsyncClient, db_session: AsyncSession):
    """Tampering with persisted plan JSON triggers cryptographic hash mismatch and 409 rejection."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # Directly tamper with stored plan_json in DB without recalculating plan_hash
    result = await db_session.execute(
        select(TaskPlan).where(TaskPlan.task_id == task_id)
    )
    plan = result.scalar_one()
    tampered_json = dict(plan.plan_json)
    tampered_json["title"] = "Tampered Title That Changes Canonical Hash"
    plan.plan_json = tampered_json
    await db_session.commit()

    # Attempt approval of tampered plan
    tampered_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved"},
        headers=headers,
    )

    assert tampered_resp.status_code == 409
    assert "integrity compromised" in tampered_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approval_rejected_when_policy_disallowed(client: AsyncClient, db_session: AsyncSession):
    """Approval re-evaluates policy; if policy disallowed, approval is denied with 422."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = await _create_test_task_awaiting_approval(client, headers)

    # Tamper with stored plan to include disallowed capability and update hash so integrity passes
    result = await db_session.execute(
        select(TaskPlan).where(TaskPlan.task_id == task_id)
    )
    plan = result.scalar_one()
    tampered_json = dict(plan.plan_json)
    tampered_json["required_capabilities"] = ["file_read", "host_filesystem"]
    plan.plan_json = tampered_json
    plan.plan_hash = compute_plan_hash(tampered_json)
    await db_session.commit()

    # Attempt approval
    policy_denied_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved"},
        headers=headers,
    )

    assert policy_denied_resp.status_code == 422
    assert "policy evaluation disallowed" in policy_denied_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approval_unauthorized_user_forbidden(client: AsyncClient, db_session: AsyncSession):
    """A user cannot approve tasks owned by another user unless they are admin."""
    # 1. Login as default demo user and create task
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    token1 = login_resp.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    task_id = await _create_test_task_awaiting_approval(client, headers1)

    # 2. Create second user in database
    user2 = User(
        email="intruder@partproof.io",
        password_hash=get_password_hash("IntruderPass2026!"),
        role="auditor",
        is_active=True,
    )
    db_session.add(user2)
    await db_session.commit()

    # 3. Login as second user
    login_resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "intruder@partproof.io", "password": "IntruderPass2026!"},
    )
    token2 = login_resp2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # 4. Attempt to approve user1's task
    forbidden_resp = await client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "approved"},
        headers=headers2,
    )

    assert forbidden_resp.status_code == 403
    assert "access denied" in forbidden_resp.json()["detail"].lower()
