from unittest.mock import MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.database.session import Base, get_db
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
from tests.integration.test_postgres_concurrency import (
    cleanup_postgres_test_data,
    postgres_test_context,
)


@pytest.mark.asyncio
async def test_pre_cleanup_failure_restores_overrides_and_disposes_engine(monkeypatch):
    """
    Verifies that a failure during pre-test cleanup:
    1. Calls cleanup and propagates the exception visibly (never swallowed).
    2. Aborts test body execution.
    3. Restores FastAPI dependency overrides.
    4. Disposes the PostgreSQL engine cleanly.
    """
    monkeypatch.setenv(
        "TEST_POSTGRES_DATABASE_URL",
        "postgresql+asyncpg://test_auditor:test_pass@localhost:5432/partproof_test",
    )
    monkeypatch.setattr("alembic.command.upgrade", lambda *args, **kwargs: None)

    engine_disposed = False
    mock_engine = MagicMock()

    async def fake_dispose():
        nonlocal engine_disposed
        engine_disposed = True

    mock_engine.dispose = fake_dispose

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "create_async_engine",
        lambda *args, **kwargs: mock_engine,
    )

    cleanup_called = False

    async def fail_cleanup(session_factory):
        nonlocal cleanup_called
        cleanup_called = True
        raise RuntimeError("Simulated pre-test cleanup database failure")

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "cleanup_postgres_test_data",
        fail_cleanup,
    )

    prev_get_db = app.dependency_overrides.get(get_db)
    body_executed = False

    with pytest.raises(RuntimeError, match="Simulated pre-test cleanup database failure"):
        async with postgres_test_context():
            body_executed = True

    # Pre-cleanup must have actually executed
    assert cleanup_called is True
    # Body must not execute on pre-cleanup failure
    assert body_executed is False
    # Dependency override must be restored
    assert app.dependency_overrides.get(get_db) == prev_get_db
    # Engine must be disposed
    assert engine_disposed is True


@pytest.mark.asyncio
async def test_post_cleanup_failure_reported_and_restores_state(monkeypatch):
    """
    Verifies that a failure during post-test cleanup:
    1. Executes pre-cleanup and allows the test body to execute.
    2. Calls cleanup exactly twice and reports the second failure visibly.
    3. Restores FastAPI dependency overrides.
    4. Disposes the PostgreSQL engine cleanly.
    """
    monkeypatch.setenv(
        "TEST_POSTGRES_DATABASE_URL",
        "postgresql+asyncpg://test_auditor:test_pass@localhost:5432/partproof_test",
    )
    monkeypatch.setattr("alembic.command.upgrade", lambda *args, **kwargs: None)

    engine_disposed = False
    mock_engine = MagicMock()

    async def fake_dispose():
        nonlocal engine_disposed
        engine_disposed = True

    mock_engine.dispose = fake_dispose

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "create_async_engine",
        lambda *args, **kwargs: mock_engine,
    )

    cleanup_call_count = 0

    async def cleanup_side_effect(session_factory):
        nonlocal cleanup_call_count
        cleanup_call_count += 1
        if cleanup_call_count > 1:
            raise RuntimeError("Simulated post-test cleanup failure")

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "cleanup_postgres_test_data",
        cleanup_side_effect,
    )

    prev_get_db = app.dependency_overrides.get(get_db)
    body_executed = False

    with pytest.raises(RuntimeError, match="Simulated post-test cleanup failure"):
        async with postgres_test_context():
            body_executed = True

    assert body_executed is True
    assert cleanup_call_count == 2
    # Dependency override must be restored
    assert app.dependency_overrides.get(get_db) == prev_get_db
    # Engine must be disposed
    assert engine_disposed is True


@pytest.mark.asyncio
async def test_post_cleanup_failure_preserves_test_exception(monkeypatch):
    """
    Verifies that when both test body and post-cleanup fail:
    1. The cleanup failure is raised.
    2. The original test exception is preserved as the chained cause (__cause__).
    3. Cleanup is called exactly twice.
    4. Dependency overrides and engine are restored cleanly.
    """
    monkeypatch.setenv(
        "TEST_POSTGRES_DATABASE_URL",
        "postgresql+asyncpg://test_auditor:test_pass@localhost:5432/partproof_test",
    )
    monkeypatch.setattr("alembic.command.upgrade", lambda *args, **kwargs: None)

    engine_disposed = False
    mock_engine = MagicMock()

    async def fake_dispose():
        nonlocal engine_disposed
        engine_disposed = True

    mock_engine.dispose = fake_dispose

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "create_async_engine",
        lambda *args, **kwargs: mock_engine,
    )

    cleanup_call_count = 0

    async def cleanup_side_effect(session_factory):
        nonlocal cleanup_call_count
        cleanup_call_count += 1
        if cleanup_call_count > 1:
            raise RuntimeError("Simulated post-cleanup failure during failed test")

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "cleanup_postgres_test_data",
        cleanup_side_effect,
    )

    prev_get_db = app.dependency_overrides.get(get_db)

    with pytest.raises(RuntimeError, match="Simulated post-cleanup failure during failed test") as exc_info:
        async with postgres_test_context():
            raise AssertionError("Original assertion failure in test")

    # Original assertion error must be chained as __cause__
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, AssertionError)
    assert "Original assertion failure in test" in str(exc_info.value.__cause__)
    assert cleanup_call_count == 2

    # Dependency override must be restored
    assert app.dependency_overrides.get(get_db) == prev_get_db
    # Engine must be disposed
    assert engine_disposed is True


@pytest.mark.asyncio
async def test_successful_cleanup_lifecycle_before_and_after_test(monkeypatch):
    """
    Verifies that in the happy path:
    1. Pre-cleanup runs before test body.
    2. Overrides are set during test body.
    3. Post-cleanup runs after test body.
    4. Overrides are restored and engine is disposed.
    """
    monkeypatch.setenv(
        "TEST_POSTGRES_DATABASE_URL",
        "postgresql+asyncpg://test_auditor:test_pass@localhost:5432/partproof_test",
    )
    monkeypatch.setattr("alembic.command.upgrade", lambda *args, **kwargs: None)

    engine_disposed = False
    mock_engine = MagicMock()

    async def fake_dispose():
        nonlocal engine_disposed
        engine_disposed = True

    mock_engine.dispose = fake_dispose

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "create_async_engine",
        lambda *args, **kwargs: mock_engine,
    )

    cleanup_events = []

    async def tracking_cleanup(session_factory):
        cleanup_events.append("cleanup_called")

    monkeypatch.setitem(
        postgres_test_context.__globals__,
        "cleanup_postgres_test_data",
        tracking_cleanup,
    )

    prev_get_db = app.dependency_overrides.get(get_db)

    async with postgres_test_context() as session_factory:
        # Pre-cleanup must have completed
        assert len(cleanup_events) == 1
        # Overrides must be active
        assert app.dependency_overrides.get(get_db) is not None
        assert app.dependency_overrides.get(get_db) != prev_get_db
        assert engine_disposed is False

    # Post-cleanup must have completed
    assert len(cleanup_events) == 2
    # Dependency override must be restored
    assert app.dependency_overrides.get(get_db) == prev_get_db
    # Engine must be disposed
    assert engine_disposed is True


@pytest.mark.asyncio
async def test_cleanup_postgres_test_data_removes_worker_and_stale_user_records():
    """
    Verifies that cleanup_postgres_test_data removes all tasks, executions, approvals,
    plans, steps, events, and artifacts associated with real-worker-test@partproof.io
    and stale-test@partproof.io while preserving User records.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionFactory() as session:
        u1 = User(email="real-worker-test@partproof.io", password_hash="dummy")
        u2 = User(email="stale-test@partproof.io", password_hash="dummy")
        session.add_all([u1, u2])
        await session.flush()

        t1 = Task(user_id=u1.id, title="Worker Task", description="worker e2e", status="queued")
        t2 = Task(user_id=u2.id, title="Stale Task", description="stale recovery", status="running")
        session.add_all([t1, t2])
        await session.flush()

        plan = TaskPlan(
            task_id=t1.id,
            model="glm-5.3",
            plan_json={"title": "plan"},
            plan_hash="worker-plan-hash-12345",
            policy_result={"decision": "pass"},
        )
        session.add(plan)

        appr = Approval(
            task_id=t1.id,
            approved_by=u1.email,
            decision="approved",
        )
        session.add(appr)
        await session.flush()

        e1 = Execution(task_id=t1.id, approval_id=appr.id, status="queued")
        e2 = Execution(task_id=t2.id, status="running")
        session.add_all([e1, e2])
        await session.flush()

        step = ExecutionStep(execution_id=e1.id, step_number=1, description="step 1")
        session.add(step)

        ev1 = ExecutionEvent(task_id=t1.id, execution_id=e1.id, event_type="log", message="running")
        ev2 = ExecutionEvent(task_id=t2.id, execution_id=e2.id, event_type="log", message="stale")
        session.add_all([ev1, ev2])

        art = Artifact(
            task_id=t1.id,
            execution_id=e1.id,
            filename="out.csv",
            storage_key="k1",
            size_bytes=10,
            sha256="abc",
        )
        session.add(art)
        await session.commit()

        ids = {
            "u1": u1.id, "u2": u2.id,
            "t1": t1.id, "t2": t2.id,
            "plan": plan.id, "appr": appr.id,
            "e1": e1.id, "e2": e2.id,
            "step": step.id,
            "ev1": ev1.id, "ev2": ev2.id,
            "art": art.id,
        }

    # Execute cleanup
    await cleanup_postgres_test_data(SessionFactory)

    # Verify dependent records deleted, users preserved
    async with SessionFactory() as session:
        assert (await session.get(User, ids["u1"])) is not None
        assert (await session.get(User, ids["u2"])) is not None

        assert (await session.get(Task, ids["t1"])) is None
        assert (await session.get(Task, ids["t2"])) is None
        assert (await session.get(TaskPlan, ids["plan"])) is None
        assert (await session.get(Approval, ids["appr"])) is None
        assert (await session.get(Execution, ids["e1"])) is None
        assert (await session.get(Execution, ids["e2"])) is None
        assert (await session.get(ExecutionStep, ids["step"])) is None
        assert (await session.get(ExecutionEvent, ids["ev1"])) is None
        assert (await session.get(ExecutionEvent, ids["ev2"])) is None
        assert (await session.get(Artifact, ids["art"])) is None

    await engine.dispose()
