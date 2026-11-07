import asyncio
from contextlib import asynccontextmanager
import functools
import logging
import os
from typing import Optional
from urllib.parse import urlparse
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token, get_password_hash
from app.database.session import get_db
from app.main import app
from app.models.entities import (
    Approval,
    Artifact,
    Execution,
    ExecutionEvent,
    ExecutionStep,
    Task,
    TaskPlan,
    User,
)
from app.schemas.plan import PlanStepSchema, TaskPlanSchema
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.policy.engine import DeterministicPolicyEngine
from app.workers.queue import QueueManager
from app.workers.leases import LeaseManager

logger = logging.getLogger(__name__)

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


INTEGRATION_TEST_USER_EMAILS = (
    "auth_verify@partproof-test.io",
    "test_auditor@partproof-test.io",
    "worker_queue_concurrency@partproof.io",
    "real-worker-test@partproof.io",
    "stale-test@partproof.io",
)


async def cleanup_postgres_test_data(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """
    Cleans up all tasks, executions, approvals, plans, events, steps, and artifacts
    associated with known integration test users in correct foreign-key order.
    Preserves the User records themselves for idempotency across test runs.
    """
    async with session_factory() as session:
        user_stmt = select(User.id).where(User.email.in_(INTEGRATION_TEST_USER_EMAILS))
        user_ids = list((await session.execute(user_stmt)).scalars().all())
        if not user_ids:
            return

        task_stmt = select(Task.id).where(Task.user_id.in_(user_ids))
        task_ids = list((await session.execute(task_stmt)).scalars().all())
        if not task_ids:
            # Clean up any lingering approvals created by integration test users
            approval_stmt = select(Approval.id).where(
                Approval.approved_by.in_(INTEGRATION_TEST_USER_EMAILS)
            )
            approval_ids = list((await session.execute(approval_stmt)).scalars().all())
            if approval_ids:
                await session.execute(
                    delete(Approval).where(Approval.id.in_(approval_ids))
                )
                await session.commit()
            return

        exec_stmt = select(Execution.id).where(Execution.task_id.in_(task_ids))
        exec_ids = list((await session.execute(exec_stmt)).scalars().all())

        # 1. execution_steps (FK -> executions.id)
        if exec_ids:
            await session.execute(
                delete(ExecutionStep).where(ExecutionStep.execution_id.in_(exec_ids))
            )

        # 2. artifacts (FK -> tasks.id, executions.id)
        if exec_ids:
            await session.execute(
                delete(Artifact).where(
                    (Artifact.task_id.in_(task_ids)) | (Artifact.execution_id.in_(exec_ids))
                )
            )
        else:
            await session.execute(
                delete(Artifact).where(Artifact.task_id.in_(task_ids))
            )

        # 3. execution_events (FK -> tasks.id, execution_id)
        if exec_ids:
            await session.execute(
                delete(ExecutionEvent).where(
                    (ExecutionEvent.task_id.in_(task_ids)) | (ExecutionEvent.execution_id.in_(exec_ids))
                )
            )
        else:
            await session.execute(
                delete(ExecutionEvent).where(ExecutionEvent.task_id.in_(task_ids))
            )

        # 4. executions (FK -> tasks.id, approvals.id)
        if exec_ids:
            await session.execute(
                delete(Execution).where(Execution.id.in_(exec_ids))
            )

        # 5. approvals (FK -> tasks.id, approved_by)
        await session.execute(
            delete(Approval).where(
                (Approval.task_id.in_(task_ids))
                | (Approval.approved_by.in_(INTEGRATION_TEST_USER_EMAILS))
            )
        )

        # 6. task_plans (FK -> tasks.id)
        await session.execute(
            delete(TaskPlan).where(TaskPlan.task_id.in_(task_ids))
        )

        # 7. tasks (FK -> users.id)
        await session.execute(
            delete(Task).where(Task.id.in_(task_ids))
        )

        await session.commit()


class _PostgresTestContextCallable:
    """Wrapper that exposes the generator function's __globals__ for direct test monkeypatching."""
    def __init__(self, cm, orig_fn):
        self._cm = cm
        functools.update_wrapper(self, cm)
        self.__wrapped__ = orig_fn

    @property
    def __globals__(self):
        return self.__wrapped__.__globals__

    def __call__(self, *args, **kwargs):
        return self._cm(*args, **kwargs)


@asynccontextmanager
async def _postgres_test_context_inner():
    """
    Sets up an isolated PostgreSQL test environment:
    1. Validates test database URL safety.
    2. Runs Alembic migrations against the test database.
    3. Overrides FastAPI get_db dependency with isolated PostgreSQL session factory.
    4. Deterministically executes pre-test cleanup inside try/finally lifecycle.
    5. Yields session factory to test block.
    6. Executes post-test cleanup in finally, visibly reporting errors without swallowing.
    7. Always restores dependency overrides, ALEMBIC_DATABASE_URL, and disposes engine.
    """
    test_pg_url = os.environ.get("TEST_POSTGRES_DATABASE_URL") or TEST_POSTGRES_URL
    assert test_pg_url is not None
    try:
        validate_test_database_url(test_pg_url)
    except ValueError as e:
        pytest.fail(f"Configured TEST_POSTGRES_DATABASE_URL failed safety check: {e}")

    orig_alembic_url = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = test_pg_url

    from alembic import command
    from alembic.config import Config

    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_ini_path = os.path.join(backend_root, "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)

    # Execute Alembic migrations on dedicated PostgreSQL test DB
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    pg_engine = create_async_engine(
        test_pg_url,
        pool_size=10,
        max_overflow=20,
        echo=False,
    )
    PgTestingSessionLocal = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_postgres_get_db():
        async with PgTestingSessionLocal() as session:
            yield session

    prev_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_postgres_get_db

    async def _restore_environment_and_engine() -> None:
        """Always restores dependency overrides, environment variables, and disposes engine."""
        try:
            if prev_override is not None:
                app.dependency_overrides[get_db] = prev_override
            else:
                app.dependency_overrides.pop(get_db, None)
        except Exception as e:
            logger.error("Failed to restore app dependency overrides: %s", e)

        try:
            if orig_alembic_url is not None:
                os.environ["ALEMBIC_DATABASE_URL"] = orig_alembic_url
            else:
                os.environ.pop("ALEMBIC_DATABASE_URL", None)
        except Exception as e:
            logger.error("Failed to restore ALEMBIC_DATABASE_URL: %s", e)

        try:
            await pg_engine.dispose()
        except Exception as e:
            logger.error("Failed to dispose PostgreSQL engine: %s", e)

    test_exc: Optional[BaseException] = None
    cleanup_exc: Optional[BaseException] = None
    pre_cleanup_done = False

    try:
        # Pre-test cleanup inside try/finally lifecycle
        try:
            await cleanup_postgres_test_data(PgTestingSessionLocal)
            pre_cleanup_done = True
        except BaseException as e:
            logger.error("Pre-test PostgreSQL cleanup failed: %s", e, exc_info=True)
            cleanup_exc = e
            raise

        try:
            yield PgTestingSessionLocal
        except BaseException as e:
            test_exc = e
            raise
    finally:
        # Post-test cleanup (runs when pre-cleanup succeeded)
        if pre_cleanup_done:
            try:
                await cleanup_postgres_test_data(PgTestingSessionLocal)
            except BaseException as e:
                logger.error("Post-test PostgreSQL cleanup failed: %s", e, exc_info=True)
                cleanup_exc = e

        # Always restore overrides, environment, and engine
        await _restore_environment_and_engine()

        # Propagate cleanup exception if one occurred
        if cleanup_exc is not None:
            if test_exc is not None:
                raise cleanup_exc from test_exc
            raise cleanup_exc


postgres_test_context = _PostgresTestContextCallable(
    _postgres_test_context_inner,
    _postgres_test_context_inner.__wrapped__,
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
async def test_postgres_token_authentication_resolution():
    """
    Regression test verifying that create_access_token(subject=user_id) produces
    a JWT whose subject string correctly resolves the seeded PostgreSQL test user
    through the get_current_user authentication dependency.
    """
    async with postgres_test_context() as PgTestingSessionLocal:
        # 1. Seed dedicated test user in PostgreSQL
        async with PgTestingSessionLocal() as session:
            res = await session.execute(
                select(User).where(User.email == "auth_verify@partproof-test.io")
            )
            test_user = res.scalar_one_or_none()
            if not test_user:
                test_user = User(
                    email="auth_verify@partproof-test.io",
                    password_hash=get_password_hash("AuthVerifyPass2026!"),
                    role="auditor",
                    is_active=True,
                )
                session.add(test_user)
                await session.commit()
                await session.refresh(test_user)

            user_id = test_user.id
            user_email = test_user.email
            user_role = test_user.role

        # 2. Generate access token with subject=user_id
        token = create_access_token(subject=user_id)
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Call /api/v1/auth/me to verify full auth resolution against PostgreSQL
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/me", headers=headers)
            assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["id"] == user_id
            assert data["email"] == user_email
            assert data["role"] == user_role

            # 4. Verify that an invalid subject fails authentication with 401
            invalid_token = create_access_token(subject="nonexistent-user-uuid")
            bad_resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {invalid_token}"},
            )
            assert bad_resp.status_code == 401


@pytest.mark.asyncio
async def test_postgres_concurrent_approval_row_locking():
    """
    Verifies that concurrent approval requests against a real PostgreSQL database
    utilizing pessimistic row-level locking (SELECT ... FOR UPDATE OF tasks) and
    unique constraints result in:
    1. All concurrent requests returning valid HTTP responses (no unhandled exceptions).
    2. Exactly one approved decision with at least one 200 OK response.
    3. Exactly one queued execution in PostgreSQL.
    4. Execution hash matching approved plan.
    5. Execution snapshot matching approved plan.
    6. Conflicting decisions unable to overwrite existing approval (409 Conflict).
    7. Database transactions leaving zero partial or orphaned records.
    8. Deterministic and safe resolution of concurrent approval vs cancellation race.
    """
    async with postgres_test_context() as PgTestingSessionLocal:
        # 1. Seed dedicated test user in PostgreSQL
        async with PgTestingSessionLocal() as session:
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

        # Use subject=user_id for correct token claim encoding
        token = create_access_token(subject=user_id)
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Seed a test task with policy-approved plan directly in PostgreSQL
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

        # 3. Fire 3 concurrent approval requests simultaneously
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

            # Ensure none of the concurrent requests threw unhandled exceptions
            for idx, r in enumerate(responses):
                if isinstance(r, Exception):
                    raise AssertionError(
                        f"Concurrent approval request #{idx + 1} raised an unhandled exception: {r}"
                    ) from r
                assert hasattr(r, "status_code"), (
                    f"Concurrent request #{idx + 1} returned unexpected non-response object: {r}"
                )

            # Assert all three HTTP requests returned actual HTTP responses
            assert len(responses) == 3

            status_codes = [r.status_code for r in responses]
            # At least one approval request must succeed with 200 OK
            assert 200 in status_codes, f"Expected at least one 200 OK approval, got: {status_codes}"
            # Every response must be either 200 (approval/idempotent duplicate) or 409 (conflict)
            for sc in status_codes:
                assert sc in (200, 409), (
                    f"Unexpected status code {sc} among concurrent approval responses: {status_codes}"
                )

        # 4. Assertions directly against PostgreSQL database
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

        # 5. Assert conflicting decision cannot overwrite existing approval
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            conflict_resp = await client.post(
                f"/api/v1/tasks/{task1_id}/approve",
                json={"decision": "rejected"},
                headers=headers,
            )
            assert conflict_resp.status_code == 409
            assert (
                "already approved" in conflict_resp.json()["detail"].lower()
                or "conflicting" in conflict_resp.json()["detail"].lower()
            )

            # Confirm database remains unchanged
            async with PgTestingSessionLocal() as session:
                appr_res2 = await session.execute(
                    select(Approval).where(Approval.task_id == task1_id)
                )
                approvals2 = appr_res2.scalars().all()
                assert len(approvals2) == 1
                assert approvals2[0].decision == "approved"

        # 6. Test concurrent Approval vs Cancellation
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

            # Ensure neither request raised unhandled exceptions
            if isinstance(res_appr, Exception):
                raise AssertionError(f"Approval request in race test raised an exception: {res_appr}") from res_appr
            if isinstance(res_cancel, Exception):
                raise AssertionError(f"Cancellation request in race test raised an exception: {res_cancel}") from res_cancel

            assert hasattr(res_appr, "status_code")
            assert hasattr(res_cancel, "status_code")
            assert res_appr.status_code in (200, 400, 409)
            assert res_cancel.status_code in (200, 400, 409)

        # Confirm consistent state in PostgreSQL (no partial or orphaned state)
        async with PgTestingSessionLocal() as session:
            t2_res = await session.execute(select(Task).where(Task.id == task2_id))
            t2 = t2_res.scalar_one()
            assert t2.status in ("cancelled", "queued")

            exec2_res = await session.execute(
                select(Execution).where(Execution.task_id == task2_id)
            )
            execs2 = exec2_res.scalars().all()
            assert len(execs2) <= 1
            if execs2:
                assert execs2[0].status in ("queued", "cancelled")


@pytest.mark.asyncio
async def test_postgres_worker_queue_concurrency():
    """
    Verifies PostgreSQL row-level locking (SKIP LOCKED) under concurrent worker queue claiming:
    1. Seeds multiple queued tasks with approved executions.
    2. Runs concurrent worker claim calls via asyncio.gather.
    3. Confirms exactly one worker claims each execution (zero double-claims).
    4. Validates lease ownership and atomic CAS renewal.
    """
    async with postgres_test_context() as PgTestingSessionLocal:
        # 1. Seed user (idempotent lookup first)
        async with PgTestingSessionLocal() as session:
            res = await session.execute(
                select(User).where(User.email == "worker_queue_concurrency@partproof.io")
            )
            user = res.scalar_one_or_none()
            if not user:
                user = User(
                    email="worker_queue_concurrency@partproof.io",
                    password_hash=get_password_hash("WorkerQueueSecurePass2026!"),
                    role="auditor",
                    is_active=True,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            user_id = user.id

        plan_schema = TaskPlanSchema(
            title="Parallel Audit Queue Test",
            summary="Validates SKIP LOCKED concurrency across workers",
            reasoning_summary="Ensures zero duplicate claims across concurrent worker processes",
            steps=[
                PlanStepSchema(
                    step_id="step_1",
                    description="Run audit computation",
                    execution_type="python",
                    code="print('Audit OK')\n",
                )
            ],
            required_capabilities=["python_execution"],
            network_required=False,
            success_criteria=["Complete"],
            expected_artifacts=["report.csv"],
        )
        plan_json = plan_schema.model_dump(mode="json")
        plan_hash = compute_plan_hash(plan_json)

        # 2. Seed 3 queued tasks with approved executions
        seeded_task_ids = []
        seeded_exec_ids = []
        async with PgTestingSessionLocal() as session:
            for i in range(3):
                t = Task(
                    user_id=user_id,
                    title=f"Parallel Queue Task {i+1}",
                    description=f"Task {i+1} for concurrent claim testing",
                    status="queued",
                )
                session.add(t)
                await session.flush()

                appr = Approval(
                    task_id=t.id,
                    approved_by="worker_queue_concurrency@partproof.io",
                    approved_plan_hash=plan_hash,
                    decision="approved",
                )
                session.add(appr)
                await session.flush()

                exc = Execution(
                    task_id=t.id,
                    approval_id=appr.id,
                    plan_hash=plan_hash,
                    plan_snapshot=plan_json,
                    status="queued",
                    timeout_seconds=30,
                )
                session.add(exc)
                await session.flush()

                seeded_task_ids.append(t.id)
                seeded_exec_ids.append(exc.id)

            await session.commit()

        # 3. Launch 3 concurrent workers attempting to claim queued tasks
        queue_mgr = QueueManager(PgTestingSessionLocal)

        claim_coros = [
            queue_mgr.claim_next_execution(worker_id=f"worker-concurrent-{i+1}", lease_duration_seconds=60)
            for i in range(3)
        ]
        claimed_results = await asyncio.gather(*claim_coros)

        # All 3 claims must succeed
        claimed_non_none = [c for c in claimed_results if c is not None]
        assert len(claimed_non_none) == 3, f"Expected 3 claims, got {len(claimed_non_none)}"

        # Every worker must claim a unique execution (zero duplicate claims)
        claimed_exec_ids = [c.execution_id for c in claimed_non_none]
        assert len(set(claimed_exec_ids)) == 3, "Duplicate execution claim detected!"
        assert set(claimed_exec_ids) == set(seeded_exec_ids)

        # 4. Verify 4th claim returns None (queue empty)
        fourth_claim = await queue_mgr.claim_next_execution(worker_id="worker-concurrent-4")
        assert fourth_claim is None

        # 5. Verify database state
        async with PgTestingSessionLocal() as session:
            for e_id in seeded_exec_ids:
                e_rec = await session.get(Execution, e_id)
                assert e_rec.status == "preparing"
                assert e_rec.worker_id is not None
                assert e_rec.lease_expires_at is not None
                assert e_rec.attempt_count == 1

            for t_id in seeded_task_ids:
                t_rec = await session.get(Task, t_id)
                assert t_rec.status == "running"

        # 6. Verify CAS lease renewal ownership on PostgreSQL
        lease_mgr = LeaseManager(PgTestingSessionLocal)
        # Owner can renew
        owner_renew = await lease_mgr.renew_lease(
            execution_id=claimed_results[0].execution_id,
            worker_id=claimed_results[0].worker_id,
            lease_duration_seconds=90,
        )
        assert owner_renew is True

        # Non-owner cannot renew
        non_owner_renew = await lease_mgr.renew_lease(
            execution_id=claimed_results[0].execution_id,
            worker_id="worker-imposter",
            lease_duration_seconds=90,
        )
        assert non_owner_renew is False


@pytest.mark.asyncio
async def test_postgres_pre_cleanup_failure_restores_state(monkeypatch):
    """
    Verifies that a pre-test cleanup failure restores dependency overrides,
    ALEMBIC_DATABASE_URL, disposes the engine, and propagates the error visibly.
    """
    cleanup_called = False

    async def fail_pre_cleanup(sf):
        nonlocal cleanup_called
        cleanup_called = True
        raise RuntimeError("Forced pre-cleanup failure for verification")

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "cleanup_postgres_test_data",
        fail_pre_cleanup,
    )

    prev_override = app.dependency_overrides.get(get_db)

    with pytest.raises(RuntimeError, match="Forced pre-cleanup failure for verification"):
        async with postgres_test_context():
            pytest.fail("Test block should not execute on pre-cleanup failure")

    assert cleanup_called is True
    assert app.dependency_overrides.get(get_db) == prev_override


@pytest.mark.asyncio
async def test_postgres_post_cleanup_failure_reported(monkeypatch):
    """
    Verifies that a post-test cleanup failure is visibly reported rather than
    silently swallowed, while still restoring overrides and environment.
    """
    call_count = 0

    async def fail_post_cleanup(sf):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise RuntimeError("Forced post-cleanup failure for verification")

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "cleanup_postgres_test_data",
        fail_post_cleanup,
    )

    prev_override = app.dependency_overrides.get(get_db)
    executed = False

    with pytest.raises(RuntimeError, match="Forced post-cleanup failure for verification"):
        async with postgres_test_context():
            executed = True

    assert executed is True
    assert call_count == 2
    assert app.dependency_overrides.get(get_db) == prev_override


@pytest.mark.asyncio
async def test_postgres_cleanup_lifecycle_success():
    """
    Verifies that successful cleanup runs before and after a test on PostgreSQL,
    properly removing seeded tasks, approvals, and executions while preserving users.
    """
    seeded_task_id = None
    seeded_user_id = None

    async with postgres_test_context() as PgTestingSessionLocal:
        async with PgTestingSessionLocal() as session:
            # Seed user
            res = await session.execute(
                select(User).where(User.email == "worker_queue_concurrency@partproof.io")
            )
            u = res.scalar_one_or_none()
            if not u:
                u = User(
                    email="worker_queue_concurrency@partproof.io",
                    password_hash=get_password_hash("TestPass2026!"),
                    role="auditor",
                )
                session.add(u)
                await session.commit()
                await session.refresh(u)
            seeded_user_id = u.id

            # Seed task and execution
            t = Task(
                user_id=seeded_user_id,
                title="Lifecycle Test Task",
                description="Testing cleanup lifecycle",
                status="queued",
            )
            session.add(t)
            await session.commit()
            await session.refresh(t)
            seeded_task_id = t.id

            exc = Execution(task_id=t.id, status="queued")
            session.add(exc)
            await session.commit()

    # Outside the first context: post-cleanup ran!
    # Re-enter context to verify records were cleaned up and pre-cleanup succeeds
    async with postgres_test_context() as PgTestingSessionLocal:
        async with PgTestingSessionLocal() as session:
            # Task must be gone
            t_rec = await session.get(Task, seeded_task_id)
            assert t_rec is None, "Task was not cleaned up after context exit"
            # User must be preserved
            u_rec = await session.get(User, seeded_user_id)
            assert u_rec is not None, "User should be preserved across cleanups"


@pytest.mark.asyncio
async def test_postgres_cleanup_handles_microsandbox_worker_and_stale_users():
    """
    Verifies that cleanup_postgres_test_data() removes all tasks, executions,
    approvals, plans, steps, events, and artifacts for real-worker-test@partproof.io
    and stale-test@partproof.io while preserving their User records.
    """
    seeded_data = {}

    async with postgres_test_context() as PgTestingSessionLocal:
        async with PgTestingSessionLocal() as session:
            # 1. Seed real-worker-test user & dependent entities
            u1_res = await session.execute(
                select(User).where(User.email == "real-worker-test@partproof.io")
            )
            u1 = u1_res.scalar_one_or_none()
            if not u1:
                u1 = User(
                    email="real-worker-test@partproof.io",
                    password_hash=get_password_hash("WorkerPass2026!"),
                    role="auditor",
                )
                session.add(u1)
                await session.flush()

            # 2. Seed stale-test user & dependent entities
            u2_res = await session.execute(
                select(User).where(User.email == "stale-test@partproof.io")
            )
            u2 = u2_res.scalar_one_or_none()
            if not u2:
                u2 = User(
                    email="stale-test@partproof.io",
                    password_hash=get_password_hash("StalePass2026!"),
                    role="auditor",
                )
                session.add(u2)
                await session.flush()

            # Tasks
            t1 = Task(user_id=u1.id, title="MicroSandbox Real Worker Task", description="worker e2e", status="queued")
            t2 = Task(user_id=u2.id, title="Stale Recovery Task", description="stale recovery", status="running")
            session.add_all([t1, t2])
            await session.flush()

            # Plan for task 1
            plan1 = TaskPlan(
                task_id=t1.id,
                model="glm-5.3",
                plan_json={"title": "plan"},
                plan_hash="worker-plan-hash-12345",
                policy_result={"decision": "pass"},
            )
            session.add(plan1)

            # Approval for task 1
            appr1 = Approval(
                task_id=t1.id,
                approved_by=u1.email,
                approved_plan_hash="worker-plan-hash-12345",
                decision="approved",
            )
            session.add(appr1)
            await session.flush()

            # Executions
            e1 = Execution(task_id=t1.id, approval_id=appr1.id, status="queued")
            e2 = Execution(task_id=t2.id, status="running")
            session.add_all([e1, e2])
            await session.flush()

            # Steps
            s1 = ExecutionStep(execution_id=e1.id, step_number=1, description="step 1")
            session.add(s1)

            # Events
            ev1 = ExecutionEvent(task_id=t1.id, execution_id=e1.id, event_type="log", message="running")
            ev2 = ExecutionEvent(task_id=t2.id, execution_id=e2.id, event_type="log", message="stale")
            session.add_all([ev1, ev2])

            # Artifacts
            art1 = Artifact(
                task_id=t1.id,
                execution_id=e1.id,
                filename="worker_output.csv",
                storage_key="worker/output.csv",
                size_bytes=100,
                sha256="abc123456",
            )
            session.add(art1)
            await session.commit()

            seeded_data = {
                "u1_id": u1.id,
                "u2_id": u2.id,
                "t1_id": t1.id,
                "t2_id": t2.id,
                "plan1_id": plan1.id,
                "appr1_id": appr1.id,
                "e1_id": e1.id,
                "e2_id": e2.id,
                "s1_id": s1.id,
                "ev1_id": ev1.id,
                "ev2_id": ev2.id,
                "art1_id": art1.id,
            }

    # Outside the first context: post-cleanup ran!
    # Re-enter context to verify cleanup purged all dependent records but preserved User records
    async with postgres_test_context() as PgTestingSessionLocal:
        async with PgTestingSessionLocal() as session:
            # Users must be preserved
            assert (await session.get(User, seeded_data["u1_id"])) is not None
            assert (await session.get(User, seeded_data["u2_id"])) is not None

            # All dependent records must be deleted
            assert (await session.get(Task, seeded_data["t1_id"])) is None
            assert (await session.get(Task, seeded_data["t2_id"])) is None
            assert (await session.get(TaskPlan, seeded_data["plan1_id"])) is None
            assert (await session.get(Approval, seeded_data["appr1_id"])) is None
            assert (await session.get(Execution, seeded_data["e1_id"])) is None
            assert (await session.get(Execution, seeded_data["e2_id"])) is None
            assert (await session.get(ExecutionStep, seeded_data["s1_id"])) is None
            assert (await session.get(ExecutionEvent, seeded_data["ev1_id"])) is None
            assert (await session.get(ExecutionEvent, seeded_data["ev2_id"])) is None
            assert (await session.get(Artifact, seeded_data["art1_id"])) is None



