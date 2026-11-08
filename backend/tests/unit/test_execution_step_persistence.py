import asyncio
import os
import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Execution, ExecutionStep, ExecutionEvent, Task, TaskPlan, User
from app.schemas.execution import ExecutionStepRead
from app.services.sandbox.base import StepExecutionOutput, MultiStepExecutionResult
from app.workers.execution_worker import ExecutionWorker


@pytest.mark.asyncio
async def test_execution_step_long_description_persistence(db_session: AsyncSession):
    """
    Priority 1 Test: Proves that an execution step with a description longer than 255 chars
    persists successfully in the database without throwing StringDataRightTruncation / DataError.
    """
    task = Task(
        title="Long Description Verification Task",
        description="Verify database accommodates descriptions exceeding legacy 255 limit",
        status="running",
    )
    db_session.add(task)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        status="running",
        runtime_image="partproof-runtime:v1",
        cpu_limit=1,
        memory_limit_mb=512,
        network_mode="none",
    )
    db_session.add(execution)
    await db_session.flush()

    long_description = (
        "Phase 1 Detailed Forensic Inspection of MicroVM Guest Filesystem: "
        "Iteratively inspecting directory tree under /workspace/output and /workspace/input, "
        "computing cryptographic SHA-256 digests across 40 distinct firmware modules, "
        "verifying compliance against airgapped policy constraints and validating deterministic hash chain integrity."
    )
    assert len(long_description) > 255, f"Expected description > 255, got {len(long_description)}"

    step = ExecutionStep(
        execution_id=execution.id,
        step_number=1,
        attempt_number=1,
        description=long_description,
        execution_type="python",
        code="print('Testing long description persistence')",
        status="succeeded",
        stdout="OK",
        exit_code=0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(step)
    await db_session.commit()

    # Query back and verify persistence
    stmt = select(ExecutionStep).where(ExecutionStep.execution_id == execution.id)
    res = await db_session.execute(stmt)
    saved_step = res.scalar_one()

    assert saved_step.description == long_description
    assert len(saved_step.description) > 255
    assert saved_step.status == "succeeded"
    assert saved_step.attempt_number == 1
    assert saved_step.exit_code == 0


@pytest.mark.asyncio
async def test_execution_step_long_code_stdout_stderr_persistence(db_session: AsyncSession):
    """
    Priority 1 Test: Proves that large code blocks, stdout, and stderr (> 10KB)
    persist without truncation or failure.
    """
    task = Task(title="Large Output Task", description="Testing large buffers", status="running")
    db_session.add(task)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        status="running",
        runtime_image="partproof-runtime:v1",
        cpu_limit=1,
        memory_limit_mb=512,
        network_mode="none",
    )
    db_session.add(execution)
    await db_session.flush()

    large_code = "# Large Python Script\n" + ("x = 42\n" * 1000)
    large_stdout = "LOG LINE: " + ("abcdefghij" * 2000)  # ~20KB
    large_stderr = "STDERR TRACE:\n" + ("Traceback line error\n" * 500)

    step = ExecutionStep(
        execution_id=execution.id,
        step_number=2,
        attempt_number=2,
        description="Executing compute-heavy script with large log buffers",
        execution_type="python",
        code=large_code,
        status="failed",
        stdout=large_stdout,
        stderr=large_stderr,
        exit_code=1,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(step)
    await db_session.commit()

    stmt = select(ExecutionStep).where(ExecutionStep.execution_id == execution.id, ExecutionStep.step_number == 2)
    res = await db_session.execute(stmt)
    saved_step = res.scalar_one()

    assert len(saved_step.code) > 5000
    assert len(saved_step.stdout) > 15000
    assert len(saved_step.stderr) > 5000
    assert saved_step.status == "failed"
    assert saved_step.attempt_number == 2
    assert saved_step.exit_code == 1


@pytest.mark.asyncio
async def test_worker_persistence_failure_marks_execution_failed():
    """
    Priority 1 Audit Behavior Test:
    If a persistence callback fails, the worker must retry and surface a real persistence failure.
    Never report a fully auditable successful execution when records could not be saved.
    """
    worker = ExecutionWorker()
    worker.worker_id = "test-worker-persistence"

    output = StepExecutionOutput(
        step_number=1,
        stdout="Output",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
        status="succeeded",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        description="Step 1 description",
        execution_type="python",
        code="print('hello')",
    )

    # Mock session factory where commit fails
    mock_session = AsyncMock()
    mock_session.bind.dialect.name = "sqlite"
    mock_session.execute.side_effect = RuntimeError("Database connection lost during step commit")

    def session_factory_mock():
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_session
        cm.__aexit__.return_value = False
        return cm

    worker.session_factory = session_factory_mock

    # Calling _persist_step_output should retry and ultimately raise
    with pytest.raises(RuntimeError) as exc_info:
        await worker._persist_step_output(
            execution_id="exec-123",
            task_id="task-123",
            attempt_number=1,
            output=output,
        )

    assert "Step persistence failed" in str(exc_info.value)
    assert worker._step_persistence_failed is True


@pytest.mark.asyncio
async def test_execution_steps_eagerly_loaded_for_task_detail(db_session: AsyncSession):
    """
    Priority 2 Test: Proves that get_task_detail query eagerly loads Execution.steps
    and populates ExecutionRead.steps without returning 0 steps.
    """
    task = Task(title="Detail Step Loading Task", description="Check eager relationship loading", status="succeeded")
    db_session.add(task)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        status="succeeded",
        runtime_image="partproof-runtime:v1",
        cpu_limit=1,
        memory_limit_mb=512,
        network_mode="none",
    )
    db_session.add(execution)
    await db_session.flush()

    step1 = ExecutionStep(
        execution_id=execution.id,
        step_number=1,
        attempt_number=1,
        description="Verify airgapped environment",
        execution_type="python",
        code="import sys; print(sys.version)",
        status="succeeded",
        stdout="Python 3.12.0",
        exit_code=0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    step2 = ExecutionStep(
        execution_id=execution.id,
        step_number=2,
        attempt_number=1,
        description="Perform cryptographic data integrity audit across input files",
        execution_type="python",
        code="print('Auditing artifacts')",
        status="succeeded",
        stdout="Verified 5 items",
        exit_code=0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add_all([step1, step2])
    await db_session.commit()

    # Emulate get_task_detail query with the eager selectinload path
    from sqlalchemy.orm import selectinload
    from app.api.v1.endpoints.tasks import _build_task_detail

    stmt = (
        select(Task)
        .where(Task.id == task.id)
        .options(
            selectinload(Task.plan),
            selectinload(Task.executions).selectinload(Execution.steps),
            selectinload(Task.executions).selectinload(Execution.artifacts),
            selectinload(Task.approvals),
            selectinload(Task.artifacts),
            selectinload(Task.events),
        )
    )
    res = await db_session.execute(stmt)
    loaded_task = res.scalar_one()

    detail = _build_task_detail(loaded_task)

    assert detail.latest_execution is not None
    assert len(detail.latest_execution.steps) == 2, f"Expected 2 steps, got {len(detail.latest_execution.steps)}"
    assert detail.latest_execution.steps[0].step_number == 1
    assert detail.latest_execution.steps[0].description == "Verify airgapped environment"
    assert detail.latest_execution.steps[0].attempt_number == 1
    assert detail.latest_execution.steps[1].step_number == 2
    assert detail.latest_execution.steps[1].stdout == "Verified 5 items"
