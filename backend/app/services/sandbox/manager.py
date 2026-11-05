import asyncio
import logging
import uuid
from typing import Dict, List, Optional, TYPE_CHECKING
from app.core.config import settings
from app.services.sandbox.base import (
    BaseSandboxAdapter,
    ExecutionOutput,
    ExecutionRequest,
    ExecutionResult,
    PolicyViolationError,
    SandboxConfig,
    SandboxTimeoutError,
    UnsupportedSandboxBackendError,
)
from app.services.sandbox.mock_adapter import MockSandboxAdapter
from app.services.sandbox.microsandbox_adapter import MicrosandboxAdapter

if TYPE_CHECKING:
    from app.services.artifacts.manager import ArtifactManager

logger = logging.getLogger("partproof.sandbox")


class SandboxManager:
    """
    Central orchestration service for sandbox lifecycles.
    Enforces deterministic backend security policies, limits concurrency,
    and isolates execution from the host.
    """

    def __init__(
        self,
        backend_name: Optional[str] = None,
        artifact_manager: Optional["ArtifactManager"] = None,
    ):
        self.backend_name = backend_name or settings.SANDBOX_BACKEND
        if artifact_manager is None:
            from app.services.artifacts.manager import ArtifactManager
            self.artifact_manager = ArtifactManager()
        else:
            self.artifact_manager = artifact_manager

        # Single-worker concurrency gate for the 2-vCPU Vultr host
        self._concurrency_lock = asyncio.Semaphore(settings.SANDBOX_MAX_CONCURRENT)
        self._active_sandboxes: Dict[str, SandboxConfig] = {}

    def get_adapter(self, config: SandboxConfig) -> BaseSandboxAdapter:
        """
        Factory method returning the configured sandbox adapter.
        Hard invariant: Production environment MUST NOT use mock adapter.
        """
        if settings.PARTPROOF_ENV == "production" and self.backend_name == "mock":
            raise PolicyViolationError(
                "CRITICAL SECURITY REJECTION: Mock sandbox backend is prohibited in production mode."
            )

        if self.backend_name == "mock":
            return MockSandboxAdapter(config, self.artifact_manager)
        elif self.backend_name == "microsandbox":
            return MicrosandboxAdapter(config, self.artifact_manager)
        else:
            raise UnsupportedSandboxBackendError(f"Unsupported sandbox backend: '{self.backend_name}'")

    def validate_policy(self, config: SandboxConfig, request: ExecutionRequest) -> None:
        """
        Deterministic policy gatekeeper. Rejects requests exceeding system constraints.
        """
        if config.image not in settings.SANDBOX_ALLOWED_IMAGES:
            raise PolicyViolationError(
                f"Requested image '{config.image}' is not in allowlisted images: {settings.SANDBOX_ALLOWED_IMAGES}"
            )

        if config.cpus > settings.SANDBOX_MAX_CPUS:
            raise PolicyViolationError(
                f"Requested CPUs ({config.cpus}) exceeds maximum allowed ({settings.SANDBOX_MAX_CPUS})"
            )

        if config.memory_mb > settings.SANDBOX_MAX_MEMORY_MB:
            raise PolicyViolationError(
                f"Requested memory ({config.memory_mb} MB) exceeds maximum allowed ({settings.SANDBOX_MAX_MEMORY_MB} MB)"
            )

        if config.timeout_seconds > settings.SANDBOX_MAX_TIMEOUT_SECONDS:
            raise PolicyViolationError(
                f"Requested timeout ({config.timeout_seconds}s) exceeds maximum allowed ({settings.SANDBOX_MAX_TIMEOUT_SECONDS}s)"
            )

        if config.network != "none":
            raise PolicyViolationError(
                f"Network mode '{config.network}' is rejected. Only 'none' is permitted for zero blast radius."
            )

        self.artifact_manager.validate_source_code(request.code)

    async def execute_task(
        self,
        task_id: str,
        execution_id: str,
        code: str,
        expected_artifacts: Optional[List[str]] = None,
        image: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        cpus: Optional[int] = None,
        memory_mb: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Executes a task under strict isolation with guaranteed cleanup.
        """
        sandbox_id = f"partproof-{task_id[:8]}-{execution_id[:8]}-{uuid.uuid4().hex[:6]}"
        
        config = SandboxConfig(
            sandbox_id=sandbox_id,
            task_id=task_id,
            execution_id=execution_id,
            image=image or settings.SANDBOX_DEFAULT_IMAGE,
            cpus=cpus or settings.SANDBOX_DEFAULT_CPUS,
            memory_mb=memory_mb or settings.SANDBOX_DEFAULT_MEMORY_MB,
            network="none",
            timeout_seconds=timeout_seconds or float(settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS),
        )

        request = ExecutionRequest(
            code=code,
            filename="audit_task.py",
            expected_artifacts=expected_artifacts or [],
            timeout_seconds=config.timeout_seconds,
        )

        # 1. Deterministic Policy Validation
        self.validate_policy(config, request)

        # 2. Acquire concurrency slot (bounded concurrency)
        async with self._concurrency_lock:
            self._active_sandboxes[sandbox_id] = config
            adapter = self.get_adapter(config)
            dest_dir = self.artifact_manager.get_execution_storage_dir(task_id, execution_id)

            logger.info(
                f"Starting sandbox execution: sandbox_id={sandbox_id} task_id={task_id} "
                f"execution_id={execution_id} backend={self.backend_name}"
            )

            status = "failed"
            cleanup_status = "pending"
            output = None
            artifacts = []
            error_msg = None

            try:
                # 3. Provision and enter context-managed sandbox
                async with adapter:
                    try:
                        # 4. Execute code inside guest
                        output = await adapter.execute(request)
                        if output.exit_code == 0:
                            status = "succeeded"
                        else:
                            status = "failed"
                    except SandboxTimeoutError as te:
                        logger.warning(f"Sandbox execution timed out: {te}")
                        status = "timed_out"
                        error_msg = str(te)
                        output = ExecutionOutput(
                            stdout="",
                            stderr=f"Process terminated: {te.message}\n",
                            exit_code=124,
                            duration_seconds=config.timeout_seconds,
                            timed_out=True,
                            guest_kernel=getattr(adapter, "_guest_kernel", None),
                        )
                    except Exception as exec_err:
                        logger.error(f"Sandbox execution error: {exec_err}", exc_info=True)
                        status = "failed"
                        error_msg = str(exec_err)
                        output = ExecutionOutput(
                            stdout="",
                            stderr=f"Execution failure: {str(exec_err)}\n",
                            exit_code=1,
                            duration_seconds=0.0,
                            timed_out=False,
                            guest_kernel=getattr(adapter, "_guest_kernel", None),
                        )

                    # 5. Extract output artifacts if requested and execution succeeded
                    if request.expected_artifacts and status == "succeeded":
                        try:
                            artifacts = await adapter.collect_artifacts(
                                request.expected_artifacts,
                                str(dest_dir),
                            )
                        except Exception as art_err:
                            logger.error(f"Artifact collection error: {art_err}", exc_info=True)

                # Context exit confirms microVM destruction
                cleanup_status = "verified_destroyed"

            except Exception as outer_err:
                cleanup_status = "failed"
                logger.error(f"Sandbox lifecycle failed: {outer_err}", exc_info=True)
                if not error_msg:
                    error_msg = str(outer_err)

            finally:
                self._active_sandboxes.pop(sandbox_id, None)

            if output is None:
                output = ExecutionOutput(
                    stdout="",
                    stderr=error_msg or "Unknown error",
                    exit_code=1,
                    duration_seconds=0.0,
                    timed_out=(status == "timed_out"),
                )

            return ExecutionResult(
                task_id=task_id,
                execution_id=execution_id,
                sandbox_id=sandbox_id,
                status=status,
                output=output,
                artifacts=artifacts,
                cleanup_status=cleanup_status,
                execution_mode=self.backend_name,
                error_message=error_msg,
            )

    @property
    def active_sandbox_count(self) -> int:
        return len(self._active_sandboxes)
