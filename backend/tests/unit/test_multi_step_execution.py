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


@pytest.mark.asyncio
async def test_cumulative_overall_execution_deadline():
    """
    Verifies that multiple steps cannot each consume the full overall timeout.
    The total execution deadline is cumulative; when elapsed time exceeds the
    configured limit, subsequent steps are aborted with 'timed_out'.
    """
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="First sleeping step",
            code="SIMULATE_SLEEP\n",
            timeout_seconds=5.0,
        ),
        StepExecutionRequest(
            step_number=2,
            description="Second sleeping step",
            code="SIMULATE_SLEEP\n",
            timeout_seconds=5.0,
        ),
        StepExecutionRequest(
            step_number=3,
            description="Third step should be skipped",
            code="print('Should never run')\n",
            timeout_seconds=5.0,
        ),
    ]

    # Overall timeout is 1.0s; Step 1 takes 0.6s, leaving only 0.4s for Step 2.
    # Step 2 needs 0.6s, so the cumulative budget expires.
    res = await manager.execute_steps(
        task_id="test-task-cumulative-deadline",
        execution_id="test-exec-cumulative-deadline",
        steps=steps,
        timeout_seconds=1.0,
    )

    assert res.status == "timed_out"
    assert res.cleanup_status == "verified_destroyed"
    assert len(res.step_outputs) == 3
    # Step 3 must be skipped due to cumulative timeout expiration
    assert res.step_outputs[2].status == "skipped"
    assert res.step_outputs[2].exit_code == -1


@pytest.mark.asyncio
async def test_multi_step_provisioning_timeout():
    """
    Verifies that when microVM provisioning times out, execution halts immediately,
    all steps are marked skipped, and cleanup is executed.
    """
    from unittest.mock import patch

    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Should not execute due to provision timeout",
            code="print('Should not run')\n",
        ),
    ]

    # Patch adapter create to simulate provisioning exceeding budget
    async def _slow_create(self_adapter):
        import asyncio
        await asyncio.sleep(1.5)

    with patch("app.services.sandbox.mock_adapter.MockSandboxAdapter.create", _slow_create):
        # Budget is 1.0s, create takes 1.5s -> provisioning timeout
        res = await manager.execute_steps(
            task_id="test-task-prov-timeout",
            execution_id="test-exec-prov-timeout",
            steps=steps,
            timeout_seconds=1.0,  # minimum config
        )

    # If provisioning fails or times out, overall status is timed_out and steps are skipped
    assert res.status == "timed_out"
    assert len(res.step_outputs) == 1
    assert res.step_outputs[0].status == "skipped"
    assert res.cleanup_status == "verified_destroyed"


@pytest.mark.asyncio
async def test_multi_step_source_transfer_timeout():
    """
    Verifies that when guest source transfer times out in execute(),
    the step is recorded as timed_out and subsequent steps are skipped.
    """
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Source transfer times out",
            code="SIMULATE_SOURCE_TRANSFER_TIMEOUT\n",
        ),
        StepExecutionRequest(
            step_number=2,
            description="Second step skipped",
            code="print('skipped')\n",
        ),
    ]

    res = await manager.execute_steps(
        task_id="test-task-transfer-timeout",
        execution_id="test-exec-transfer-timeout",
        steps=steps,
        timeout_seconds=10.0,
    )

    assert res.status == "timed_out"
    assert len(res.step_outputs) == 2
    assert res.step_outputs[0].status == "timed_out"
    assert res.step_outputs[1].status == "skipped"
    assert res.cleanup_status == "verified_destroyed"


@pytest.mark.asyncio
async def test_multi_step_execution_timeout():
    """
    Verifies that when script execution times out in the microVM,
    the step is marked timed_out and remaining steps are skipped.
    """
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Script execution times out",
            code="SIMULATE_TIMEOUT\n",
        ),
        StepExecutionRequest(
            step_number=2,
            description="Subsequent step skipped",
            code="print('skipped')\n",
        ),
    ]

    res = await manager.execute_steps(
        task_id="test-task-exec-timeout",
        execution_id="test-exec-exec-timeout",
        steps=steps,
        timeout_seconds=10.0,
    )

    assert res.status == "timed_out"
    assert len(res.step_outputs) == 2
    assert res.step_outputs[0].status == "timed_out"
    assert res.step_outputs[1].status == "skipped"
    assert res.cleanup_status == "verified_destroyed"


@pytest.mark.asyncio
async def test_multi_step_cleanup_timeout():
    """
    Verifies that when microVM cleanup times out during the bounded grace period,
    cleanup_status is marked 'failed' and execution is not silently abandoned.
    """
    from unittest.mock import patch

    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Step triggers cleanup timeout",
            code="SIMULATE_CLEANUP_TIMEOUT\n",
        ),
    ]

    # Patch cleanup timeout grace period to a short window
    with patch("app.core.config.settings.SANDBOX_CLEANUP_TIMEOUT_SECONDS", 0.05):
        res = await manager.execute_steps(
            task_id="test-task-clean-timeout",
            execution_id="test-exec-clean-timeout",
            steps=steps,
            timeout_seconds=10.0,
        )

    assert res.cleanup_status == "failed"


@pytest.mark.asyncio
async def test_microsandbox_cancellation_during_provisioning_before_context_manager_assignment():
    """
    REGRESSION TEST:
    If MicroSandbox provisioning is cancelled or times out during Sandbox.create()
    BEFORE _sandbox_cm is assigned:
    1. _provision_attempted is True, but _sandbox_cm is None.
    2. destroy() must NEVER report verified_destroyed without proof.
    3. If CLI verification fails, destroy() must raise SandboxCleanupError.
    4. If CLI verification proves absence, destroy() returns verified_destroyed.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.sandbox.base import SandboxConfig, SandboxCleanupError
    from app.services.sandbox.microsandbox_adapter import MicrosandboxAdapter

    config = SandboxConfig(
        sandbox_id="partproof-test-cancel-001",
        image="python:3.12-slim",
        cpus=1,
        memory_mb=512,
        network="none",
        timeout_seconds=30,
        task_id="test-task-cancel",
        execution_id="test-exec-cancel",
    )
    adapter = MicrosandboxAdapter(config)

    # Mock SDK loading and Sandbox.create to simulate cancellation before context manager assignment
    mock_sandbox_cls = AsyncMock()
    mock_sandbox_cls.create.side_effect = asyncio.CancelledError("User cancelled during provisioning")
    mock_network_cls = AsyncMock()
    mock_network_cls.none.return_value = "none"

    with patch("app.services.sandbox.microsandbox_adapter._load_microsandbox_sdk", return_value=(mock_sandbox_cls, mock_network_cls)), \
         patch("os.path.exists", return_value=True):

        try:
            await adapter.create()
        except asyncio.CancelledError:
            pass

    # Verify state after partial/cancelled provisioning
    assert adapter._provision_attempted is True
    assert adapter._sandbox_cm is None
    assert adapter._sandbox is None
    assert adapter._is_created is False

    # Scenario A: CLI verification fails (uncertain cleanup) -> MUST NOT report verified_destroyed!
    with patch.object(adapter, "_cli_destroy_and_verify", AsyncMock(return_value=(False, "msb rm --force failed with exit code 1: permission denied"))):
        with pytest.raises(SandboxCleanupError) as exc_info:
            await adapter.destroy()
        assert "MicroVM destruction could not be verified" in str(exc_info.value)
        assert adapter._is_destroyed is False

    # Scenario B: CLI verification succeeds (proven absence via msb ls) -> Reports verified_destroyed
    with patch.object(adapter, "_cli_destroy_and_verify", AsyncMock(return_value=(True, "MicroVM confirmed absent in msb ls"))):
        status = await adapter.destroy()
        assert status == "verified_destroyed"
        assert adapter._is_destroyed is True


@pytest.mark.asyncio
async def test_subprocess_safe_timeout_termination_and_reaping():
    """
    Verifies that run_subprocess_safe:
    1. Binds execution by the specified timeout.
    2. Explicitly terminates the subprocess on timeout.
    3. Escalates to proc.kill() if graceful termination times out.
    4. Reaps the process before returning.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.sandbox.subprocess_utils import run_subprocess_safe

    # Case A: Times out, proc.terminate() terminates the process within grace period
    mock_proc_a = AsyncMock()
    mock_proc_a.terminate = MagicMock()
    mock_proc_a.kill = MagicMock()
    # First communicate times out; second communicate (after terminate) returns reaped output
    mock_proc_a.communicate.side_effect = [
        asyncio.TimeoutError("Timeout on command"),
        (b"output after terminate", b""),
    ]

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc_a):
        rc, out, err, err_msg = await run_subprocess_safe("test-cmd", ["arg1"], timeout=0.1, terminate_grace_period=0.5)

    assert rc is None
    assert "timed out after 0.1s and was terminated" in err_msg
    mock_proc_a.terminate.assert_called_once()
    mock_proc_a.kill.assert_not_called()
    assert mock_proc_a.communicate.call_count == 2

    # Case B: Times out, terminate does not exit in time -> escalates to proc.kill() and reaps
    mock_proc_b = AsyncMock()
    mock_proc_b.terminate = MagicMock()
    mock_proc_b.kill = MagicMock()
    mock_proc_b.communicate.side_effect = [
        asyncio.TimeoutError("Timeout on command"),
        asyncio.TimeoutError("Timeout on terminate grace"),
        (b"output after kill", b""),
    ]

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc_b):
        rc, out, err, err_msg = await run_subprocess_safe("test-cmd", ["arg1"], timeout=0.1, terminate_grace_period=0.1, kill_grace_period=0.5)

    assert rc is None
    assert "timed out after 0.1s and was killed" in err_msg
    mock_proc_b.terminate.assert_called_once()
    mock_proc_b.kill.assert_called_once()
    assert mock_proc_b.communicate.call_count == 3


@pytest.mark.asyncio
async def test_microsandbox_nonzero_rm_exit_with_sandbox_absent_verifies_destruction():
    """
    Verifies that when 'msb rm --force' returns non-zero (e.g. sandbox already removed),
    cleanup is NOT classified as failed if independent 'msb ls' proves absence.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.sandbox.base import SandboxConfig
    from app.services.sandbox.microsandbox_adapter import MicrosandboxAdapter

    config = SandboxConfig(
        sandbox_id="partproof-test-absent-002",
        image="python:3.12-slim",
        cpus=1,
        memory_mb=512,
        network="none",
        timeout_seconds=30,
        task_id="test-task-absent",
        execution_id="test-exec-absent",
    )
    adapter = MicrosandboxAdapter(config)
    adapter._provision_attempted = True

    # msb rm returns non-zero (code 1, sandbox not found)
    # msb ls returns code 0 with sandbox absent
    with patch("os.path.exists", return_value=True), \
         patch("app.services.sandbox.microsandbox_adapter.run_subprocess_safe", side_effect=[
             (1, b"", b"Error: sandbox 'partproof-test-absent-002' not found\n", None),
             (0, b"other-vm-123 running\n", b"", None),
         ]):
        status = await adapter.destroy()

    assert status == "verified_destroyed"
    assert adapter._is_destroyed is True


@pytest.mark.asyncio
async def test_microsandbox_nonzero_rm_exit_with_sandbox_present_fails_cleanup():
    """
    Verifies that when 'msb rm --force' returns non-zero AND 'msb ls' still detects
    the sandbox, cleanup raises SandboxCleanupError, preserving needs_reconciliation.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.sandbox.base import SandboxConfig, SandboxCleanupError
    from app.services.sandbox.microsandbox_adapter import MicrosandboxAdapter

    config = SandboxConfig(
        sandbox_id="partproof-test-present-003",
        image="python:3.12-slim",
        cpus=1,
        memory_mb=512,
        network="none",
        timeout_seconds=30,
        task_id="test-task-present",
        execution_id="test-exec-present",
    )
    adapter = MicrosandboxAdapter(config)
    adapter._provision_attempted = True

    # msb rm returns non-zero (code 1)
    # msb ls returns code 0, BUT sandbox is still present!
    with patch("os.path.exists", return_value=True), \
         patch("app.services.sandbox.microsandbox_adapter.run_subprocess_safe", side_effect=[
             (1, b"", b"Error: failed to force remove container\n", None),
             (0, b"partproof-test-present-003 running\n", b"", None),
         ]):
        with pytest.raises(SandboxCleanupError) as exc_info:
            await adapter.destroy()

    assert "still detected present in msb ls" in str(exc_info.value)
    assert adapter._is_destroyed is False


@pytest.mark.asyncio
async def test_microsandbox_preflight_sdk_failure_skips_cli_cleanup():
    """
    Verifies that if SDK or runtime directory preflight fails BEFORE Sandbox.create(),
    _provision_attempted remains False, and destroy() skips unnecessary CLI cleanup.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.sandbox.base import SandboxConfig, SandboxCreationError, UnsupportedSandboxBackendError
    from app.services.sandbox.microsandbox_adapter import MicrosandboxAdapter

    config = SandboxConfig(
        sandbox_id="partproof-test-preflight-004",
        image="python:3.12-slim",
        cpus=1,
        memory_mb=512,
        network="none",
        timeout_seconds=30,
        task_id="test-task-preflight",
        execution_id="test-exec-preflight",
    )
    adapter = MicrosandboxAdapter(config)

    # 1. Simulate preflight runtime dir failure
    with patch("app.services.sandbox.microsandbox_adapter._load_microsandbox_sdk", return_value=(MagicMock(), MagicMock())), \
         patch("os.path.exists", return_value=False):
        with pytest.raises(SandboxCreationError) as exc_info:
            await adapter.create()
        assert "runtime directory not found" in str(exc_info.value)

    # _provision_attempted must be False
    assert adapter._provision_attempted is False

    # Calling destroy() must succeed without calling _cli_destroy_and_verify
    with patch.object(adapter, "_cli_destroy_and_verify", AsyncMock()) as mock_cli:
        status = await adapter.destroy()
        mock_cli.assert_not_called()
        assert status == "verified_destroyed"


@pytest.mark.asyncio
async def test_successful_cleanup_within_configured_grace_period():
    """
    Verifies that execution steps complete and microVM cleanup finishes
    cleanly with 'verified_destroyed' within the configured SANDBOX_CLEANUP_TIMEOUT_SECONDS grace period.
    """
    manager = SandboxManager(backend_name="mock")

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Audit step finishing cleanly",
            code="print('Audit step passed successfully')\n",
        ),
    ]

    res = await manager.execute_steps(
        task_id="test-task-grace-period",
        execution_id="test-exec-grace-period",
        steps=steps,
        timeout_seconds=10.0,
    )

    assert res.status == "succeeded"
    assert res.cleanup_status == "verified_destroyed"
    assert len(res.step_outputs) == 1
    assert res.step_outputs[0].status == "succeeded"
