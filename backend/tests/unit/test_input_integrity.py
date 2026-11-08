import hashlib
import os
import tempfile
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import Approval, Execution, Task, User
from app.schemas.plan import TaskInputFileManifest, TaskInputProvenance, TaskPlanSchema
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.sandbox.base import SandboxConfig
from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.mock_adapter import MockSandboxAdapter
from app.workers.execution_worker import ExecutionWorker
from app.workers.host_lock import HostLock
from app.workers.validator import SecurityExecutionValidator, SecurityValidationError


@pytest.fixture
def clean_plan_dict():
    raw_csv = b"col1,col2\n10,20\n30,40\n"
    digest = hashlib.sha256(raw_csv).hexdigest()
    return {
        "title": "Input Integrity Plan",
        "summary": "Validates input staging integrity",
        "reasoning_summary": "Systematic audit",
        "steps": [
            {
                "step_id": "step_1",
                "description": "Read /workspace/input/input_data.csv",
                "execution_type": "python",
                "code": "import os\nwith open('/workspace/input/input_data.csv') as f:\n    print(f.read())\n",
            }
        ],
        "required_capabilities": ["file_read"],
        "network_required": False,
        "success_criteria": ["Input read verified"],
        "expected_artifacts": [],
        "input_provenance": {
            "mode": "user_upload",
            "files": [
                {
                    "filename": "input_data.csv",
                    "size_bytes": len(raw_csv),
                    "sha256": digest,
                    "detected_format": "csv",
                    "validation_status": "valid",
                }
            ],
        },
    }


def test_validator_rejects_missing_input_file(tmp_path, clean_plan_dict):
    validator = SecurityExecutionValidator()
    plan_hash = compute_plan_hash(clean_plan_dict)

    # Point storage dir to tmp_path
    original_storage = settings.ARTIFACT_STORAGE_DIR
    settings.ARTIFACT_STORAGE_DIR = str(tmp_path)
    try:
        task_id = "test-task-missing-input"
        execution = Execution(
            id="exec-1",
            task_id=task_id,
            status="queued",
            plan_hash=plan_hash,
            plan_snapshot=clean_plan_dict,
            runtime_image="python:3.12-slim",
            cpu_limit=1,
            memory_limit_mb=512,
            network_mode="none",
            timeout_seconds=30,
        )
        approval = Approval(
            id="appr-1",
            task_id=task_id,
            approved_by="auditor@partproof.io",
            approved_plan_hash=plan_hash,
            decision="approved",
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            validator.validate(execution, approval)

        assert any("is missing from staging" in v for v in exc_info.value.violations)
    finally:
        settings.ARTIFACT_STORAGE_DIR = original_storage


def test_validator_rejects_tampered_input_file(tmp_path, clean_plan_dict):
    validator = SecurityExecutionValidator()
    plan_hash = compute_plan_hash(clean_plan_dict)

    original_storage = settings.ARTIFACT_STORAGE_DIR
    settings.ARTIFACT_STORAGE_DIR = str(tmp_path)
    try:
        task_id = "test-task-tampered-input"
        # Create staging dir with tampered content
        input_dir = os.path.join(str(tmp_path), "tasks", task_id, "inputs")
        os.makedirs(input_dir, exist_ok=True)
        with open(os.path.join(input_dir, "input_data.csv"), "wb") as f:
            f.write(b"MALICIOUS_TAMPERED_CONTENT_AFTER_APPROVAL\n")

        execution = Execution(
            id="exec-2",
            task_id=task_id,
            status="queued",
            plan_hash=plan_hash,
            plan_snapshot=clean_plan_dict,
            runtime_image="python:3.12-slim",
            cpu_limit=1,
            memory_limit_mb=512,
            network_mode="none",
            timeout_seconds=30,
        )
        approval = Approval(
            id="appr-2",
            task_id=task_id,
            approved_by="auditor@partproof.io",
            approved_plan_hash=plan_hash,
            decision="approved",
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            validator.validate(execution, approval)

        assert any("was modified after approval" in v for v in exc_info.value.violations)
    finally:
        settings.ARTIFACT_STORAGE_DIR = original_storage


def test_validator_accepts_valid_input_file(tmp_path, clean_plan_dict):
    validator = SecurityExecutionValidator()
    plan_hash = compute_plan_hash(clean_plan_dict)

    original_storage = settings.ARTIFACT_STORAGE_DIR
    settings.ARTIFACT_STORAGE_DIR = str(tmp_path)
    try:
        task_id = "test-task-valid-input"
        input_dir = os.path.join(str(tmp_path), "tasks", task_id, "inputs")
        os.makedirs(input_dir, exist_ok=True)
        with open(os.path.join(input_dir, "input_data.csv"), "wb") as f:
            f.write(b"col1,col2\n10,20\n30,40\n")

        execution = Execution(
            id="exec-3",
            task_id=task_id,
            status="queued",
            plan_hash=plan_hash,
            plan_snapshot=clean_plan_dict,
            runtime_image="python:3.12-slim",
            cpu_limit=1,
            memory_limit_mb=512,
            network_mode="none",
            timeout_seconds=30,
        )
        approval = Approval(
            id="appr-3",
            task_id=task_id,
            approved_by="auditor@partproof.io",
            approved_plan_hash=plan_hash,
            decision="approved",
        )

        plan_schema = validator.validate(execution, approval)
        assert plan_schema.title == "Input Integrity Plan"
    finally:
        settings.ARTIFACT_STORAGE_DIR = original_storage


@pytest.mark.asyncio
async def test_input_staging_in_mock_adapter(tmp_path):
    input_dir = os.path.join(str(tmp_path), "inputs")
    os.makedirs(input_dir, exist_ok=True)
    with open(os.path.join(input_dir, "pump_specs.csv"), "wb") as f:
        f.write(b"pump_id,flow_rate,max_head\nP-100,450,85\n")

    config = SandboxConfig(
        sandbox_id="sb-test-staging",
        task_id="task-pump-1",
        execution_id="exec-pump-1",
    )
    adapter = MockSandboxAdapter(config)
    await adapter.create()
    await adapter.stage_input_files(input_dir)

    assert "pump_specs.csv" in adapter.staged_input_files
