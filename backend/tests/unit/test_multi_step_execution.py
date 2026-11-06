import pytest
from app.services.sandbox.base import (
    StepExecutionRequest,
    StepExecutionOutput,
    MultiStepExecutionResult,
)
from app.services.sandbox.manager import SandboxManager


@pytest.mark.asyncio
async def test_multi_step_execution_success():
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Extract purchase orders",
            code="print('Step 1 complete')\n",
        ),
        StepExecutionRequest(
            step_number=2,
            description="Cross reference parts catalog",
            code="print('Step 2 complete')\n",
        ),
    ]

    completed_steps = []
    async def _on_step_complete(step_num: int, output: StepExecutionOutput):
        completed_steps.append((step_num, output.status))

    res: MultiStepExecutionResult = await manager.execute_steps(
        task_id="test-task-1",
        execution_id="test-exec-1",
        steps=steps,
        expected_artifacts=["report.csv"],
        on_step_complete=_on_step_complete,
    )

    assert res.status == "succeeded"
    assert res.cleanup_status == "verified_destroyed"
    assert len(res.step_outputs) == 2
    assert res.step_outputs[0].status == "succeeded"
    assert res.step_outputs[1].status == "succeeded"
    assert len(completed_steps) == 2
    assert len(res.artifacts) == 1
    assert res.artifacts[0].filename == "report.csv"


@pytest.mark.asyncio
async def test_multi_step_fail_fast_on_error():
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Failing step",
            code="SIMULATE_ERROR\n",
        ),
        StepExecutionRequest(
            step_number=2,
            description="Dependent step",
            code="print('Should never run')\n",
        ),
    ]

    res = await manager.execute_steps(
        task_id="test-task-fail",
        execution_id="test-exec-fail",
        steps=steps,
    )

    assert res.status == "failed"
    assert res.cleanup_status == "verified_destroyed"
    assert len(res.step_outputs) == 2
    assert res.step_outputs[0].status == "failed"
    assert res.step_outputs[0].exit_code == 1
    # Step 2 must be marked skipped due to fail-fast
    assert res.step_outputs[1].status == "skipped"
    assert res.step_outputs[1].exit_code == -1


@pytest.mark.asyncio
async def test_multi_step_fail_fast_on_timeout():
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Timing out step",
            code="SIMULATE_TIMEOUT\n",
        ),
        StepExecutionRequest(
            step_number=2,
            description="Subsequent step",
            code="print('Should not run')\n",
        ),
    ]

    res = await manager.execute_steps(
        task_id="test-task-timeout",
        execution_id="test-exec-timeout",
        steps=steps,
    )

    assert res.status == "timed_out"
    assert res.cleanup_status == "verified_destroyed"
    assert len(res.step_outputs) == 2
    assert res.step_outputs[0].status == "timed_out"
    assert res.step_outputs[1].status == "skipped"


@pytest.mark.asyncio
async def test_multi_step_missing_declared_artifact_fails():
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Step simulating missing artifact",
            code="SIMULATE_MISSING_ARTIFACT\n",
        ),
    ]

    res = await manager.execute_steps(
        task_id="test-task-missing-art",
        execution_id="test-exec-missing-art",
        steps=steps,
        expected_artifacts=["required_output.csv"],
    )

    assert res.status == "failed"
    assert "Artifact collection failed" in (res.error_message or "")
    assert res.cleanup_status == "verified_destroyed"


@pytest.mark.asyncio
async def test_multi_step_cancellation_callback():
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="First step",
            code="print('Step 1 done')\n",
        ),
        StepExecutionRequest(
            step_number=2,
            description="Second step",
            code="print('Step 2 done')\n",
        ),
    ]

    cancel_call_count = 0
    async def _check_cancel():
        nonlocal cancel_call_count
        cancel_call_count += 1
        # Cancel before step 2
        return cancel_call_count >= 2

    res = await manager.execute_steps(
        task_id="test-task-cancel",
        execution_id="test-exec-cancel",
        steps=steps,
        check_cancellation=_check_cancel,
    )

    assert res.status == "cancelled"
    assert res.step_outputs[0].status == "succeeded"
    assert res.step_outputs[1].status == "skipped"


@pytest.mark.asyncio
async def test_multi_step_cleanup_failure_handled():
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Simulate cleanup failure",
            code="SIMULATE_CLEANUP_FAILURE\n",
        ),
    ]

    res = await manager.execute_steps(
        task_id="test-task-clean-fail",
        execution_id="test-exec-clean-fail",
        steps=steps,
    )

    assert res.cleanup_status == "failed"
