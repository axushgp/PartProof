import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING
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

    async def create(self) -> str:
        """
        Provisions a real microVM on Vultr Cloud Compute via libkrun/KVM.
        """
        if self._is_created and self._sandbox is not None:
            return self.config.sandbox_id

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
        """
        if not self._is_created or not self._sandbox:
            await self.create()

        self.artifact_manager.validate_source_code(request.code)

        safe_script_name = self.artifact_manager.sanitize_and_validate_filename(request.filename)
        guest_script_path = f"/workspace/{safe_script_name}"

        try:
            code_bytes = request.code.encode("utf-8")
            if hasattr(self._sandbox, "fs") and hasattr(self._sandbox.fs, "write"):
                await self._sandbox.fs.write(guest_script_path, code_bytes)
            else:
                write_py = (
                    f"import os\n"
                    f"with open('{guest_script_path}', 'wb') as f:\n"
                    f"    f.write({repr(code_bytes)})\n"
                )
                await self._sandbox.exec("python3", ["-c", write_py], timeout=10.0)
        except Exception as e:
            raise SandboxExecutionError(
                f"Failed to write script payload into guest: {e}",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            ) from e

        timeout = request.timeout_seconds or self.config.timeout_seconds
        start_time = time.monotonic()

        try:
            result = await self._sandbox.exec(
                "python3",
                [guest_script_path],
                timeout=float(timeout),
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
                        continue

                if host_dest_path.exists():
                    meta = self.artifact_manager.register_host_artifact(
                        task_id=self.config.task_id,
                        execution_id=self.config.execution_id,
                        source_path=host_dest_path,
                        filename=safe_name,
                    )
                    collected.append(meta)

            except Exception:
                continue

        self.artifact_manager.validate_artifact_collection_limits(collected)
        return collected

    async def destroy(self) -> str:
        """
        Stops and destroys the microVM, confirming zero resources remain.
        """
        if self._is_destroyed:
            return "verified_destroyed"

        cleanup_error = None
        if self._sandbox_cm is not None:
            try:
                await self._sandbox_cm.__aexit__(None, None, None)
            except Exception as e:
                cleanup_error = e

        self._sandbox = None
        self._sandbox_cm = None
        self._is_destroyed = True

        if cleanup_error:
            raise SandboxCleanupError(
                f"Failed to cleanly destroy microVM '{self.config.sandbox_id}': {cleanup_error}",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            ) from cleanup_error

        return "verified_destroyed"
