import asyncio
import time
from typing import List, Optional, TYPE_CHECKING
from app.services.sandbox.base import (
    ArtifactMetadata,
    BaseSandboxAdapter,
    ExecutionOutput,
    ExecutionRequest,
    SandboxCleanupError,
    SandboxConfig,
    SandboxTimeoutError,
)

if TYPE_CHECKING:
    from app.services.artifacts.manager import ArtifactManager


class MockSandboxAdapter(BaseSandboxAdapter):
    """
    Deterministic simulated sandbox adapter for local Windows/Mac development and test suites.
    CRITICAL SAFETY GUARANTEE: Never executes arbitrary user code on the host OS.
    Produces deterministic simulated outputs marked explicitly with execution_mode='mock'.
    """

    def __init__(self, config: SandboxConfig, artifact_manager: Optional["ArtifactManager"] = None):
        super().__init__(config)
        if artifact_manager is None:
            from app.services.artifacts.manager import ArtifactManager
            self.artifact_manager = ArtifactManager()
        else:
            self.artifact_manager = artifact_manager
            
        self.simulated_guest_kernel = "simulated-kernel-6.12.113-mock"
        self._last_request: Optional[ExecutionRequest] = None

    async def create(self) -> str:
        """Simulates microVM provisioning."""
        if self._is_created:
            return self.config.sandbox_id
        
        await asyncio.sleep(0.01)
        self._is_created = True
        return self.config.sandbox_id

    async def execute(self, request: ExecutionRequest) -> ExecutionOutput:
        """
        Simulates code execution without running any untrusted code on the host.
        Recognizes explicit deterministic test markers inside the code string.
        """
        if not self._is_created:
            await self.create()

        self._last_request = request
        self.artifact_manager.validate_source_code(request.code)

        start_time = time.monotonic()

        # 1. Deterministic simulation: Timeout simulation
        if "SIMULATE_TIMEOUT" in request.code or (request.timeout_seconds and request.timeout_seconds < 0.05):
            elapsed = 0.05
            raise SandboxTimeoutError(
                f"Simulated execution deadline ({self.config.timeout_seconds}s) exceeded.",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        # 2. Deterministic simulation: Failure simulation
        if (
            "SIMULATE_ERROR" in request.code
            or "raise " in request.code
            or "sys.exit(1)" in request.code
            or "def invalid syntax" in request.code
        ):
            await asyncio.sleep(0.02)
            elapsed = time.monotonic() - start_time
            return ExecutionOutput(
                stdout="[MOCK SANDBOX] Initializing isolated execution environment...\n[MOCK SANDBOX] Executing task script...",
                stderr="Traceback (most recent call last):\n  File 'audit_task.py', line 8, in <module>\nValueError: Simulated error trigger detected inside mock adapter\n",
                exit_code=1,
                duration_seconds=round(elapsed, 4),
                timed_out=False,
                guest_kernel=self.simulated_guest_kernel,
            )

        # 3. Standard successful deterministic execution simulation
        await asyncio.sleep(0.02)
        elapsed = time.monotonic() - start_time

        stdout_text = (
            f"[MOCK SANDBOX] Running in deterministic simulated environment (execution_mode=mock)\n"
            f"[MOCK SANDBOX] Sandbox ID: {self.config.sandbox_id}\n"
            f"[MOCK SANDBOX] Guest Kernel: {self.simulated_guest_kernel}\n"
            f"[MOCK SANDBOX] Resource Bounds: {self.config.cpus} vCPU, {self.config.memory_mb} MB RAM\n"
            f"[MOCK SANDBOX] Network: {self.config.network}\n"
            f"[MOCK SANDBOX] Execution completed with status 0."
        )

        return ExecutionOutput(
            stdout=stdout_text,
            stderr="",
            exit_code=0,
            duration_seconds=round(elapsed, 4),
            timed_out=False,
            guest_kernel=self.simulated_guest_kernel,
        )

    async def collect_artifacts(self, expected_names: List[str], destination_dir: str) -> List[ArtifactMetadata]:
        """
        Generates simulated output artifacts corresponding to expected filenames.
        """
        collected: List[ArtifactMetadata] = []
        if not expected_names:
            return collected

        for raw_name in expected_names:
            safe_name = self.artifact_manager.sanitize_and_validate_filename(raw_name)
            
            if safe_name.endswith(".csv"):
                content = (
                    "line_item,part_number,description,qty,unit_cost,extended_cost,discrepancy\n"
                    "1,P-8801,Hex Cap Screw M8x30,500,0.45,225.00,0.00\n"
                    "2,P-8802,Structural Flange Bracket,100,18.50,1850.00,12.50\n"
                    "3,P-8803,EPDM Gasket Seal,200,3.20,640.00,0.00\n"
                ).encode("utf-8")
            elif safe_name.endswith(".json"):
                content = (
                    '{"audit_id": "audit-mock-01", "total_cost": 2715.00, "verified": true, "variance": 12.50}\n'
                ).encode("utf-8")
            else:
                content = f"PartProof Audit Log - Output for {safe_name}\nStatus: Verified\n".encode("utf-8")

            metadata = self.artifact_manager.store_artifact_from_bytes(
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
                filename=safe_name,
                data=content,
            )
            collected.append(metadata)

        self.artifact_manager.validate_artifact_collection_limits(collected)
        return collected

    async def destroy(self) -> str:
        """Simulates microVM destruction and verification."""
        if not self._is_created:
            return "verified_destroyed"

        if "SIMULATE_CLEANUP_FAILURE" in getattr(self._last_request, "code", ""):
            raise SandboxCleanupError(
                "Simulated failure during sandbox cleanup verification",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        self._is_destroyed = True
        return "verified_destroyed"
