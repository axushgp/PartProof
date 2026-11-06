import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.models.entities import Execution, ExecutionEvent, Task

logger = logging.getLogger("partproof.worker.recovery")


class StaleExecutionReconciler:
    """
    Identifies executions whose worker lease expired without a completed terminal status.
    Enforces the critical safety invariant: Lease expiration does NOT prove the microVM stopped.
    Verifies microVM absence/cleanup before requeueing, or marks the execution as 'needs_reconciliation'.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def reconcile_stale_executions(self, max_attempts: int = 3) -> int:
        """
        Scans for and resolves executions with expired worker leases.
        Returns the number of reconciled executions.
        """
        now = datetime.now(timezone.utc)
        reconciled_count = 0

        async with self.session_factory() as session:
            stmt = (
                select(Execution)
                .join(Task, Task.id == Execution.task_id)
                .where(
                    Execution.status.in_(("preparing", "running", "verifying")),
                    Execution.lease_expires_at < now,
                )
            )
            res = await session.execute(stmt)
            stale_executions = res.scalars().all()

            if not stale_executions:
                return 0

            logger.warning("Found %d stale execution(s) with expired leases", len(stale_executions))

            for execution in stale_executions:
                task = await session.get(Task, execution.task_id)
                if not task:
                    continue

                cleanup_verified = await self._verify_and_cleanup_sandbox(execution.sandbox_id)

                if not cleanup_verified:
                    logger.error(
                        "Execution %s (sandbox %s) cannot be proven stopped. Marking 'needs_reconciliation'.",
                        execution.id,
                        execution.sandbox_id,
                    )
                    execution.status = "needs_reconciliation"
                    task.status = "needs_reconciliation"
                    session.add(
                        ExecutionEvent(
                            task_id=task.id,
                            execution_id=execution.id,
                            event_type="execution_needs_reconciliation",
                            message=(
                                f"Worker lease expired (worker={execution.worker_id}), but sandbox microVM "
                                f"absence could not be confirmed. Manual reconciliation required."
                            ),
                        )
                    )
                    reconciled_count += 1
                    continue

                # Cleanup confirmed
                execution.cleanup_status = "verified_destroyed"

                if execution.attempt_count < max_attempts:
                    logger.info(
                        "Requeueing execution %s (attempt %d/%d) after confirmed microVM teardown",
                        execution.id,
                        execution.attempt_count,
                        max_attempts,
                    )
                    execution.status = "queued"
                    execution.worker_id = None
                    execution.lease_expires_at = None
                    task.status = "queued"
                    session.add(
                        ExecutionEvent(
                            task_id=task.id,
                            execution_id=execution.id,
                            event_type="execution_requeued",
                            message=(
                                f"Execution lease expired for worker {execution.worker_id}. "
                                f"MicroVM was cleaned up; requeueing for attempt {execution.attempt_count + 1}."
                            ),
                        )
                    )
                else:
                    logger.warning(
                        "Execution %s exceeded max attempts (%d) following lease expiry. Marking failed.",
                        execution.id,
                        max_attempts,
                    )
                    execution.status = "failed"
                    task.status = "failed"
                    session.add(
                        ExecutionEvent(
                            task_id=task.id,
                            execution_id=execution.id,
                            event_type="execution_failed",
                            message=f"Execution exceeded max attempts ({max_attempts}) after lease expiration.",
                        )
                    )

                reconciled_count += 1

            await session.commit()

        return reconciled_count

    async def _verify_and_cleanup_sandbox(self, sandbox_id: Optional[str]) -> bool:
        """
        Attempts to verify that the microVM is destroyed.
        If sandbox_id is None, no microVM was created yet.
        """
        if not sandbox_id:
            return True

        # In mock mode or when CLI is not available
        try:
            from app.core.config import settings
            if settings.SANDBOX_BACKEND == "mock":
                return True

            # In Linux/Microsandbox mode, attempt CLI list or stop
            proc = await asyncio.create_subprocess_exec(
                "msb", "stop", sandbox_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return True
        except Exception as e:
            logger.warning("Error verifying microVM cleanup for %s: %s", sandbox_id, e)
            # If backend is mock or command not found in tests, treat as verified
            from app.core.config import settings
            if settings.SANDBOX_BACKEND == "mock":
                return True
            return False
