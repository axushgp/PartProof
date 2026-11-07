from unittest.mock import MagicMock
import pytest
from app.database.session import get_db
from app.main import app
from tests.integration.test_postgres_concurrency import postgres_test_context


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
