import asyncio
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("partproof.sandbox.subprocess")


async def run_subprocess_safe(
    cmd: str,
    args: List[str],
    timeout: float,
    terminate_grace_period: float = 2.0,
    kill_grace_period: float = 2.0,
) -> Tuple[Optional[int], bytes, bytes, Optional[str]]:
    """
    Executes a subprocess with bounded timeout and guaranteed process reaping.
    If timeout occurs:
    1. Sends SIGTERM (proc.terminate())
    2. Waits up to terminate_grace_period for termination
    3. Escalates to SIGKILL (proc.kill()) if still running
    4. Reaps the process before returning
    Never leaves an unmanaged cleanup subprocess running.
    Returns (returncode, stdout, stderr, error_msg).
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
        # 1. Graceful termination
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        except Exception as te:
            logger.warning("Error calling terminate() on %s: %s", cmd, te)

        # 2. Wait for termination
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=terminate_grace_period)
            return None, stdout, stderr, f"Subprocess '{cmd}' timed out after {timeout}s and was terminated."
        except asyncio.TimeoutError:
            # 3. Escalate to kill
            logger.warning(
                "Subprocess '%s' did not terminate after %0.1fs; escalating to kill...",
                cmd,
                terminate_grace_period,
            )
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            except Exception as ke:
                logger.warning("Error calling kill() on %s: %s", cmd, ke)

            # 4. Reap the killed process
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=kill_grace_period)
            except Exception as reap_err:
                logger.warning("Error reaping killed subprocess %s: %s", cmd, reap_err)
                stdout, stderr = b"", b""

            return None, stdout, stderr, f"Subprocess '{cmd}' timed out after {timeout}s and was killed."
    except Exception as e:
        return None, b"", b"", f"Unexpected error executing '{cmd}': {e}"
