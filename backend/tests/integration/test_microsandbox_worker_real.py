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

    # Verify no running microVMs left behind via CLI: fail if msb ls fails or reports leak
    msb_list = subprocess.run(["msb", "ls"], capture_output=True, text=True)
    assert msb_list.returncode == 0, f"msb ls verification failed with exit code {msb_list.returncode}: {msb_list.stderr}"
    assert result.sandbox_id not in msb_list.stdout, (
        f"MicroVM '{result.sandbox_id}' still detected running in msb ls: {msb_list.stdout}"
    )


@pytest.mark.asyncio
async def test_real_microsandbox_execution_worker_with_postgres(tmp_path):
    """
    True end-to-end persistent worker integration test with real PostgreSQL and real Microsandbox:
    1. Seed approved plan in the dedicated PostgreSQL test database (partproof_test).
    2. Create a queued Execution.
    3. Start the actual ExecutionWorker in run-once mode.
    4. Verify PostgreSQL queue claiming and worker ownership.
    5. Verify sandbox identity is persisted before execution.
    6. Execute at least two steps inside the same real microVM.
    7. Verify workspace persistence across steps.
    8. Verify step records and artifacts in PostgreSQL.
    9. Verify sandbox destruction via CLI.
    10. Verify Task and Execution terminal states ('succeeded').
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.core.config import settings
    from app.models.entities import Approval, Artifact, Execution, ExecutionEvent, ExecutionStep, Task, User
    from app.services.orchestration.plan_integrity import compute_plan_hash
    from app.workers.execution_worker import ExecutionWorker
    from app.workers.host_lock import HostLock
    from tests.integration.test_postgres_concurrency import (
        TEST_POSTGRES_URL,
        postgres_test_context,
        validate_test_database_url,
    )

    if not TEST_POSTGRES_URL:
        pytest.skip("Requires TEST_POSTGRES_DATABASE_URL to be set for PostgreSQL worker integration test")

    validate_test_database_url(TEST_POSTGRES_URL)

    step1_code = """
import csv
data = [["part_id", "qty", "price"], ["HEX-01", 10, 2.50], ["HEX-02", 5, 8.00]]
with open("/workspace/parts.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(data)
print("WROTE_PARTS_CSV")
"""
    step2_code = """
import csv
import os
assert os.path.exists("/workspace/parts.csv"), "Missing parts.csv!"
total = 0.0
with open("/workspace/parts.csv", "r") as f:
    reader = csv.DictReader(f)
    for r in reader:
        total += int(r["qty"]) * float(r["price"])
os.makedirs("/workspace/output", exist_ok=True)
with open("/workspace/output/audit_receipt.csv", "w", newline="") as f:
    f.write(f"total_cost\\n{total}\\n")
print(f"CALCULATED_TOTAL:{total}")
"""

    plan_dict = {
        "title": "Real Worker End-to-End Test",
        "summary": "Validates persistent worker with live PostgreSQL and real microVM",
        "reasoning_summary": "Tests full multi-step persistent pipeline",
        "steps": [
            {"step_id": "step_1", "description": "Extract raw parts", "execution_type": "python", "code": step1_code},
            {"step_id": "step_2", "description": "Calculate audit total", "execution_type": "python", "code": step2_code},
        ],
        "required_capabilities": ["file_read", "file_write"],
        "network_required": False,
        "success_criteria": ["Receipt generated"],
        "expected_artifacts": ["audit_receipt.csv"],
    }
    plan_hash = compute_plan_hash(plan_dict)

    async with postgres_test_context() as SessionFactory:
        async with SessionFactory() as session:
            # 1. Seed user (idempotent lookup first) and task
            user_stmt = select(User).where(User.email == "real-worker-test@partproof.io")
            user = (await session.execute(user_stmt)).scalar_one_or_none()
            if not user:
                user = User(email="real-worker-test@partproof.io", password_hash="dummy")
                session.add(user)
                await session.flush()

            task = Task(user_id=user.id, title="Live Worker Pipeline Task", description="PostgreSQL E2E", status="queued")
            session.add(task)
            await session.flush()

            approval = Approval(
                task_id=task.id,
                approved_by=user.email,
                approved_plan_hash=plan_hash,
                decision="approved",
            )
            session.add(approval)
            await session.flush()

            execution = Execution(
                task_id=task.id,
                approval_id=approval.id,
                plan_hash=plan_hash,
                plan_snapshot=plan_dict,
                status="queued",
                runtime_image="python:3.12-slim",
                cpu_limit=1,
                memory_limit_mb=512,
                network_mode="none",
                timeout_seconds=60,
            )
            session.add(execution)
            await session.commit()
            exec_id = execution.id
            task_id = task.id

        # 2. Run ExecutionWorker
        art_manager = ArtifactManager(base_storage_dir=str(tmp_path / "artifacts"))
        sb_manager = SandboxManager(backend_name="microsandbox", artifact_manager=art_manager)
        worker = ExecutionWorker(
            session_factory=SessionFactory,
            sandbox_manager=sb_manager,
            artifact_manager=art_manager,
            worker_id="real-worker-integration-01",
        )
        lock_path = str(tmp_path / "partproof_worker_test.lock")
        worker.host_lock = HostLock(lock_path)

        await worker.run(run_once=True)

        # 3. Assertions against PostgreSQL
        async with SessionFactory() as session:
            db_exec = await session.get(Execution, exec_id)
            db_task = await session.get(Task, task_id)

            assert db_task is not None
            assert db_exec is not None

            # Terminal states must be canonical 'succeeded'
            assert db_task.status == "succeeded"
            assert db_exec.status == "succeeded"
            assert db_exec.cleanup_status == "verified_destroyed"
            assert db_exec.exit_code == 0
            assert db_exec.duration_seconds is not None and db_exec.duration_seconds > 0

            # Sandbox identity was persisted in PostgreSQL
            assert db_exec.sandbox_id is not None
            assert db_exec.sandbox_id.startswith("partproof-")

            # Worker ownership was recorded
            assert db_exec.worker_id == "real-worker-integration-01"
            assert db_exec.lease_expires_at is None

            # Step records
            steps_stmt = select(ExecutionStep).where(ExecutionStep.execution_id == exec_id).order_by(ExecutionStep.step_number)
            steps = (await session.execute(steps_stmt)).scalars().all()
            assert len(steps) == 2
            assert steps[0].status == "succeeded"
            assert steps[0].exit_code == 0
            assert "WROTE_PARTS_CSV" in (steps[0].stdout or "")
            assert steps[1].status == "succeeded"
            assert steps[1].exit_code == 0
            assert "CALCULATED_TOTAL:65.0" in (steps[1].stdout or "")

            # Artifact persisted
            art_stmt = select(Artifact).where(Artifact.execution_id == exec_id)
            arts = (await session.execute(art_stmt)).scalars().all()
            assert len(arts) == 1
            assert arts[0].filename == "audit_receipt.csv"
            assert os.path.exists(arts[0].storage_key)

            # Verification of microVM absence via msb ls: must fail if msb ls fails or reports leak
            msb_list = subprocess.run(["msb", "ls"], capture_output=True, text=True)
            assert msb_list.returncode == 0, f"msb ls verification failed with exit code {msb_list.returncode}: {msb_list.stderr}"
            assert db_exec.sandbox_id not in msb_list.stdout, (
                f"MicroVM '{db_exec.sandbox_id}' still detected running after worker finalization: {msb_list.stdout}"
            )


@pytest.mark.asyncio
async def test_real_microsandbox_stale_recovery_with_postgres(tmp_path):
    """
    Tests stale execution recovery with PostgreSQL:
    - Verifies an execution whose lease expired with verified cleanup is safely requeued.
    - Genuinely simulates unverified cleanup for an execution and verifies transition to needs_reconciliation.
    """
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch
    from sqlalchemy import select
    from app.models.entities import Execution, Task, User
    from app.workers.recovery import StaleExecutionReconciler
    from tests.integration.test_postgres_concurrency import (
        TEST_POSTGRES_URL,
        postgres_test_context,
        validate_test_database_url,
    )

    if not TEST_POSTGRES_URL:
        pytest.skip("Requires TEST_POSTGRES_DATABASE_URL to be set for PostgreSQL worker integration test")

    validate_test_database_url(TEST_POSTGRES_URL)

    async with postgres_test_context() as SessionFactory:
        reconciler = StaleExecutionReconciler(SessionFactory)

        async with SessionFactory() as session:
            user_stmt = select(User).where(User.email == "stale-test@partproof.io")
            user = (await session.execute(user_stmt)).scalar_one_or_none()
            if not user:
                user = User(email="stale-test@partproof.io", password_hash="dummy")
                session.add(user)
                await session.flush()

            # Case 1: Stale execution with confirmed absent sandbox (sandbox already stopped)
            task1 = Task(user_id=user.id, title="Stale Task 1", description="Requeue test", status="running")
            session.add(task1)
            await session.flush()

            exec1 = Execution(
                task_id=task1.id,
                status="running",
                worker_id="dead-worker-01",
                sandbox_id="already-absent-sandbox-id-9999",
                lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=60),
                attempt_count=1,
            )
            session.add(exec1)

            # Case 2: Stale execution where microVM cleanup cannot be confirmed
            task2 = Task(user_id=user.id, title="Stale Task 2", description="Leak test", status="running")
            session.add(task2)
            await session.flush()

            exec2 = Execution(
                task_id=task2.id,
                status="running",
                worker_id="dead-worker-02",
                sandbox_id="unverified-leak-sandbox-id-8888",
                lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=60),
                attempt_count=1,
            )
            session.add(exec2)
            await session.commit()
            e1_id, e2_id = exec1.id, exec2.id
            t1_id, t2_id = task1.id, task2.id

        # Reconcile with genuine failure simulation for unverified microVM
        original_verify = reconciler._verify_and_cleanup_sandbox

        async def _mock_verify(sandbox_id):
            if sandbox_id == "unverified-leak-sandbox-id-8888":
                return False, "Simulated msb ls leak: microVM remains active or CLI unresponsive"
            return await original_verify(sandbox_id)

        with patch.object(reconciler, "_verify_and_cleanup_sandbox", side_effect=_mock_verify):
            reconciled = await reconciler.reconcile_stale_executions(max_attempts=3)
            assert reconciled == 2

        async with SessionFactory() as session:
            res_e1 = await session.get(Execution, e1_id)
            res_t1 = await session.get(Task, t1_id)
            res_e2 = await session.get(Execution, e2_id)
            res_t2 = await session.get(Task, t2_id)

            assert res_e1 is not None and res_t1 is not None
            assert res_e2 is not None and res_t2 is not None

            # Case 1: Confirmed absent -> requeued safely
            assert res_e1.status == "queued"
            assert res_t1.status == "queued"
            assert res_e1.cleanup_status == "verified_destroyed"
            assert res_e1.worker_id is None

            # Case 2: Unverified cleanup -> transitioned to needs_reconciliation (NEVER requeued)
            assert res_e2.status == "needs_reconciliation"
            assert res_t2.status == "needs_reconciliation"
            assert res_e2.cleanup_status == "leak_detected"
            assert res_e2.worker_id is not None
            assert res_e2.worker_id.startswith("reconciler-")
            assert res_e2.lease_expires_at is None
            assert res_e2.sandbox_id == "unverified-leak-sandbox-id-8888"
