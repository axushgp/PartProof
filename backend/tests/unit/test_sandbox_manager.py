import pytest
from app.core.config import settings
from app.services.artifacts.manager import ArtifactManager
from app.services.sandbox.base import (
    PolicyViolationError,
    UnsupportedSandboxBackendError,
)
from app.services.sandbox.manager import SandboxManager


@pytest.fixture
def sandbox_manager(tmp_path):
    art_mgr = ArtifactManager(base_storage_dir=str(tmp_path / "artifacts"))
    return SandboxManager(backend_name="mock", artifact_manager=art_mgr)


@pytest.mark.asyncio
async def test_manager_successful_execution(sandbox_manager):
    result = await sandbox_manager.execute_task(
        task_id="task-test-01",
        execution_id="exec-test-01",
        code="print('Auditing supplier quote...')",
        expected_artifacts=["report.csv", "summary.json"],
    )

    assert result.status == "succeeded"
    assert result.execution_mode == "mock"
    assert result.cleanup_status == "verified_destroyed"
    assert result.output.exit_code == 0
    assert len(result.artifacts) == 2
    assert result.artifacts[0].filename == "report.csv"
    assert result.artifacts[1].filename == "summary.json"


@pytest.mark.asyncio
async def test_manager_timeout_handling(sandbox_manager):
    result = await sandbox_manager.execute_task(
        task_id="task-test-02",
        execution_id="exec-test-02",
        code="# SIMULATE_TIMEOUT\nwhile True: pass",
        timeout_seconds=2.0,
    )

    assert result.status == "timed_out"
    assert result.output.timed_out is True
    assert result.output.exit_code == 124
    assert result.cleanup_status == "verified_destroyed"


@pytest.mark.asyncio
async def test_manager_policy_violation_disallowed_image(sandbox_manager):
    with pytest.raises(PolicyViolationError, match="not in allowlisted images"):
        await sandbox_manager.execute_task(
            task_id="task-test-03",
            execution_id="exec-test-03",
            code="print('test')",
            image="untrusted/malicious:latest",
        )


@pytest.mark.asyncio
async def test_manager_policy_violation_excessive_cpu(sandbox_manager, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_MAX_CPUS", 1)
    with pytest.raises((PolicyViolationError, Exception)):
        await sandbox_manager.execute_task(
            task_id="task-test-04",
            execution_id="exec-test-04",
            code="print('test')",
            cpus=2,
        )


@pytest.mark.asyncio
async def test_manager_policy_violation_excessive_memory(sandbox_manager, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_MAX_MEMORY_MB", 256)
    with pytest.raises((PolicyViolationError, Exception)):
        await sandbox_manager.execute_task(
            task_id="task-test-05",
            execution_id="exec-test-05",
            code="print('test')",
            memory_mb=512,
        )


@pytest.mark.asyncio
async def test_manager_prohibits_mock_in_production(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PARTPROOF_ENV", "production")
    manager = SandboxManager(backend_name="mock", artifact_manager=ArtifactManager(str(tmp_path)))
    
    with pytest.raises(PolicyViolationError, match="Mock sandbox backend is prohibited in production"):
        await manager.execute_task(
            task_id="task-test-06",
            execution_id="exec-test-06",
            code="print('production task')",
        )


@pytest.mark.asyncio
async def test_manager_unsupported_backend(tmp_path):
    manager = SandboxManager(backend_name="unknown_engine", artifact_manager=ArtifactManager(str(tmp_path)))
    
    with pytest.raises(UnsupportedSandboxBackendError, match="Unsupported sandbox backend"):
        await manager.execute_task(
            task_id="task-test-07",
            execution_id="exec-test-07",
            code="print('test')",
        )
