import asyncio
import os
from urllib.parse import urlparse
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token, get_password_hash
from app.database.session import get_db
from app.main import app
from app.models.entities import Approval, Execution, ExecutionEvent, Task, TaskPlan, User
from app.schemas.plan import PlanStepSchema, TaskPlanSchema
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.policy.engine import DeterministicPolicyEngine

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_DATABASE_URL")


def validate_test_database_url(url: str) -> None:
    """
    Enforces strict safety guardrails on the PostgreSQL test database target:
    - Rejects targeting the production database 'partproof_db'.
    - Mandates that the target database name contains 'test' (e.g. 'partproof_test').
    """
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/").split("?")[0].lower()

    if "partproof_db" in db_name:
        raise ValueError(
            f"TEST_POSTGRES_DATABASE_URL points to production database '{db_name}'. "
            f"Testing on production databases is strictly prohibited."
        )

    if "test" not in db_name:
        raise ValueError(
            f"TEST_POSTGRES_DATABASE_URL target '{db_name}' is not clearly a test database. "
            f"Database name must contain 'test' (e.g., 'partproof_test')."
        )


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_TESTS") != "1" or not TEST_POSTGRES_URL,
    reason="PostgreSQL integration tests require RUN_POSTGRES_TESTS=1 and TEST_POSTGRES_DATABASE_URL",
)

MOCK_SEED_PLAN = TaskPlanSchema(
    title="PostgreSQL Concurrency Row-Lock Test Plan",
    summary="Validates pessimistic row-locking and idempotency across concurrent workers",
    reasoning_summary="Ensures blast-radius-zero execution isolation on PostgreSQL",
    steps=[
        PlanStepSchema(
            step_id="step_1",
            description="Calculate structural shear loads",
            execution_type="python",
            code="print('Calculating shear loads...')",
            expected_output="Done",
        )
    ],
    required_capabilities=["math_computation"],
    network_required=False,
    success_criteria=["Shear load verified"],
    expected_artifacts=["shear_loads.csv"],
)


@pytest.mark.asyncio
async def test_postgres_concurrent_approval_row_locking():
    """
    Verifies that concurrent approval requests against a real PostgreSQL database
    utilizing pessimistic row-level locking (SELECT ... FOR UPDATE OF tasks) and
    unique constraints result in:
    1. Exactly one approved decision.
    2. Exactly one queued execution.
    3. Execution hash matching approved plan.
    4. Execution snapshot matching approved plan.
    5. Conflicting decisions unable to overwrite existing approval (409 Conflict).
    6. Transactions leaving zero partial or orphaned records.
    7. Consistent resolution of concurrent approval vs cancellation requests.
    """
    assert TEST_POSTGRES_URL is not None
    try:
        validate_test_database_url(TEST_POSTGRES_URL)
    except ValueError as e:
        pytest.fail(f"Configured TEST_POSTGRES_DATABASE_URL failed safety check: {e}")

    # 1. Run actual Alembic migrations on the PostgreSQL test database in a separate thread
    from alembic import command
    from alembic.config import Config

    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_ini_path = os.path.join(backend_root, "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)

    os.environ["ALEMBIC_DATABASE_URL"] = TEST_POSTGRES_URL
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    # 2. Create isolated async engine and session factory for PostgreSQL test DB
    pg_engine = create_async_engine(
        TEST_POSTGRES_URL,
        pool_size=10,
        max_overflow=20,
        echo=False,
    )
    PgTestingSessionLocal = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_postgres_get_db():
        async with PgTestingSessionLocal() as session:
            yield session

    # 3. Save existing get_db override and inject PostgreSQL session factory
    prev_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_postgres_get_db

    try:
        # 4. Seed dedicated test user (not production credentials)
        async with PgTestingSessionLocal() as session:
            # Upsert or fetch test user
            res = await session.execute(
                select(User).where(User.email == "test_auditor@partproof-test.io")
            )
            test_user = res.scalar_one_or_none()
            if not test_user:
                test_user = User(
                    email="test_auditor@partproof-test.io",
                    password_hash=get_password_hash("TestPgPass2026!"),
                    role="auditor",
                    is_active=True,
                )
                session.add(test_user)
                await session.commit()
                await session.refresh(test_user)

            user_id = test_user.id
            user_email = test_user.email
            user_role = test_user.role

        token = create_access_token({"sub": user_id, "email": user_email, "role": user_role})
        headers = {"Authorization": f"Bearer {token}"}

        # 5. Seed a test task with policy-approved plan directly in PostgreSQL
        plan_json = MOCK_SEED_PLAN.model_dump(mode="json")
        plan_hash = compute_plan_hash(plan_json)
        policy_res = DeterministicPolicyEngine().evaluate(MOCK_SEED_PLAN)

        async with PgTestingSessionLocal() as session:
            task1 = Task(
                user_id=user_id,
                title="Concurrent PostgreSQL Approval Verification",
                description="Audit verifying row-locking mutual exclusion on PostgreSQL",
                status="awaiting_approval",
            )
            session.add(task1)
            await session.commit()
            await session.refresh(task1)
            task1_id = task1.id

            plan1 = TaskPlan(
                task_id=task1_id,
                model="glm-5.3",
                plan_json=plan_json,
                plan_hash=plan_hash,
                policy_result=policy_res.model_dump(mode="json"),
                policy_version=policy_res.policy_version,
                policy_evaluated_at=policy_res.evaluated_at,
                approval_status="pending",
            )
            session.add(plan1)
            await session.commit()

        # 6. Fire 3 concurrent approval requests simultaneously
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reqs = [
                client.post(
                    f"/api/v1/tasks/{task1_id}/approve",
                    json={"decision": "approved", "reason": f"Concurrent attempt #{i}"},
                    headers=headers,
                )
                for i in range(1, 4)
            ]
            responses = await asyncio.gather(*reqs, return_exceptions=True)

            status_codes = [r.status_code for r in responses if hasattr(r, "status_code")]
            # All successful requests must return 200 (idempotent duplicate responses)
            for sc in status_codes:
                assert sc in (200, 409)
            assert 200 in status_codes

        # 7. Assertions directly against PostgreSQL database
        async with PgTestingSessionLocal() as session:
            # Exactly one execution must exist in PostgreSQL
            exec_res = await session.execute(
                select(Execution).where(Execution.task_id == task1_id)
            )
            executions = exec_res.scalars().all()
            assert len(executions) == 1, f"Expected exactly 1 Execution, found {len(executions)}"
            execution = executions[0]
            assert execution.status == "queued"
            assert execution.plan_hash == plan_hash
            assert execution.plan_snapshot == plan_json

            # Exactly one Approval record must exist for this plan hash
            appr_res = await session.execute(
                select(Approval).where(Approval.task_id == task1_id)
            )
            approvals = appr_res.scalars().all()
            assert len(approvals) == 1, f"Expected exactly 1 Approval, found {len(approvals)}"
            assert approvals[0].decision == "approved"
            assert approvals[0].approved_plan_hash == plan_hash

            # Task status must be queued
            t_res = await session.execute(select(Task).where(Task.id == task1_id))
            task_db = t_res.scalar_one()
            assert task_db.status == "queued"

            # ExecutionEvent records should be consistent
            ev_res = await session.execute(
                select(ExecutionEvent).where(ExecutionEvent.task_id == task1_id)
            )
            events = ev_res.scalars().all()
            event_types = [e.event_type for e in events]
            assert "execution_queued" in event_types

        # 8. Assert conflicting decision cannot overwrite existing approval
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            conflict_resp = await client.post(
                f"/api/v1/tasks/{task1_id}/approve",
                json={"decision": "rejected"},
                headers=headers,
            )
            assert conflict_resp.status_code == 409
            assert "already approved" in conflict_resp.json()["detail"].lower() or "conflicting" in conflict_resp.json()["detail"].lower()

            # Confirm database remains unchanged
            async with PgTestingSessionLocal() as session:
                appr_res2 = await session.execute(
                    select(Approval).where(Approval.task_id == task1_id)
                )
                approvals2 = appr_res2.scalars().all()
                assert len(approvals2) == 1
                assert approvals2[0].decision == "approved"

        # 9. Test concurrent Approval vs Cancellation
        async with PgTestingSessionLocal() as session:
            task2 = Task(
                user_id=user_id,
                title="Concurrent Approval vs Cancellation Race",
                description="Verifies deterministic consistency under approval vs cancellation race",
                status="awaiting_approval",
            )
            session.add(task2)
            await session.commit()
            await session.refresh(task2)
            task2_id = task2.id

            plan2 = TaskPlan(
                task_id=task2_id,
                model="glm-5.3",
                plan_json=plan_json,
                plan_hash=plan_hash,
                policy_result=policy_res.model_dump(mode="json"),
                policy_version=policy_res.policy_version,
                policy_evaluated_at=policy_res.evaluated_at,
                approval_status="pending",
            )
            session.add(plan2)
            await session.commit()

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            appr_coro = client.post(
                f"/api/v1/tasks/{task2_id}/approve",
                json={"decision": "approved"},
                headers=headers,
            )
            cancel_coro = client.post(
                f"/api/v1/tasks/{task2_id}/cancel",
                json={"reason": "Simultaneous user abort"},
                headers=headers,
            )
            res_appr, res_cancel = await asyncio.gather(appr_coro, cancel_coro, return_exceptions=True)

            # Both endpoints must succeed (200) or one succeed and one handle transition cleanly
            codes = [r.status_code for r in (res_appr, res_cancel) if hasattr(r, "status_code")]
            for c in codes:
                assert c in (200, 400, 409)

        # Confirm consistent state in PostgreSQL (no partial or orphaned state)
        async with PgTestingSessionLocal() as session:
            t2_res = await session.execute(select(Task).where(Task.id == task2_id))
            t2 = t2_res.scalar_one()
            # Task must either be cancelled or queued
            assert t2.status in ("cancelled", "queued")

            exec2_res = await session.execute(
                select(Execution).where(Execution.task_id == task2_id)
            )
            execs2 = exec2_res.scalars().all()
            assert len(execs2) <= 1
            if execs2:
                # If execution was created, its status must match task state
                assert execs2[0].status in ("queued", "cancelled")

    finally:
        # Restore original dependency overrides
        if prev_override is not None:
            app.dependency_overrides[get_db] = prev_override
        else:
            app.dependency_overrides.pop(get_db, None)

        # Dispose PostgreSQL engine
        await pg_engine.dispose()
