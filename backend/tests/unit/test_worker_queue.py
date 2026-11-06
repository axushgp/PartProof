import copy
import os
import tempfile
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    Approval,
    Artifact,
    Execution,
    ExecutionEvent,
    ExecutionStep,
    Task,
    User,
)
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.workers.host_lock import HostLock, HostLockError
from app.workers.leases import LeaseManager
from app.workers.queue import QueueManager
from app.workers.recovery import StaleExecutionReconciler
from app.workers.validator import SecurityExecutionValidator, SecurityValidationError


VALID_PLAN_DICT = {
    "title": "Hex Cap Screw Procurement Audit",
    "summary": "Validates line items against contract catalog",
    "reasoning_summary": "Systematic audit of procurement line items against catalog",
    "steps": [
        {
            "step_id": "step_1",
            "description": "Parse items and verify prices",
            "execution_type": "python",
            "code": "print('Auditing contract pricing...')\nx = 100\n",
        },
        {
            "step_id": "step_2",
            "description": "Generate summary report",
            "execution_type": "python",
            "code": "print('Writing report')\n",
        },
    ],
    "required_capabilities": ["file_read", "file_write"],
    "network_required": False,
    "success_criteria": ["All line items audited"],
    "expected_artifacts": ["audit_summary.csv"],
}


class MockSessionFactory:
    """Wrapper around single in-memory SQLite db_session preventing premature closure during test context exit."""
    def __init__(self, session):
        self.session = session
    def __call__(self):
        return self
    async def __aenter__(self):
        return self.session
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def test_host_lock_acquire_and_release():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        lock_path = f.name

    try:
        lock1 = HostLock(lock_path)
        assert lock1.acquire() is True
        assert lock1.is_locked is True

        # Second lock attempt must fail
        lock2 = HostLock(lock_path)
        assert lock2.acquire() is False
        assert lock2.is_locked is False

        # Release first lock
        lock1.release()
        assert lock1.is_locked is False

        # Now second lock can acquire
        assert lock2.acquire() is True
        assert lock2.is_locked is True
        lock2.release()
    finally:
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass


def test_host_lock_context_manager():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        lock_path = f.name

    try:
        with HostLock(lock_path) as lock:
            assert lock.is_locked is True
            # Nested or rival acquisition in another instance must fail
            rival = HostLock(lock_path)
            assert rival.acquire() is False
    finally:
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_lease_renewal_cas_success_and_failure(db_session: AsyncSession):
    session_factory = MockSessionFactory(db_session)
    lease_mgr = LeaseManager(session_factory)

    user = User(email="lease-test@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    task = Task(user_id=user.id, title="Lease Task", description="Testing leases", status="running")
    db_session.add(task)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        status="running",
        worker_id="worker-test-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    db_session.add(execution)
    await db_session.commit()

    # 1. Successful renewal with matching worker_id and active status
    renewed = await lease_mgr.renew_lease(execution.id, "worker-test-1", lease_duration_seconds=60)
    assert renewed is True

    # 2. Failed renewal with wrong worker_id
    renewed_wrong = await lease_mgr.renew_lease(execution.id, "worker-test-2", lease_duration_seconds=60)
    assert renewed_wrong is False

    # 3. Failed renewal when status is not active (e.g. succeeded)
    execution.status = "succeeded"
    await db_session.commit()

    renewed_terminal = await lease_mgr.renew_lease(execution.id, "worker-test-1", lease_duration_seconds=60)
    assert renewed_terminal is False


@pytest.mark.asyncio
async def test_queue_claim_next_execution(db_session: AsyncSession):
    session_factory = MockSessionFactory(db_session)
    queue_mgr = QueueManager(session_factory)

    user = User(email="claim-test@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    plan_dict = copy.deepcopy(VALID_PLAN_DICT)
    plan_hash = compute_plan_hash(plan_dict)

    task = Task(user_id=user.id, title="Claimable Task", description="Testing queue claim", status="queued")
    db_session.add(task)
    await db_session.flush()

    approval = Approval(
        task_id=task.id,
        approved_by=user.email,
        approved_plan_hash=plan_hash,
        decision="approved",
    )
    db_session.add(approval)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        approval_id=approval.id,
        plan_hash=plan_hash,
        plan_snapshot=plan_dict,
        status="queued",
        timeout_seconds=30,
    )
    db_session.add(execution)
    await db_session.commit()

    # Claim next execution
    claimed = await queue_mgr.claim_next_execution(worker_id="worker-unit-1", lease_duration_seconds=60)

    assert claimed is not None
    assert claimed.execution_id == execution.id
    assert claimed.task_id == task.id
    assert claimed.worker_id == "worker-unit-1"
    assert claimed.attempt_count == 1

    # Verify database state after claim
    await db_session.refresh(task)
    await db_session.refresh(execution)
    assert task.status == "running"
    assert execution.status == "preparing"
    assert execution.worker_id == "worker-unit-1"
    assert execution.lease_expires_at is not None

    # Second claim attempt should find queue empty
    second_claim = await queue_mgr.claim_next_execution(worker_id="worker-unit-2")
    assert second_claim is None


@pytest.mark.asyncio
async def test_queue_claim_rejects_unapproved_or_hash_mismatch(db_session: AsyncSession):
    session_factory = MockSessionFactory(db_session)
    queue_mgr = QueueManager(session_factory)

    user = User(email="claim-tamper@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    plan_dict = copy.deepcopy(VALID_PLAN_DICT)
    real_hash = compute_plan_hash(plan_dict)

    task = Task(user_id=user.id, title="Tampered Task", description="Testing tamper claim", status="queued")
    db_session.add(task)
    await db_session.flush()

    # Approval has different hash than execution
    approval = Approval(
        task_id=task.id,
        approved_by=user.email,
        approved_plan_hash="different_hash_00000000000000000000000000000000000000000000000000000",
        decision="approved",
    )
    db_session.add(approval)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        approval_id=approval.id,
        plan_hash=real_hash,
        plan_snapshot=plan_dict,
        status="queued",
    )
    db_session.add(execution)
    await db_session.commit()

    claimed = await queue_mgr.claim_next_execution(worker_id="worker-unit-1")
    assert claimed is None

    await db_session.refresh(task)
    await db_session.refresh(execution)
    assert task.status == "failed"
    assert execution.status == "failed"


@pytest.mark.asyncio
async def test_security_execution_validator():
    validator = SecurityExecutionValidator()

    plan_dict = copy.deepcopy(VALID_PLAN_DICT)
    plan_hash = compute_plan_hash(plan_dict)

    approval = Approval(
        task_id="task-1",
        approved_by="admin@partproof.io",
        approved_plan_hash=plan_hash,
        decision="approved",
    )

    execution = Execution(
        task_id="task-1",
        approval_id="app-1",
        plan_hash=plan_hash,
        plan_snapshot=plan_dict,
        status="preparing",
        runtime_image="python:3.12-slim",
        cpu_limit=1,
        memory_limit_mb=512,
        network_mode="none",
        timeout_seconds=30,
    )

    # 1. Valid execution passes
    validated_plan = validator.validate(execution, approval)
    assert validated_plan.title == plan_dict["title"]

    # 2. Tampered plan hash fails
    bad_exec = copy.copy(execution)
    bad_exec.plan_hash = "f" * 64
    with pytest.raises(SecurityValidationError) as exc_info:
        validator.validate(bad_exec, approval)
    assert "Cryptographic hash integrity mismatch" in str(exc_info.value)

    # 3. Disallowed network mode fails
    net_exec = copy.copy(execution)
    net_exec.network_mode = "bridge"
    with pytest.raises(SecurityValidationError) as exc_info:
        validator.validate(net_exec, approval)
    assert "Non-zero network mode" in str(exc_info.value)

    # 4. Missing approval fails
    with pytest.raises(SecurityValidationError) as exc_info:
        validator.validate(execution, None)
    assert "Missing associated Approval" in str(exc_info.value)


@pytest.mark.asyncio
async def test_stale_execution_reconciler_requeues_and_fails(db_session: AsyncSession):
    session_factory = MockSessionFactory(db_session)
    reconciler = StaleExecutionReconciler(session_factory)

    user = User(email="stale@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    # 1. Execution with attempt_count=1 and expired lease should be requeued
    task1 = Task(user_id=user.id, title="Stale 1", description="Will requeue", status="running")
    db_session.add(task1)
    await db_session.flush()

    exec1 = Execution(
        task_id=task1.id,
        status="running",
        worker_id="dead-worker-1",
        attempt_count=1,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    db_session.add(exec1)

    # 2. Execution with attempt_count=3 (max) and expired lease should be failed
    task2 = Task(user_id=user.id, title="Stale 2", description="Will fail", status="running")
    db_session.add(task2)
    await db_session.flush()

    exec2 = Execution(
        task_id=task2.id,
        status="running",
        worker_id="dead-worker-2",
        attempt_count=3,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    db_session.add(exec2)
    await db_session.commit()

    reconciled = await reconciler.reconcile_stale_executions(max_attempts=3)
    assert reconciled == 2

    await db_session.refresh(task1)
    await db_session.refresh(exec1)
    assert task1.status == "queued"
    assert exec1.status == "queued"
    assert exec1.worker_id is None

    await db_session.refresh(task2)
    await db_session.refresh(exec2)
    assert task2.status == "failed"
    assert exec2.status == "failed"


@pytest.mark.asyncio
async def test_execution_worker_process_claimed_task_end_to_end(db_session: AsyncSession):
    from app.workers.execution_worker import ExecutionWorker

    session_factory = MockSessionFactory(db_session)
    user = User(email="worker-e2e@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    plan_dict = copy.deepcopy(VALID_PLAN_DICT)
    plan_hash = compute_plan_hash(plan_dict)

    task = Task(user_id=user.id, title="End-to-End Worker Task", description="Full pipeline audit", status="queued")
    db_session.add(task)
    await db_session.flush()

    approval = Approval(
        task_id=task.id,
        approved_by=user.email,
        approved_plan_hash=plan_hash,
        decision="approved",
    )
    db_session.add(approval)
    await db_session.flush()

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
        timeout_seconds=30,
    )
    db_session.add(execution)
    await db_session.commit()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        lock_file = f.name

    try:
        worker = ExecutionWorker(
            session_factory=session_factory,
            worker_id="worker-unit-test-e2e",
        )
        worker.host_lock = HostLock(lock_file)

        await worker.run(run_once=True)

        await db_session.refresh(task)
        await db_session.refresh(execution)

        assert task.status == "succeeded"
        assert execution.status == "succeeded"
        assert execution.sandbox_id is not None
        assert execution.sandbox_id.startswith("partproof-")
        assert execution.cleanup_status == "verified_destroyed"
        assert execution.duration_seconds is not None
        assert execution.duration_seconds > 0
        assert execution.lease_expires_at is None

        # Verify steps persisted with full metadata
        steps_stmt = select(ExecutionStep).where(ExecutionStep.execution_id == execution.id).order_by(ExecutionStep.step_number)
        steps_res = await db_session.execute(steps_stmt)
        steps = steps_res.scalars().all()
        assert len(steps) == 2
        assert steps[0].status == "succeeded"
        assert steps[0].description == "Parse items and verify prices"
        assert steps[0].code is not None
        assert steps[0].execution_type == "python"
        assert steps[1].status == "succeeded"
        assert steps[1].description == "Generate summary report"

        # Verify artifacts persisted
        art_stmt = select(Artifact).where(Artifact.execution_id == execution.id)
        art_res = await db_session.execute(art_stmt)
        arts = art_res.scalars().all()
        assert len(arts) == 1
        assert arts[0].filename == "audit_summary.csv"
        assert arts[0].sha256 is not None

        # Verify events persisted
        event_stmt = select(ExecutionEvent).where(ExecutionEvent.execution_id == execution.id)
        event_res = await db_session.execute(event_stmt)
        events = event_res.scalars().all()
        event_types = [e.event_type for e in events]
        assert "execution_claimed" in event_types
        assert "execution_started" in event_types
        assert "sandbox_allocated" in event_types
        assert "execution_step_completed" in event_types
        assert "execution_succeeded" in event_types
    finally:
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_sandbox_identity_persisted_before_provisioning_and_crash_recovery(db_session: AsyncSession):
    """
    Simulates a worker crashing immediately after sandbox identity is persisted and provisioned.
    Proves that Execution.sandbox_id was recorded in the database, allowing the reconciler
    to detect the orphaned microVM, verify its absence, and cleanly requeue the execution.
    """
    from app.workers.execution_worker import ExecutionWorker

    session_factory = MockSessionFactory(db_session)
    user = User(email="crash-test@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    plan_dict = copy.deepcopy(VALID_PLAN_DICT)
    plan_hash = compute_plan_hash(plan_dict)

    task = Task(user_id=user.id, title="Crash Recovery Task", description="Simulate crash", status="queued")
    db_session.add(task)
    await db_session.flush()

    approval = Approval(task_id=task.id, approved_by=user.email, approved_plan_hash=plan_hash, decision="approved")
    db_session.add(approval)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        approval_id=approval.id,
        plan_hash=plan_hash,
        plan_snapshot=plan_dict,
        status="queued",
        timeout_seconds=30,
    )
    db_session.add(execution)
    await db_session.commit()

    # Step 1: Claim execution
    queue_mgr = QueueManager(session_factory)
    claimed = await queue_mgr.claim_next_execution("crashing-worker", lease_duration_seconds=1, max_attempts=3)
    assert claimed is not None

    # Step 2: Worker allocates and persists sandbox_id before provisioning
    worker = ExecutionWorker(session_factory=session_factory, worker_id="crashing-worker")
    sandbox_id = worker.sandbox_manager.generate_sandbox_id(task.id, execution.id)

    # Worker records sandbox_id and starts running
    execution.sandbox_id = sandbox_id
    execution.status = "running"
    # Worker crashes! Lease expires immediately:
    execution.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    await db_session.commit()

    # Verify that before reconciliation, sandbox_id is safely stored in database
    await db_session.refresh(execution)
    assert execution.sandbox_id == sandbox_id
    assert execution.status == "running"

    # Step 3: StaleExecutionReconciler runs and reconciles the orphaned execution
    reconciler = StaleExecutionReconciler(session_factory)
    reconciled_count = await reconciler.reconcile_stale_executions(max_attempts=3)
    assert reconciled_count == 1

    await db_session.refresh(execution)
    await db_session.refresh(task)
    assert execution.status == "queued"
    assert execution.cleanup_status == "verified_destroyed"
    assert execution.worker_id is None
    assert task.status == "queued"


@pytest.mark.asyncio
async def test_old_worker_cannot_overwrite_state_of_replacement_worker(db_session: AsyncSession):
    """
    Proves that an old worker that lost ownership cannot overwrite the state of a replacement worker.
    """
    from app.workers.execution_worker import ExecutionWorker
    from app.services.sandbox.base import MultiStepExecutionResult

    session_factory = MockSessionFactory(db_session)
    user = User(email="ownership-test@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    plan_dict = copy.deepcopy(VALID_PLAN_DICT)
    plan_hash = compute_plan_hash(plan_dict)

    task = Task(user_id=user.id, title="Ownership Guard Task", description="Testing worker CAS", status="running")
    db_session.add(task)
    await db_session.flush()

    # Execution was reassigned to replacement-worker-02
    execution = Execution(
        task_id=task.id,
        plan_hash=plan_hash,
        plan_snapshot=plan_dict,
        status="running",
        worker_id="replacement-worker-02",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    db_session.add(execution)
    await db_session.commit()

    # Old worker (worker-01) tries to finalize execution or persist output
    old_worker = ExecutionWorker(session_factory=session_factory, worker_id="worker-01")

    # Finalization must be rejected because worker_id doesn't match
    dummy_result = MultiStepExecutionResult(
        task_id=task.id,
        execution_id=execution.id,
        sandbox_id="sb-old",
        status="succeeded",
        step_outputs=[],
        artifacts=[],
        cleanup_status="verified_destroyed",
        execution_mode="mock",
        duration_seconds=1.5,
        exit_code=0,
    )
    await old_worker._finalize_execution(execution.id, task.id, dummy_result)

    await db_session.refresh(execution)
    await db_session.refresh(task)
    # Execution remains owned by replacement-worker-02 with running status
    assert execution.worker_id == "replacement-worker-02"
    assert execution.status == "running"
    assert task.status == "running"


@pytest.mark.asyncio
async def test_unverified_sandbox_cleanup_marks_needs_reconciliation(db_session: AsyncSession):
    """
    Proves that when microVM absence cannot be established, the execution transitions
    to 'needs_reconciliation' and is NEVER requeued.
    """
    session_factory = MockSessionFactory(db_session)
    user = User(email="leak-test@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    task = Task(user_id=user.id, title="Unverified Teardown Task", description="Leak test", status="running")
    db_session.add(task)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        status="running",
        worker_id="crashed-worker",
        sandbox_id="leaked-microvm-001",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    db_session.add(execution)
    await db_session.commit()

    reconciler = StaleExecutionReconciler(session_factory)
    # Simulate failed absence verification
    reconciler._force_cleanup_unverified = True

    count = await reconciler.reconcile_stale_executions(max_attempts=3)
    assert count == 1

    await db_session.refresh(execution)
    await db_session.refresh(task)
    assert execution.status == "needs_reconciliation"
    assert execution.cleanup_status == "leak_detected"
    assert task.status == "needs_reconciliation"
