import asyncio
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("partproof.sandbox.subprocess")


async def _do_terminate_and_reap(
    proc: asyncio.subprocess.Process,
    cmd: str,
    args: List[str],
    terminate_grace_period: float,
    kill_grace_period: float,
    reason: str,
) -> Tuple[Optional[int], bytes, bytes, str, bool]:
    """
    Terminates, escalates to kill if necessary, and reaps a subprocess.
    Returns (returncode, stdout, stderr, message, exit_confirmed).
    """
    stdout, stderr = b"", b""

    # 1. Graceful termination
    try:
        proc.terminate()
    except ProcessLookupError:
        pass
    except Exception as te:
        logger.warning("Error calling terminate() on %s: %s", cmd, te)

    # 2. Wait up to terminate_grace_period
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=terminate_grace_period)
        msg = f"Subprocess '{cmd}' {reason} and was terminated."
        return None, stdout, stderr, msg, True
    except asyncio.TimeoutError:
        logger.warning(
            "Subprocess '%s' did not terminate after %0.1fs; escalating to kill...",
            cmd,
            terminate_grace_period,
        )
    except Exception as term_err:
        logger.warning("Error waiting for termination of %s: %s", cmd, term_err)

    # 3. Escalate to kill
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    except Exception as ke:
        logger.warning("Error calling kill() on %s: %s", cmd, ke)

    # 4. Wait up to kill_grace_period to reap process
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=kill_grace_period)
        msg = f"Subprocess '{cmd}' {reason} and was killed."
        return None, stdout, stderr, msg, True
    except asyncio.TimeoutError:
        logger.warning(
            "Subprocess '%s' failed to exit after kill within %0.1fs grace period",
            cmd,
            kill_grace_period,
        )
        msg = (
            f"Subprocess '{cmd}' {reason}; kill escalation timed out after "
            f"{kill_grace_period}s (cleanup unverified, process reaping unconfirmed)."
        )
        return None, stdout, stderr, msg, False
    except Exception as reap_err:
        logger.warning("Error reaping killed subprocess %s: %s", cmd, reap_err)
        msg = f"Subprocess '{cmd}' {reason}; kill escalation failed: {reap_err} (cleanup unverified)."
        return None, stdout, stderr, msg, False


async def _shielded_terminate_and_reap(
    proc: asyncio.subprocess.Process,
    cmd: str,
    args: List[str],
    terminate_grace_period: float,
    kill_grace_period: float,
    reason: str,
) -> Tuple[Optional[int], bytes, bytes, str, bool]:
    """
    Executes _do_terminate_and_reap inside an independent shielded Task,
    ensuring parent cancellations cannot interrupt process termination and reaping.
    """
    task = asyncio.create_task(
        _do_terminate_and_reap(
            proc, cmd, args, terminate_grace_period, kill_grace_period, reason
        )
    )
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass
    return task.result()


async def run_subprocess_safe(
    cmd: str,
    args: List[str],
    timeout: float,
    terminate_grace_period: float = 2.0,
    kill_grace_period: float = 2.0,
) -> Tuple[Optional[int], bytes, bytes, Optional[str]]:
    """
    Executes a subprocess with bounded timeout, graceful termination, kill escalation,
    and guaranteed process reaping.

    Lifecycle guarantees:
    1. Bounds overall command execution by the specified `timeout`.
    2. On command timeout, sends SIGTERM (`proc.terminate()`), waits up to
       `terminate_grace_period`, escalates to SIGKILL (`proc.kill()`) if the process
       fails to exit, and reaps the process via `communicate()`.
    3. On parent coroutine cancellation (`asyncio.CancelledError`), executes the termination,
       kill-escalation, and reaping sequence inside a shielded task to protect cleanup
       from being interrupted by the parent cancellation, ensuring no spawned process
       is abandoned before propagating `CancelledError`.
    4. If process exit cannot be verified (e.g. final wait after kill times out or fails),
       reports cleanup as unverified and does not claim the process was reaped.
    5. Cleanly integrates with configurable grace periods (e.g. `SANDBOX_CLEANUP_TIMEOUT_SECONDS`, default 30.0s).

    Returns:
        (returncode, stdout, stderr, error_msg)
        where error_msg is None if the command completed normally within timeout.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        return None, b"", b"", f"Failed to spawn process '{cmd}': {e}"

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout, stderr, None
    except asyncio.TimeoutError:
        logger.warning(
            "Subprocess '%s %s' exceeded timeout of %0.1fs; terminating...",
            cmd,
            " ".join(args),
            timeout,
        )
        rc, out, err, msg, confirmed = await _shielded_terminate_and_reap(
            proc,
            cmd,
            args,
            terminate_grace_period,
            kill_grace_period,
            reason=f"timed out after {timeout}s",
        )
        return rc, out, err, msg
    except asyncio.CancelledError as ce:
        logger.warning(
            "Subprocess '%s %s' cancelled by parent coroutine; terminating and reaping...",
            cmd,
            " ".join(args),
        )
        rc, out, err, msg, confirmed = await _shielded_terminate_and_reap(
            proc,
            cmd,
            args,
            terminate_grace_period,
            kill_grace_period,
            reason="cancelled by parent coroutine",
        )
        if not confirmed:
            logger.error(
                "Subprocess '%s' cancelled and cleanup unverified: %s",
                cmd,
                msg,
            )
            raise asyncio.CancelledError(msg) from ce
        raise
    except Exception as e:
        return None, b"", b"", f"Unexpected error executing '{cmd}': {e}"
