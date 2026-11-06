import asyncio
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple, TYPE_CHECKING
from app.services.sandbox.base import (
    ArtifactCollectionError,
    ArtifactMetadata,
    BaseSandboxAdapter,
    ExecutionOutput,
    ExecutionRequest,
    SandboxCleanupError,
    SandboxConfig,
    SandboxCreationError,
    SandboxExecutionError,
    SandboxTimeoutError,
    UnsupportedSandboxBackendError,
)

logger = logging.getLogger("partproof.sandbox.microsandbox")

if TYPE_CHECKING:
    from app.services.artifacts.manager import ArtifactManager


def _load_microsandbox_sdk():
    """
    Lazy loader for the microsandbox SDK.
    Prevents import crashes on Windows during local development.
    """
    if sys.platform != "linux":
        raise UnsupportedSandboxBackendError(
            f"Microsandbox requires Linux with hardware virtualization (KVM). Detected OS: {sys.platform}"
        )
    try:
        from microsandbox import Sandbox, Network
        return Sandbox, Network
    except ImportError as e:
        raise UnsupportedSandboxBackendError(
            f"Failed to import 'microsandbox' SDK (version 0.7.13 expected): {e}"
        ) from e


class MicrosandboxAdapter(BaseSandboxAdapter):
    """
    Production Linux adapter integrating with Microsandbox 0.7.13 over KVM.
    Creates ephemeral microVMs with dedicated guest kernels, zero networking,
    and automatic context-managed destruction.
    """

    def __init__(self, config: SandboxConfig, artifact_manager: Optional["ArtifactManager"] = None):
        super().__init__(config)
        if artifact_manager is None:
            from app.services.artifacts.manager import ArtifactManager
            self.artifact_manager = ArtifactManager()
        else:
            self.artifact_manager = artifact_manager

        self._sandbox_cm = None
        self._sandbox = None
        self._guest_kernel: Optional[str] = None
        self._provision_attempted: bool = False

    async def create(self) -> str:
        """
        Provisions a real microVM on Vultr Cloud Compute via libkrun/KVM.
        """
        if self._is_created and self._sandbox is not None:
            return self.config.sandbox_id

        self._provision_attempted = True
        Sandbox, Network = _load_microsandbox_sdk()

        # Enforce home and runtime paths
        msb_home = os.environ.get("MSB_HOME", "/home/linuxuser/.microsandbox")
        if not os.path.exists(msb_home):
            user_msb = os.path.expanduser("~/.microsandbox")
            if not os.path.exists(user_msb):
                raise SandboxCreationError(
                    f"Microsandbox runtime directory not found at {msb_home} or {user_msb}",
                    task_id=self.config.task_id,
                    execution_id=self.config.execution_id,
                )

        try:
            self._sandbox_cm = await Sandbox.create(
                self.config.sandbox_id,
                image=self.config.image,
                cpus=self.config.cpus,
                memory=self.config.memory_mb,
                network=Network.none(),
            )
            self._sandbox = await self._sandbox_cm.__aenter__()
            self._is_created = True

            try:
                uname_res = await self._sandbox.exec("uname", ["-r"], timeout=5.0)
                if uname_res and hasattr(uname_res, "stdout_text"):
                    self._guest_kernel = uname_res.stdout_text.strip()
            except Exception:
                self._guest_kernel = "linux-guest-microvm"

            await self._sandbox.exec("mkdir", ["-p", "/workspace/output"], timeout=5.0)

            return self.config.sandbox_id

        except Exception as e:
            self._is_created = False
            raise SandboxCreationError(
                f"Failed to create Microsandbox microVM '{self.config.sandbox_id}': {e}",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            ) from e

    async def execute(self, request: ExecutionRequest) -> ExecutionOutput:
        """
        Transfers source code into guest workspace and executes it inside the microVM.
        The entire operation, including guest source transfer, is strictly bounded by remaining execution time.
        """
        timeout = float(request.timeout_seconds or self.config.timeout_seconds)
        start_time = time.monotonic()
        deadline = start_time + timeout

        if not self._is_created or not self._sandbox:
            prov_remaining = max(0.1, deadline - time.monotonic())
            await asyncio.wait_for(self.create(), timeout=prov_remaining)

        self.artifact_manager.validate_source_code(request.code)

        safe_script_name = self.artifact_manager.sanitize_and_validate_filename(request.filename)
        guest_script_path = f"/workspace/{safe_script_name}"

        # Bound guest source transfer by remaining time budget
        remaining_transfer_time = deadline - time.monotonic()
        if remaining_transfer_time <= 0:
            raise SandboxTimeoutError(
                f"Execution deadline ({timeout}s) expired before guest source transfer could complete.",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        try:
            code_bytes = request.code.encode("utf-8")
            if hasattr(self._sandbox, "fs") and hasattr(self._sandbox.fs, "write"):
                await asyncio.wait_for(
                    self._sandbox.fs.write(guest_script_path, code_bytes),
                    timeout=remaining_transfer_time,
                )
            else:
                write_py = (
                    f"import os\n"
                    f"with open('{guest_script_path}', 'wb') as f:\n"
                    f"    f.write({repr(code_bytes)})\n"
                )
                await asyncio.wait_for(
                    self._sandbox.exec("python3", ["-c", write_py], timeout=float(remaining_transfer_time)),
                    timeout=remaining_transfer_time,
                )
        except asyncio.TimeoutError as te:
            raise SandboxTimeoutError(
                f"Guest source transfer timed out after remaining budget of {remaining_transfer_time:.2f}s",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            ) from te
        except Exception as e:
            if "timeout" in str(e).lower():
                raise SandboxTimeoutError(
                    f"Guest source transfer timed out: {e}",
                    task_id=self.config.task_id,
                    execution_id=self.config.execution_id,
                ) from e
            raise SandboxExecutionError(
                f"Failed to write script payload into guest: {e}",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            ) from e

        # Bound process execution by remaining time budget
        remaining_exec_time = deadline - time.monotonic()
        if remaining_exec_time <= 0:
            raise SandboxTimeoutError(
                f"Execution deadline ({timeout}s) expired before script execution could start.",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        try:
            result = await self._sandbox.exec(
                "python3",
                [guest_script_path],
                timeout=float(remaining_exec_time),
            )
            elapsed = time.monotonic() - start_time

            stdout = getattr(result, "stdout_text", "") or ""
            stderr = getattr(result, "stderr_text", "") or ""
            exit_code = getattr(result, "exit_code", 0)

            return ExecutionOutput(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_seconds=round(elapsed, 4),
                timed_out=False,
                guest_kernel=self._guest_kernel,
            )

        except asyncio.TimeoutError as e:
            elapsed = time.monotonic() - start_time
            raise SandboxTimeoutError(
                f"Sandbox execution exceeded hard deadline of {timeout}s",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            ) from e
        except Exception as e:
            elapsed = time.monotonic() - start_time
            if "timeout" in str(e).lower():
                raise SandboxTimeoutError(
                    f"Process execution timed out: {e}",
                    task_id=self.config.task_id,
                    execution_id=self.config.execution_id,
                ) from e
            raise SandboxExecutionError(
                f"Error executing script in guest: {e}",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            ) from e

    async def collect_artifacts(self, expected_names: List[str], destination_dir: str) -> List[ArtifactMetadata]:
        """
        Extracts permitted artifacts from /workspace/output/ inside the guest to host storage.
        """
        if not expected_names or not self._sandbox:
            return []

        collected: List[ArtifactMetadata] = []
        host_dir = Path(destination_dir)

        for raw_name in expected_names:
            safe_name = self.artifact_manager.sanitize_and_validate_filename(raw_name)
            guest_path = f"/workspace/output/{safe_name}"
            host_dest_path = host_dir / safe_name

            try:
                if hasattr(self._sandbox, "fs") and hasattr(self._sandbox.fs, "copy_to_host"):
                    await self._sandbox.fs.copy_to_host(guest_path, str(host_dest_path))
                else:
                    cat_res = await self._sandbox.exec("cat", [guest_path], timeout=10.0)
                    if cat_res.exit_code == 0:
                        content_bytes = cat_res.stdout_text.encode("utf-8")
                        with open(host_dest_path, "wb") as f:
                            f.write(content_bytes)
                    else:
                        raise ArtifactCollectionError(
                            f"Declared expected artifact '{safe_name}' was not found in guest workspace at '{guest_path}' (cat exited with {cat_res.exit_code})",
                            task_id=self.config.task_id,
                            execution_id=self.config.execution_id,
                        )

                if host_dest_path.exists():
                    meta = self.artifact_manager.register_host_artifact(
                        task_id=self.config.task_id,
                        execution_id=self.config.execution_id,
                        source_path=host_dest_path,
                        filename=safe_name,
                    )
                    collected.append(meta)
                else:
                    raise ArtifactCollectionError(
                        f"Expected artifact '{safe_name}' could not be located on host after transfer",
                        task_id=self.config.task_id,
                        execution_id=self.config.execution_id,
                    )

            except ArtifactCollectionError:
                raise
            except Exception as e:
                raise ArtifactCollectionError(
                    f"Failed to extract declared artifact '{safe_name}' from guest: {e}",
                    task_id=self.config.task_id,
                    execution_id=self.config.execution_id,
                ) from e

        self.artifact_manager.validate_artifact_collection_limits(collected)
        return collected

    async def _cli_destroy_and_verify(self) -> Tuple[bool, str]:
        """
        Invokes 'msb rm --force <sandbox_id>' and independently verifies absence via 'msb ls'.
        Returns (is_verified, detail_message).
        """
        msb_bin = os.environ.get("MSB_BIN", "/home/linuxuser/.local/bin/msb")
        if not os.path.exists(msb_bin):
            resolved = shutil.which("msb")
            if resolved:
                msb_bin = resolved
            else:
                return False, f"msb CLI binary not found at '{msb_bin}' or in PATH; cannot prove destruction."

        sandbox_id = self.config.sandbox_id

        # Step 1: Force remove sandbox and its stored resources via msb rm --force
        try:
            rm_proc = await asyncio.create_subprocess_exec(
                msb_bin,
                "rm",
                "--force",
                sandbox_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            rm_out, rm_err = await asyncio.wait_for(rm_proc.communicate(), timeout=15.0)
            if rm_proc.returncode != 0:
                err_text = rm_err.decode("utf-8", errors="replace").strip()
                logger.warning("msb rm --force for %s exited with %d: %s", sandbox_id, rm_proc.returncode, err_text)
                return False, f"msb rm --force failed with exit code {rm_proc.returncode}: {err_text}"
        except asyncio.TimeoutError:
            logger.warning("msb rm --force timed out after 15s for %s", sandbox_id)
            return False, f"msb rm --force timed out after 15.0s for '{sandbox_id}'"
        except Exception as e:
            logger.warning("Error invoking msb rm --force for %s: %s", sandbox_id, e)
            return False, f"msb rm --force failed with error: {e}"

        # Step 2: Independently verify complete absence via msb ls
        try:
            ls_proc = await asyncio.create_subprocess_exec(
                msb_bin,
                "ls",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            ls_out, ls_err = await asyncio.wait_for(ls_proc.communicate(), timeout=10.0)
            if ls_proc.returncode != 0:
                err_text = ls_err.decode("utf-8", errors="replace").strip()
                return False, f"msb ls verification failed with exit code {ls_proc.returncode}: {err_text}"

            ls_text = ls_out.decode("utf-8", errors="replace")
            if sandbox_id in ls_text:
                return False, f"Sandbox microVM '{sandbox_id}' still detected present in msb ls: {ls_text.strip()}"

            return True, f"MicroVM '{sandbox_id}' confirmed absent in msb ls."
        except asyncio.TimeoutError:
            return False, f"msb ls verification timed out after 10.0s for '{sandbox_id}'"
        except Exception as e:
            return False, f"Failed to execute msb ls absence verification: {e}"

    async def destroy(self) -> str:
        """
        Stops and destroys the microVM, confirming zero resources remain.
        If provisioning timed out or failed before _sandbox_cm was assigned,
        SDK cleanup cannot establish destruction, so fallback to 'msb rm --force'
        with independent 'msb ls' absence verification is enforced.
        """
        if self._is_destroyed:
            return "verified_destroyed"

        cleanup_error = None
        sdk_cleaned = False

        if self._sandbox_cm is not None:
            try:
                await self._sandbox_cm.__aexit__(None, None, None)
                sdk_cleaned = True
            except Exception as e:
                cleanup_error = e

        self._sandbox = None
        self._sandbox_cm = None

        # If SDK context-managed cleanup succeeded cleanly, mark destroyed
        if sdk_cleaned and not cleanup_error:
            self._is_destroyed = True
            return "verified_destroyed"

        # If provisioning was attempted (or SDK cleanup failed / could not establish destruction),
        # we MUST NOT report verified_destroyed without proof.
        # Enforce CLI fallback: 'msb rm --force <sandbox_id>' and independently verify absence via 'msb ls'.
        if self._provision_attempted or cleanup_error is not None:
            cli_verified, cli_reason = await self._cli_destroy_and_verify()
            if cli_verified:
                self._is_destroyed = True
                return "verified_destroyed"
            else:
                err_msg = (
                    f"MicroVM destruction could not be verified for '{self.config.sandbox_id}'. "
                    f"SDK cleanup error: {cleanup_error}. CLI verification error: {cli_reason}"
                )
                logger.error(err_msg)
                raise SandboxCleanupError(
                    err_msg,
                    task_id=self.config.task_id,
                    execution_id=self.config.execution_id,
                )

        # If provisioning was never attempted, no microVM resources were allocated
        self._is_destroyed = True
        return "verified_destroyed"
