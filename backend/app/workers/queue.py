import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from app.models.entities import Execution, ExecutionEvent, Task

logger = logging.getLogger("partproof.worker.queue")


@dataclass(frozen=True)
class ClaimedExecution:
    execution_id: str
    task_id: str
    worker_id: str
    plan_snapshot: Dict[str, Any]
    plan_hash: str
    attempt_count: int
    runtime_image: str
    cpu_limit: int
    memory_limit_mb: int
    network_mode: str
    timeout_seconds: int


class QueueManager:
    """
    Manages queue claiming for worker execution.
    Adheres strictly to the lock-ordering invariant: ALWAYS lock Task first,
    then Execution, using PostgreSQL SKIP LOCKED to prevent deadlocks and race conditions.
    Commits the claim transaction immediately so database connections are not held open
    during isolated microVM lifecycle operations.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def claim_next_execution(
        self,
        worker_id: str,
        lease_duration_seconds: int = 60,
        max_attempts: int = 3,
    ) -> Optional[ClaimedExecution]:
        """
        Atomically claims the next eligible queued execution from PostgreSQL.
        Returns ClaimedExecution if claimed, None if queue is empty.
        """
        async with self.session_factory() as session:
            dialect_name = session.bind.dialect.name if session.bind else "postgresql"
            is_postgres = "postgres" in dialect_name

            # 1. Lock Task first with SKIP LOCKED to enforce lock ordering
            task_stmt = (
                select(Task)
                .join(Execution, Execution.task_id == Task.id)
                .where(
                    Task.status == "queued",
                    Execution.status == "queued",
                )
                .order_by(Execution.queued_at.asc())
                .limit(1)
            )

            if is_postgres:
                task_stmt = task_stmt.with_for_update(of=Task, skip_locked=True)

            task_res = await session.execute(task_stmt)
            task = task_res.scalar_one_or_none()

            if not task:
                return None

            # 2. Lock Execution within the same transaction
            exec_stmt = (
                select(Execution)
                .where(
                    Execution.task_id == task.id,
                    Execution.status == "queued",
                )
                .options(selectinload(Execution.approval))
            )
            if is_postgres:
                exec_stmt = exec_stmt.with_for_update(of=Execution)

            exec_res = await session.execute(exec_stmt)
            execution = exec_res.scalar_one_or_none()

            if not execution:
                # Execution was cancelled or modified
                return None

            now = datetime.now(timezone.utc)

            # 3. Verify maximum attempts
            if execution.attempt_count >= max_attempts:
                logger.warning(
                    "Execution %s for task %s exceeded max attempts (%d >= %d). Marking failed.",
                    execution.id,
                    task.id,
                    execution.attempt_count,
                    max_attempts,
                )
                execution.status = "failed"
                task.status = "failed"
                session.add(
                    ExecutionEvent(
                        task_id=task.id,
                        execution_id=execution.id,
                        event_type="execution_failed",
                        message=f"Execution exceeded maximum retry attempts ({max_attempts}).",
                    )
                )
                await session.commit()
                return None

            # 4. Verify approval integrity upon claim
            approval = execution.approval
            if (
                not approval
                or approval.decision != "approved"
                or approval.approved_plan_hash != execution.plan_hash
            ):
                logger.warning(
                    "Execution %s has invalid approval or hash mismatch upon claim. Marking failed.",
                    execution.id,
                )
                execution.status = "failed"
                task.status = "failed"
                session.add(
                    ExecutionEvent(
                        task_id=task.id,
                        execution_id=execution.id,
                        event_type="execution_failed",
                        message="Queue claim rejected: missing or mismatched approval record.",
                    )
                )
                await session.commit()
                return None

            if not execution.plan_snapshot:
                logger.warning("Execution %s missing plan snapshot upon claim.", execution.id)
                execution.status = "failed"
                task.status = "failed"
                session.add(
                    ExecutionEvent(
                        task_id=task.id,
                        execution_id=execution.id,
                        event_type="execution_failed",
                        message="Queue claim rejected: missing plan snapshot.",
                    )
                )
                await session.commit()
                return None

            # 5. Apply claim transition
            execution.status = "preparing"
            execution.worker_id = worker_id
            execution.attempt_count += 1
            execution.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
            if execution.started_at is None:
                execution.started_at = now

            task.status = "running"

            session.add(
                ExecutionEvent(
                    task_id=task.id,
                    execution_id=execution.id,
                    event_type="execution_claimed",
                    message=(
                        f"Execution claimed by worker {worker_id} (attempt {execution.attempt_count}/{max_attempts}, "
                        f"lease expires in {lease_duration_seconds}s)."
                    ),
                    metadata_json={
                        "worker_id": worker_id,
                        "attempt": execution.attempt_count,
                        "lease_expires_at": execution.lease_expires_at.isoformat(),
                    },
                )
            )

            # 6. Commit the claim transaction immediately before microVM provisioning
            await session.commit()

            logger.info(
                "Execution %s (task %s) claimed by worker %s (attempt %d)",
                execution.id,
                task.id,
                worker_id,
                execution.attempt_count,
            )

            return ClaimedExecution(
                execution_id=execution.id,
                task_id=task.id,
                worker_id=worker_id,
                plan_snapshot=execution.plan_snapshot,
                plan_hash=execution.plan_hash,
                attempt_count=execution.attempt_count,
                runtime_image=execution.runtime_image,
                cpu_limit=execution.cpu_limit,
                memory_limit_mb=execution.memory_limit_mb,
                network_mode=execution.network_mode,
                timeout_seconds=execution.timeout_seconds,
            )
