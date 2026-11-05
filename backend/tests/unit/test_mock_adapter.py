import pytest
from app.services.artifacts.manager import ArtifactManager
from app.services.sandbox.base import (
    ExecutionRequest,
    PolicyViolationError,
    SandboxCleanupError,
    SandboxConfig,
    SandboxTimeoutError,
)
from app.services.sandbox.mock_adapter import MockSandboxAdapter


@pytest.fixture
def mock_config():
    return SandboxConfig(
        sandbox_id="mock-sb-01",
        task_id="task-01",
        execution_id="exec-01",
        image="python:3.12-slim",
        cpus=1,
        memory_mb=512,
        network="none",
        timeout_seconds=5.0,
    )


@pytest.fixture
def temp_artifact_manager(tmp_path):
    return ArtifactManager(base_storage_dir=str(tmp_path / "artifacts"))


@pytest.mark.asyncio
async def test_mock_adapter_successful_execution(mock_config, temp_artifact_manager):
    adapter = MockSandboxAdapter(mock_config, temp_artifact_manager)
    
    async with adapter:
        request = ExecutionRequest(
            code="print('Calculate BOM variance')",
            filename="audit_task.py",
            expected_artifacts=["report.csv"],
        )
        output = await adapter.execute(request)
        
        assert output.exit_code == 0
        assert "deterministic simulated environment" in output.stdout
        assert output.guest_kernel == "simulated-kernel-6.12.113-mock"
        assert output.duration_seconds >= 0.0
        assert output.timed_out is False

        # Collect artifacts
        artifacts = await adapter.collect_artifacts(
            request.expected_artifacts,
            str(temp_artifact_manager.get_execution_storage_dir(mock_config.task_id, mock_config.execution_id)),
        )
        assert len(artifacts) == 1
        assert artifacts[0].filename == "report.csv"
        assert artifacts[0].size_bytes > 0
        assert len(artifacts[0].sha256) == 64

    # Verify adapter state post-exit
    assert adapter._is_destroyed is True


@pytest.mark.asyncio
async def test_mock_adapter_failed_execution(mock_config, temp_artifact_manager):
    adapter = MockSandboxAdapter(mock_config, temp_artifact_manager)
    
    async with adapter:
        request = ExecutionRequest(
            code="def invalid syntax here\n# SIMULATE_ERROR",
            filename="broken_task.py",
        )
        output = await adapter.execute(request)
        
        assert output.exit_code == 1
        assert "Simulated error trigger detected" in output.stderr
        assert output.timed_out is False


@pytest.mark.asyncio
async def test_mock_adapter_simulated_timeout(mock_config, temp_artifact_manager):
    adapter = MockSandboxAdapter(mock_config, temp_artifact_manager)
    
    async with adapter:
        request = ExecutionRequest(
            code="# SIMULATE_TIMEOUT\nwhile True: pass",
            filename="infinite_loop.py",
        )
        with pytest.raises(SandboxTimeoutError, match="deadline .* exceeded"):
            await adapter.execute(request)


@pytest.mark.asyncio
async def test_mock_adapter_invalid_source_rejected(mock_config, temp_artifact_manager):
    adapter = MockSandboxAdapter(mock_config, temp_artifact_manager)
    
    async with adapter:
        # Empty code
        with pytest.raises(PolicyViolationError, match="cannot be empty"):
            await adapter.execute(ExecutionRequest(code="   "))

        # Null byte in code
        with pytest.raises(PolicyViolationError, match="null bytes"):
            await adapter.execute(ExecutionRequest(code="import os\x00malicious"))


@pytest.mark.asyncio
async def test_mock_adapter_cleanup_failure_simulation(mock_config, temp_artifact_manager):
    adapter = MockSandboxAdapter(mock_config, temp_artifact_manager)
    await adapter.create()
    
    # Trigger simulated cleanup failure marker
    await adapter.execute(ExecutionRequest(code="# SIMULATE_CLEANUP_FAILURE"))
    with pytest.raises(SandboxCleanupError, match="Simulated failure during sandbox cleanup"):
        await adapter.destroy()
