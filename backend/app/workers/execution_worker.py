import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database.session import async_session_maker
from app.models.entities import (
    Approval,
    Artifact,
    Execution,
    ExecutionEvent,
    ExecutionStep,
    Task,
)
from app.services.artifacts.manager import ArtifactManager
from app.services.sandbox.base import (
    MultiStepExecutionResult,
    StepExecutionOutput,
    StepExecutionRequest,
)
from app.services.sandbox.manager import SandboxManager
from app.workers.host_lock import HostLock, HostLockError
from app.workers.leases import LeaseManager
from app.workers.queue import ClaimedExecution, QueueManager
from app.workers.recovery import StaleExecutionReconciler
from app.workers.validator import SecurityExecutionValidator, SecurityValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("partproof.worker")


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures datetime is timezone-aware UTC for safe comparisons across SQLite and PostgreSQL."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ExecutionWorker:
    """
    Persistent background execution worker for PartProof.
    Orchestrates queue claiming via PostgreSQL SKIP LOCKED, distributed lease heartbeats,
    and isolated multi-step execution in Microsandbox microVMs with zero networking.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        artifact_manager: Optional[ArtifactManager] = None,
        worker_id: Optional[str] = None,
    ):
        self.session_factory = session_factory or async_session_maker
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.sandbox_manager = sandbox_manager or SandboxManager(artifact_manager=self.artifact_manager)
        self.worker_id = worker_id or settings.WORKER_ID
        self.queue_manager = QueueManager(self.session_factory)
        self.lease_manager = LeaseManager(self.session_factory)
        self.reconciler = StaleExecutionReconciler(self.session_factory)
        self.validator = SecurityExecutionValidator(artifact_manager=self.artifact_manager)
        self.host_lock = HostLock(settings.WORKER_LOCK_FILE_PATH)
        self._stop_requested = False
        self._current_execution_id: Optional[str] = None
        self._execution_cancelled = False

    def request_stop(self) -> None:
        """Signals graceful shutdown."""
        logger.info("Graceful shutdown requested for worker %s", self.worker_id)
        self._stop_requested = True

    async def run(self, run_once: bool = False) -> None:
        """
        Main worker execution loop.
        """
        settings.validate_worker_production_invariants()

        if not self.host_lock.acquire():
            logger.error("Could not acquire host lock %s. Another worker is active.", settings.WORKER_LOCK_FILE_PATH)
            sys.exit(1)

        logger.info(
            "PartProof Worker started (worker_id=%s, backend=%s, env=%s, max_concurrency=%d)",
            self.worker_id,
            settings.SANDBOX_BACKEND,
            settings.PARTPROOF_ENV,
            settings.SANDBOX_MAX_CONCURRENT,
        )

        try:
            while not self._stop_requested:
                # 1. Reconcile stale executions
                try:
                    await self.reconciler.reconcile_stale_executions(max_attempts=settings.WORKER_MAX_ATTEMPTS)
                except Exception as rec_err:
                    logger.error("Error during stale execution reconciliation: %s", rec_err)

                # 2. Claim next execution
                claimed: Optional[ClaimedExecution] = None
                try:
                    claimed = await self.queue_manager.claim_next_execution(
                        worker_id=self.worker_id,
                        lease_duration_seconds=settings.WORKER_LEASE_DURATION_SECONDS,
                        max_attempts=settings.WORKER_MAX_ATTEMPTS,
                    )
                except Exception as claim_err:
                    logger.error("Error claiming execution from queue: %s", claim_err)

                if claimed is None:
                    if run_once:
                        logger.info("Run-once mode: queue is empty, terminating.")
                        break
                    try:
                        await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)
                    except asyncio.CancelledError:
                        break
                    continue

                # 3. Process claimed execution
                self._current_execution_id = claimed.execution_id
                self._execution_cancelled = False
                try:
                    await self._process_execution(claimed)
                except Exception as proc_err:
                    logger.error("Fatal error processing execution %s: %s", claimed.execution_id, proc_err, exc_info=True)
                finally:
                    self._current_execution_id = None

                if run_once:
                    logger.info("Run-once mode: processed one execution, terminating.")
                    break

        finally:
            self.host_lock.release()
            logger.info("PartProof Worker stopped cleanly (worker_id=%s)", self.worker_id)

    async def _process_execution(self, claimed: ClaimedExecution) -> None:
        """
        Executes a claimed task through validation, microVM execution, and result persistence.
        Enforces strict worker ownership checks at every lifecycle transition.
        """
        execution_id = claimed.execution_id
        task_id = claimed.task_id

        logger.info("Beginning processing for execution %s (task %s)", execution_id, task_id)

        # 1. Fetch execution and approval for pre-execution validation
        plan_schema = None
        sandbox_id = self.sandbox_manager.generate_sandbox_id(task_id, execution_id)
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            stmt = (
                select(Execution)
                .where(Execution.id == execution_id)
                .options(selectinload(Execution.approval), selectinload(Execution.task))
            )
            res = await session.execute(stmt)
            execution = res.scalar_one_or_none()

            if not execution:
                logger.error("Execution %s not found in database during pre-execution check", execution_id)
                return

            approval = execution.approval
            try:
                plan_schema = self.validator.validate(execution, approval)
            except SecurityValidationError as sve:
                logger.error("Security validation rejected execution %s: %s", execution_id, sve.message)
                # Atomic conditional update requiring ownership, preparing status, and unexpired lease
                update_stmt = (
                    update(Execution)
                    .where(
                        Execution.id == execution_id,
                        Execution.worker_id == self.worker_id,
                        Execution.status == "preparing",
                        Execution.lease_expires_at > now,
                    )
                    .values(status="failed", lease_expires_at=None)
                )
                upd_res = await session.execute(update_stmt)
                if upd_res.rowcount > 0:
                    if execution.task:
                        execution.task.status = "failed"
                    session.add(
                        ExecutionEvent(
                            task_id=task_id,
                            execution_id=execution_id,
                            event_type="execution_failed",
                            message=f"Pre-execution security validation failed: {sve.message}",
                            metadata_json={"violations": sve.violations},
                        )
                    )
                    await session.commit()
                return

            # Capture current timestamp immediately before the preparing-to-running transition
            transition_now = datetime.now(timezone.utc)
            update_stmt = (
                update(Execution)
                .where(
                    Execution.id == execution_id,
                    Execution.worker_id == self.worker_id,
                    Execution.status == "preparing",
                    Execution.lease_expires_at > transition_now,
                )
                .values(status="running", sandbox_id=sandbox_id)
            )
            upd_res = await session.execute(update_stmt)
            if upd_res.rowcount == 0:
                logger.warning(
                    "Worker %s lost ownership or lease expired during validation before starting execution %s",
                    self.worker_id,
                    execution_id,
                )
                return

            session.add(
                ExecutionEvent(
                    task_id=task_id,
                    execution_id=execution_id,
                    event_type="execution_started",
                    message=f"MicroVM execution started with {len(plan_schema.steps)} step(s). Sandbox ID: {sandbox_id}",
                    metadata_json={"sandbox_id": sandbox_id, "worker_id": self.worker_id},
                )
            )
            await session.commit()

        # 2. Start lease heartbeat
        async def _on_lease_lost():
            logger.error("Worker %s lost lease for execution %s. Halting execution.", self.worker_id, execution_id)
            self._execution_cancelled = True

        await self.lease_manager.start_heartbeat(
            execution_id=execution_id,
            worker_id=self.worker_id,
            heartbeat_interval_seconds=settings.WORKER_HEARTBEAT_INTERVAL_SECONDS,
            lease_duration_seconds=settings.WORKER_LEASE_DURATION_SECONDS,
            on_lease_lost=_on_lease_lost,
        )

        # 3. Prepare multi-step requests
        step_requests: list[StepExecutionRequest] = [
            StepExecutionRequest(
                step_number=idx,
                description=s.description,
                execution_type=s.execution_type,
                code=s.code,
                timeout_seconds=float(claimed.timeout_seconds),
            )
            for idx, s in enumerate(plan_schema.steps, start=1)
        ]

        # Callbacks
        async def _on_sandbox_created(sb_id: str) -> None:
            """Explicit typed callback confirming sandbox identity is persisted before provisioning."""
            chk_now = datetime.now(timezone.utc)
            async with self.session_factory() as s:
                stmt = (
                    update(Execution)
                    .where(
                        Execution.id == execution_id,
                        Execution.worker_id == self.worker_id,
                        Execution.status == "running",
                        Execution.lease_expires_at > chk_now,
                    )
                    .values(sandbox_id=sb_id)
                )
                res = await s.execute(stmt)
                if res.rowcount == 0:
                    raise RuntimeError(
                        f"Worker {self.worker_id} lost ownership of execution {execution_id} before sandbox creation"
                    )
                s.add(
                    ExecutionEvent(
                        task_id=task_id,
                        execution_id=execution_id,
                        event_type="sandbox_allocated",
                        message=f"Sandbox ID '{sb_id}' verified recorded before microVM provisioning.",
                        metadata_json={"sandbox_id": sb_id, "worker_id": self.worker_id},
                    )
                )
                await s.commit()

        async def _on_step_complete(step_num: int, output: StepExecutionOutput) -> None:
            await self._persist_step_output(execution_id, task_id, claimed.attempt_count, output)

        async def _check_cancellation() -> bool:
            if self._execution_cancelled or self._stop_requested:
                return True
            try:
                async with self.session_factory() as session:
                    chk_now = datetime.now(timezone.utc)
                    exec_rec = await session.get(Execution, execution_id)
                    task_rec = await session.get(Task, task_id)
                    if not exec_rec or not task_rec:
                        logger.warning("Execution or task record missing during cancellation check")
                        self._execution_cancelled = True
                        return True
                    if exec_rec.worker_id != self.worker_id:
                        logger.warning(
                            "Worker %s lost ownership of execution %s during cancellation check (current worker: %s)",
                            self.worker_id,
                            execution_id,
                            exec_rec.worker_id,
                        )
                        self._execution_cancelled = True
                        return True
                    if exec_rec.lease_expires_at and _ensure_utc(exec_rec.lease_expires_at) < chk_now:
                        logger.warning("Worker %s lease expired for execution %s during cancellation check", self.worker_id, execution_id)
                        self._execution_cancelled = True
                        return True
                    if (
                        exec_rec.status in ("cancel_requested", "cancelled")
                        or task_rec.status in ("cancel_requested", "cancelled")
                    ):
                        return True
                    return False
            except Exception as ce:
                logger.error("Database error during cancellation check for %s: %s. Failing closed.", execution_id, ce)
                self._execution_cancelled = True
                return True

        # 4. Execute multi-step isolated MicroVM
        multi_result: Optional[MultiStepExecutionResult] = None
        try:
            multi_result = await self.sandbox_manager.execute_steps(
                task_id=task_id,
                execution_id=execution_id,
                steps=step_requests,
                sandbox_id=sandbox_id,
                on_sandbox_created=_on_sandbox_created,
                expected_artifacts=plan_schema.expected_artifacts,
                image=claimed.runtime_image,
                timeout_seconds=float(claimed.timeout_seconds),
                cpus=claimed.cpu_limit,
                memory_mb=claimed.memory_limit_mb,
                on_step_complete=_on_step_complete,
                check_cancellation=_check_cancellation,
            )
        except Exception as exec_err:
            logger.error("Exception in sandbox_manager.execute_steps: %s", exec_err, exc_info=True)
        finally:
            await self.lease_manager.stop_heartbeat()

        # 5. Persist final results
        await self._finalize_execution(execution_id, task_id, multi_result)

    async def _persist_step_output(
        self,
        execution_id: str,
        task_id: str,
        attempt_number: int,
        output: StepExecutionOutput,
    ) -> None:
        """
        Persists each step output immediately into PostgreSQL upon step completion.
        Enforces worker ID, active execution status ('running'), and unexpired lease.
        A worker that loses its lease must not persist steps, events, or artifacts.
        """
        async with self.session_factory() as session:
            now = datetime.now(timezone.utc)
            dialect_name = session.bind.dialect.name if session.bind else "postgresql"
            is_postgres = "postgres" in dialect_name

            # Row lock / conditional verification of ownership, active running status, and valid lease
            stmt = (
                select(Execution)
                .where(
                    Execution.id == execution_id,
                    Execution.worker_id == self.worker_id,
                    Execution.status == "running",
                    Execution.lease_expires_at > now,
                )
            )
            if is_postgres:
                stmt = stmt.with_for_update(of=Execution)

            res = await session.execute(stmt)
            exec_rec = res.scalar_one_or_none()

            if not exec_rec:
                logger.warning(
                    "Worker %s lost ownership, active status, or unexpired lease for execution %s during step %d output persistence. Mutation aborted.",
                    self.worker_id,
                    execution_id,
                    output.step_number,
                )
                self._execution_cancelled = True
                raise RuntimeError(
                    f"Worker {self.worker_id} lost ownership, active status, or lease for execution {execution_id} before persisting step {output.step_number}"
                )

            step_record = ExecutionStep(
                execution_id=execution_id,
                step_number=output.step_number,
                attempt_number=attempt_number,
                description=output.description or f"Step {output.step_number}",
                execution_type=output.execution_type or "python",
                code=output.code,
                status=output.status,
                stdout=output.stdout,
                stderr=output.stderr,
                exit_code=output.exit_code,
                started_at=output.started_at,
                completed_at=output.completed_at,
            )
            session.add(step_record)
            session.add(
                ExecutionEvent(
                    task_id=task_id,
                    execution_id=execution_id,
                    event_type="execution_step_completed" if output.status != "skipped" else "execution_step_skipped",
                    message=(
                        f"Step {output.step_number} ('{step_record.description}') finished with "
                        f"status '{output.status}' (exit_code={output.exit_code})."
                    ),
                    metadata_json={
                        "step_number": output.step_number,
                        "status": output.status,
                        "exit_code": output.exit_code,
                        "duration_seconds": output.duration_seconds,
                    },
                )
            )
            await session.commit()

    async def _finalize_execution(
        self,
        execution_id: str,
        task_id: str,
        result: Optional[MultiStepExecutionResult],
    ) -> None:
        """
        Atomically updates Execution and Task to terminal states, registers artifacts, and logs events.
        Enforces atomic worker ownership, active execution status ('running'), and unexpired lease.
        A worker that loses its lease must not persist terminal states, artifacts, or events.

        CRITICAL SAFETY INVARIANT:
        If cleanup_status != verified_destroyed, NEVER finalize as succeeded, failed, or cancelled.
        Preserve sandbox identity and transition to needs_reconciliation.
        Covers the result is None, cancelled, timed_out, and failed execution paths.
        """
        async with self.session_factory() as session:
            now = datetime.now(timezone.utc)
            cleanup_status = result.cleanup_status if result else "pending_cleanup"

            # 1. Evaluate target states adhering strictly to cleanup safety invariants
            if cleanup_status != "verified_destroyed":
                # MicroVM destruction could not be independently established.
                # Must NEVER finalize as succeeded, failed, or cancelled.
                # Preserve sandbox identity and transition to needs_reconciliation!
                target_status = "needs_reconciliation"
                task_status = "needs_reconciliation"
                final_cleanup_status = "leak_detected" if cleanup_status in ("failed", "pending_cleanup", "pending") else cleanup_status
                event_type = "execution_needs_reconciliation"
                event_msg = (
                    f"Execution terminated with unverified microVM cleanup ({cleanup_status}). "
                    f"Preserved sandbox identity for manual operator reconciliation."
                )
            elif result is None:
                # Unexpected lifecycle exception, but cleanup was verified
                target_status = "failed"
                task_status = "failed"
                final_cleanup_status = "verified_destroyed"
                event_type = "execution_failed"
                event_msg = "Execution failed: unhandled exception during microVM lifecycle."
            elif result.status == "cancelled" or self._execution_cancelled or self._stop_requested:
                target_status = "cancelled"
                task_status = "cancelled"
                final_cleanup_status = "verified_destroyed"
                event_type = "execution_cancelled"
                event_msg = "Execution cancelled."
            elif result.status == "succeeded":
                target_status = "succeeded"
                task_status = "succeeded"
                final_cleanup_status = "verified_destroyed"
                event_type = "execution_succeeded"
                event_msg = f"Execution succeeded in {result.duration_seconds}s."
            elif result.status == "timed_out":
                target_status = "timed_out"
                task_status = "failed"
                final_cleanup_status = "verified_destroyed"
                event_type = "execution_timed_out"
                event_msg = result.error_message or "Execution timed out."
            else:
                target_status = "failed"
                task_status = "failed"
                final_cleanup_status = "verified_destroyed"
                event_type = "execution_failed"
                event_msg = result.error_message or "Execution failed with non-zero exit code."

            # 2. Atomic conditional SQL update checking worker_id, active running status, AND unexpired lease
            stmt = (
                update(Execution)
                .where(
                    Execution.id == execution_id,
                    Execution.worker_id == self.worker_id,
                    Execution.status == "running",
                    Execution.lease_expires_at > now,
                )
                .values(
                    status=target_status,
                    completed_at=now,
                    duration_seconds=result.duration_seconds if result else None,
                    exit_code=result.exit_code if result else 1,
                    cleanup_status=final_cleanup_status,
                    guest_kernel=result.guest_kernel if result else None,
                    lease_expires_at=None,
                )
            )
            res = await session.execute(stmt)

            if res.rowcount == 0:
                logger.warning(
                    "Worker %s lost ownership, active status, or unexpired lease for execution %s during finalization. "
                    "Finalization aborted: no steps, artifacts, events, or terminal states persisted.",
                    self.worker_id,
                    execution_id,
                )
                return

            # 3. Only mutate Task, add artifacts, and record events if the atomic update affected exactly the claimed row!
            task_rec = await session.get(Task, task_id)
            if task_rec:
                task_rec.status = task_status

            session.add(
                ExecutionEvent(
                    task_id=task_id,
                    execution_id=execution_id,
                    event_type=event_type,
                    message=event_msg,
                    metadata_json={
                        "duration_seconds": result.duration_seconds if result else None,
                        "cleanup_status": final_cleanup_status,
                        "target_status": target_status,
                    },
                )
            )

            # Register artifacts ONLY IF target_status == 'succeeded' and cleanup was confirmed destroyed
            if target_status == "succeeded" and result:
                for art in result.artifacts:
                    session.add(
                        Artifact(
                            task_id=task_id,
                            execution_id=execution_id,
                            filename=art.filename,
                            storage_key=art.storage_path,
                            mime_type=art.mime_type,
                            size_bytes=art.size_bytes,
                            sha256=art.sha256,
                            created_at=art.created_at,
                        )
                    )

            await session.commit()
            logger.info("Execution %s finalized with terminal status '%s'", execution_id, target_status)


def main():
    """CLI entrypoint for standalone worker process."""
    parser = argparse.ArgumentParser(description="PartProof Background Execution Worker")
    parser.add_argument("--once", action="store_true", help="Run one claim iteration and exit")
    args = parser.parse_args()

    worker = ExecutionWorker()

    def _signal_handler(signum, frame):
        logger.info("Received signal %d, stopping worker...", signum)
        worker.request_stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    asyncio.run(worker.run(run_once=args.once))


if __name__ == "__main__":
    main()
