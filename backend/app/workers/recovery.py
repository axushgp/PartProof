import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.core.config import settings
from app.models.entities import Execution, ExecutionEvent, Task
from app.services.sandbox.subprocess_utils import run_subprocess_safe

logger = logging.getLogger("partproof.worker.recovery")


class StaleExecutionReconciler:
    """
    Identifies executions whose worker lease expired without a completed terminal status.
    Enforces the critical safety invariant: Lease expiration does NOT prove the microVM stopped.
    Verifies microVM absence/cleanup before requeueing, or marks the execution as 'needs_reconciliation'.

    Uses a non-blocking two-phase claim to avoid holding open database transactions
    during external subprocess calls and prevent concurrent reconciliation by multiple workers.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def reconcile_stale_executions(self, max_attempts: int = 3) -> int:
        """
        Scans for and resolves executions with expired worker leases.
        Returns the number of reconciled executions.
        """
        reconciled_count = 0

        while True:
            # Phase 1: Atomically claim one stale execution with row-level locking
            claim = await self._claim_next_stale_execution()
            if claim is None:
                break

            exec_id, task_id, original_worker_id, sandbox_id, attempt_count, reconciler_id = claim

            # Phase 2: External verification and cleanup (no DB transaction held)
            cleanup_verified, cleanup_detail = await self._verify_and_cleanup_sandbox(sandbox_id)

            # Phase 3: Finalize state transition with ownership check
            finalized = await self._finalize_reconciliation(
                execution_id=exec_id,
                task_id=task_id,
                reconciler_id=reconciler_id,
                original_worker_id=original_worker_id,
                sandbox_id=sandbox_id,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
                cleanup_verified=cleanup_verified,
                cleanup_detail=cleanup_detail,
            )
            if finalized:
                reconciled_count += 1

        return reconciled_count

    async def _claim_next_stale_execution(
        self,
    ) -> Optional[Tuple[str, str, Optional[str], Optional[str], int, str]]:
        """
        Finds and claims one stale execution using row-level locking (SKIP LOCKED).
        Extends the lease to the reconciler and commits immediately.
        Returns (execution_id, task_id, original_worker_id, sandbox_id, attempt_count, reconciler_id).
        """
        now = datetime.now(timezone.utc)
        reconciler_id = f"reconciler-{uuid.uuid4().hex[:8]}"
        recovery_lease = now + timedelta(seconds=settings.WORKER_LEASE_DURATION_SECONDS)

        async with self.session_factory() as session:
            dialect_name = session.bind.dialect.name if session.bind else "postgresql"
            is_postgres = "postgres" in dialect_name

            stmt = (
                select(Execution)
                .join(Task, Task.id == Execution.task_id)
                .where(
                    Execution.status.in_(("preparing", "running", "verifying")),
                    Execution.lease_expires_at < now,
                )
                .order_by(Execution.lease_expires_at.asc())
                .limit(1)
            )

            if is_postgres:
                stmt = stmt.with_for_update(of=Execution, skip_locked=True)

            res = await session.execute(stmt)
            execution = res.scalar_one_or_none()

            if not execution:
                return None

            original_worker_id = execution.worker_id
            exec_id = execution.id
            task_id = execution.task_id
            sandbox_id = execution.sandbox_id
            attempt_count = execution.attempt_count

            # Atomically transfer lease ownership to reconciler
            execution.worker_id = reconciler_id
            execution.lease_expires_at = recovery_lease

            session.add(
                ExecutionEvent(
                    task_id=task_id,
                    execution_id=exec_id,
                    event_type="execution_reconciliation_started",
                    message=(
                        f"Stale execution lease expired (worker={original_worker_id}). "
                        f"Claimed by {reconciler_id} for microVM verification and cleanup."
                    ),
                    metadata_json={
                        "original_worker_id": original_worker_id,
                        "reconciler_id": reconciler_id,
                        "sandbox_id": sandbox_id,
                    },
                )
            )
            await session.commit()

            logger.info(
                "Claimed stale execution %s (sandbox=%s, original_worker=%s) for reconciliation by %s",
                exec_id,
                sandbox_id,
                original_worker_id,
                reconciler_id,
            )
            return (exec_id, task_id, original_worker_id, sandbox_id, attempt_count, reconciler_id)

    async def _finalize_reconciliation(
        self,
        execution_id: str,
        task_id: str,
        reconciler_id: str,
        original_worker_id: Optional[str],
        sandbox_id: Optional[str],
        attempt_count: int,
        max_attempts: int,
        cleanup_verified: bool,
        cleanup_detail: str,
    ) -> bool:
        """
        Applies terminal or requeue transition conditional on reconciler ownership.
        """
        async with self.session_factory() as session:
            exec_rec = await session.get(Execution, execution_id)
            task_rec = await session.get(Task, task_id)

            if not exec_rec or not task_rec:
                return False

            # Verify that reconciler still owns this execution
            if exec_rec.worker_id != reconciler_id:
                logger.warning(
                    "Reconciler %s lost ownership of execution %s during verification",
                    reconciler_id,
                    execution_id,
                )
                return False

            if not cleanup_verified:
                logger.error(
                    "Execution %s (sandbox %s) cannot be proven stopped: %s. Marking 'needs_reconciliation'.",
                    execution_id,
                    sandbox_id,
                    cleanup_detail,
                )
                exec_rec.status = "needs_reconciliation"
                exec_rec.cleanup_status = "leak_detected"
                exec_rec.lease_expires_at = None
                task_rec.status = "needs_reconciliation"
                session.add(
                    ExecutionEvent(
                        task_id=task_id,
                        execution_id=execution_id,
                        event_type="execution_needs_reconciliation",
                        message=(
                            f"Worker lease expired (worker={original_worker_id}), but microVM destruction "
                            f"could not be confirmed: {cleanup_detail}. Manual reconciliation required."
                        ),
                        metadata_json={
                            "original_worker_id": original_worker_id,
                            "sandbox_id": sandbox_id,
                            "detail": cleanup_detail,
                        },
                    )
                )
                await session.commit()
                return True

            # Cleanup is independently confirmed
            exec_rec.cleanup_status = "verified_destroyed"

            if attempt_count < max_attempts:
                logger.info(
                    "Requeueing execution %s (attempt %d/%d) after confirmed microVM teardown",
                    execution_id,
                    attempt_count,
                    max_attempts,
                )
                exec_rec.status = "queued"
                exec_rec.worker_id = None
                exec_rec.lease_expires_at = None
                task_rec.status = "queued"
                session.add(
                    ExecutionEvent(
                        task_id=task_id,
                        execution_id=execution_id,
                        event_type="execution_requeued",
                        message=(
                            f"Execution lease expired for worker {original_worker_id}. "
                            f"MicroVM destruction confirmed ({cleanup_detail}); requeueing for attempt {attempt_count + 1}."
                        ),
                        metadata_json={
                            "original_worker_id": original_worker_id,
                            "sandbox_id": sandbox_id,
                            "detail": cleanup_detail,
                            "next_attempt": attempt_count + 1,
                        },
                    )
                )
            else:
                logger.warning(
                    "Execution %s exceeded max attempts (%d) following lease expiry. Marking failed.",
                    execution_id,
                    max_attempts,
                )
                exec_rec.status = "failed"
                exec_rec.worker_id = None
                exec_rec.lease_expires_at = None
                task_rec.status = "failed"
                session.add(
                    ExecutionEvent(
                        task_id=task_id,
                        execution_id=execution_id,
                        event_type="execution_failed",
                        message=(
                            f"Execution exceeded max attempts ({max_attempts}) after lease expiration. "
                            f"MicroVM teardown was confirmed."
                        ),
                        metadata_json={
                            "original_worker_id": original_worker_id,
                            "sandbox_id": sandbox_id,
                            "attempts": attempt_count,
                        },
                    )
                )

            await session.commit()
            return True

    async def _verify_and_cleanup_sandbox(self, sandbox_id: Optional[str]) -> Tuple[bool, str]:
        """
        Attempts to verify and ensure that the microVM is destroyed.
        Checks subprocess exit codes and error output.
        Independently verifies that the sandbox is absent via 'msb ls'.
        Never equates command completion with confirmed destruction.
        Returns (is_verified_destroyed, detail_message).
        """
        if not sandbox_id:
            return True, "No sandbox_id was allocated; microVM was never created."

        if settings.SANDBOX_BACKEND == "mock":
            # In mock mode, check if a simulated leak is flagged
            if getattr(self, "_force_cleanup_unverified", False):
                return False, "Simulated cleanup verification failure in mock mode."
            return True, f"Mock sandbox '{sandbox_id}' verified destroyed."

        # Production / Linux Microsandbox mode
        msb_bin = os.environ.get("MSB_BIN", "/home/linuxuser/.local/bin/msb")
        if not os.path.exists(msb_bin):
            resolved = shutil.which("msb")
            if resolved:
                msb_bin = resolved
            else:
                return False, f"msb CLI binary not found at '{msb_bin}' or in PATH; cannot prove destruction."

        # Step 1: Force remove sandbox and its stored resources via msb rm --force
        rm_rc, rm_out, rm_err, rm_err_msg = await run_subprocess_safe(
            msb_bin,
            ["rm", "--force", sandbox_id],
            timeout=10.0,
        )
        if rm_err_msg:
            logger.warning("msb rm --force warning for %s: %s", sandbox_id, rm_err_msg)
        elif rm_rc != 0:
            err_text = rm_err.decode("utf-8", errors="replace").strip()
            # Do not immediately classify cleanup as failed; sandbox may already be absent.
            # Independent verification via msb ls follows.
            logger.warning("msb rm --force returned non-zero code %d for %s: %s", rm_rc, sandbox_id, err_text)
        else:
            logger.info("msb rm --force successfully executed for %s", sandbox_id)

        # Step 2: Independently verify complete absence via msb ls
        ls_rc, ls_out, ls_err, ls_err_msg = await run_subprocess_safe(
            msb_bin,
            ["ls"],
            timeout=5.0,
        )
        if ls_err_msg:
            return False, f"msb ls verification failed: {ls_err_msg}"

        if ls_rc != 0:
            err_text = ls_err.decode("utf-8", errors="replace").strip()
            return False, f"msb ls verification failed with exit code {ls_rc}: {err_text}"

        ls_text = ls_out.decode("utf-8", errors="replace")
        if sandbox_id in ls_text:
            return False, f"Sandbox microVM '{sandbox_id}' still detected present in msb ls: {ls_text.strip()}"

        return True, f"MicroVM '{sandbox_id}' confirmed absent in msb ls."
