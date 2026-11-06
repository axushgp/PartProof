import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine, Optional
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.models.entities import Execution

logger = logging.getLogger("partproof.worker.leases")


class LeaseManager:
    """
    Manages distributed execution leases and heartbeats via CAS updates.
    Ensures that a worker retains ownership of an active execution and detects
    lost leases or worker preemption.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def renew_lease(
        self,
        execution_id: str,
        worker_id: str,
        lease_duration_seconds: int = 60,
    ) -> bool:
        """
        Executes atomic Compare-And-Swap (CAS) update to extend the lease.
        Returns True if lease renewed, False if lease was lost or execution status changed.
        """
        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_duration_seconds)
        active_statuses = ("preparing", "running", "verifying")

        async with self.session_factory() as session:
            stmt = (
                update(Execution)
                .where(
                    Execution.id == execution_id,
                    Execution.worker_id == worker_id,
                    Execution.status.in_(active_statuses),
                )
                .values(lease_expires_at=new_expires_at)
            )
            result = await session.execute(stmt)
            await session.commit()
            renewed = result.rowcount > 0

        if not renewed:
            logger.warning(
                "Lease renewal CAS failed for execution %s (worker_id=%s). Lease was lost.",
                execution_id,
                worker_id,
            )
        else:
            logger.debug(
                "Lease renewed for execution %s until %s",
                execution_id,
                new_expires_at.isoformat(),
            )

        return renewed

    async def start_heartbeat(
        self,
        execution_id: str,
        worker_id: str,
        heartbeat_interval_seconds: float = 15.0,
        lease_duration_seconds: int = 60,
        on_lease_lost: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
    ) -> None:
        """
        Starts background heartbeat loop renewing lease every heartbeat_interval_seconds.
        """
        self._stop_event.clear()

        async def _heartbeat_loop():
            logger.info("Heartbeat loop started for execution %s", execution_id)
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=heartbeat_interval_seconds,
                    )
                    break
                except asyncio.TimeoutError:
                    pass

                try:
                    renewed = await self.renew_lease(
                        execution_id=execution_id,
                        worker_id=worker_id,
                        lease_duration_seconds=lease_duration_seconds,
                    )
                    if not renewed:
                        logger.error(
                            "Lease lost during heartbeat for execution %s. Triggering callback.",
                            execution_id,
                        )
                        if on_lease_lost:
                            try:
                                await on_lease_lost()
                            except Exception as cb_err:
                                logger.error("Error in on_lease_lost callback: %s", cb_err)
                        break
                except Exception as e:
                    logger.error("Exception during lease renewal for %s: %s. Failing closed.", execution_id, e)
                    if on_lease_lost:
                        try:
                            await on_lease_lost()
                        except Exception as cb_err:
                            logger.error("Error in on_lease_lost callback: %s", cb_err)
                    break

            logger.info("Heartbeat loop terminated for execution %s", execution_id)

        self._heartbeat_task = asyncio.create_task(_heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        """Stops the active background heartbeat task."""
        self._stop_event.set()
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
