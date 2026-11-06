import os
import subprocess
import sys
import pytest
from app.services.artifacts.manager import ArtifactManager
from app.services.sandbox.base import (
    MultiStepExecutionResult,
    StepExecutionOutput,
    StepExecutionRequest,
)
from app.services.sandbox.manager import SandboxManager

# Opt-in integration test on Vultr VM with KVM
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MICROSANDBOX_WORKER_INTEGRATION") != "1" or sys.platform != "linux",
    reason="Requires Linux host with KVM and RUN_MICROSANDBOX_WORKER_INTEGRATION=1 (run on Vultr VM)",
)


@pytest.mark.asyncio
async def test_real_microsandbox_multi_step_worker_pipeline(tmp_path):
    """
    Validates isolated multi-step execution in a single real MicroVM on Vultr:
    1. Step 1 writes intermediate data to /workspace/raw_parts.csv.
    2. Step 2 reads /workspace/raw_parts.csv and outputs /workspace/output/final_audit.csv.
    3. Confirms /workspace state is preserved between steps.
    4. Validates artifact extraction from guest to host storage with SHA-256 checksums.
    5. Verifies complete microVM destruction.
    """
    task_id = "vultr-worker-task"
    execution_id = "vultr-worker-exec-001"

    art_manager = ArtifactManager(base_storage_dir=str(tmp_path / "artifacts"))
    manager = SandboxManager(backend_name="microsandbox", artifact_manager=art_manager)

    step1_code = """
import csv

data = [
    ["part_id", "qty", "unit_price"],
    ["P-101", 10, 5.50],
    ["P-102", 20, 12.00],
    ["P-103", 5, 45.00]
]

with open("/workspace/raw_parts.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(data)

print("Step 1 successfully wrote /workspace/raw_parts.csv")
"""

    step2_code = """
import csv
import os

if not os.path.exists("/workspace/raw_parts.csv"):
    raise FileNotFoundError("Intermediate file /workspace/raw_parts.csv missing!")

total_cost = 0.0
items = []
with open("/workspace/raw_parts.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        line_cost = int(row["qty"]) * float(row["unit_price"])
        total_cost += line_cost
        items.append([row["part_id"], row["qty"], row["unit_price"], str(line_cost)])

os.makedirs("/workspace/output", exist_ok=True)
with open("/workspace/output/final_audit.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["part_id", "qty", "unit_price", "line_cost"])
    writer.writerows(items)
    writer.writerow(["TOTAL", "", "", str(total_cost)])

print(f"Step 2 processed {len(items)} items. Total cost: {total_cost}")
"""

    steps = [
        StepExecutionRequest(
            step_number=1,
            description="Extract purchase orders to intermediate workspace file",
            code=step1_code,
            timeout_seconds=30.0,
        ),
        StepExecutionRequest(
            step_number=2,
            description="Process intermediate file and output final audit CSV",
            code=step2_code,
            timeout_seconds=30.0,
        ),
    ]

    completed_steps = []
    async def _on_step_complete(step_num: int, output: StepExecutionOutput):
        completed_steps.append((step_num, output.status, output.exit_code))

    result: MultiStepExecutionResult = await manager.execute_steps(
        task_id=task_id,
        execution_id=execution_id,
        steps=steps,
        expected_artifacts=["final_audit.csv"],
        image="python:3.12-slim",
        timeout_seconds=60.0,
        on_step_complete=_on_step_complete,
    )

    # Assertions
    assert result.status == "succeeded", f"Multi-step execution failed: {result.error_message}"
    assert result.cleanup_status == "verified_destroyed"
    assert result.exit_code == 0
    assert len(result.step_outputs) == 2
    assert result.step_outputs[0].status == "succeeded"
    assert result.step_outputs[0].exit_code == 0
    assert result.step_outputs[1].status == "succeeded"
    assert result.step_outputs[1].exit_code == 0

    assert len(completed_steps) == 2

    # Artifact assertions
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.filename == "final_audit.csv"
    assert os.path.exists(artifact.storage_path)
    assert artifact.size_bytes > 0
    assert len(artifact.sha256) == 64

    with open(artifact.storage_path, "r") as f:
        content = f.read()
    assert "P-101" in content
    assert "TOTAL" in content
    assert "520.0" in content  # 10*5.50 + 20*12.00 + 5*45.00 = 55 + 240 + 225 = 520.0

    # Verify no running microVMs left behind via CLI
    msb_list = subprocess.run(["msb", "ls"], capture_output=True, text=True)
    if msb_list.returncode == 0:
        assert result.sandbox_id not in msb_list.stdout
