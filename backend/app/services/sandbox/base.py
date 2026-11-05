from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Exception Hierarchy
# ============================================================================

class SandboxError(Exception):
    """Base exception for all sandbox operations."""
    def __init__(self, message: str, task_id: Optional[str] = None, execution_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.task_id = task_id
        self.execution_id = execution_id


class SandboxCreationError(SandboxError):
    """Raised when sandbox provisioning or boot fails."""
    pass


class SandboxExecutionError(SandboxError):
    """Raised when code execution fails inside the guest."""
    pass


class SandboxTimeoutError(SandboxError):
    """Raised when process execution exceeds the configured deadline."""
    pass


class ArtifactCollectionError(SandboxError):
    """Raised when artifact extraction or validation fails."""
    pass


class SandboxCleanupError(SandboxError):
    """Raised when sandbox destruction or resource cleanup fails."""
    pass


class UnsupportedSandboxBackendError(SandboxError):
    """Raised when an unknown or unavailable sandbox backend is requested."""
    pass


class PolicyViolationError(SandboxError):
    """Raised when execution parameters violate security policies."""
    pass


# ============================================================================
# Typed Models
# ============================================================================

class SandboxConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    sandbox_id: str = Field(description="Unique identifier for the sandbox microVM")
    task_id: str = Field(description="Parent task identifier")
    execution_id: str = Field(description="Execution run identifier")
    image: str = Field(default="python:3.12-slim", description="OCI container/microVM base image")
    cpus: int = Field(default=1, ge=1, le=2, description="vCPU allocation limit")
    memory_mb: int = Field(default=512, ge=128, le=1024, description="Memory limit in MB")
    network: str = Field(default="none", description="Network isolation mode: strictly 'none' by default")
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0, description="Hard deadline for execution")


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(description="Python source code to execute inside the isolated sandbox")
    filename: str = Field(default="audit_task.py", description="Script filename inside guest workspace")
    expected_artifacts: List[str] = Field(default_factory=list, description="List of expected output filenames, e.g. ['report.csv']")
    timeout_seconds: Optional[float] = Field(default=None, description="Optional override within config bounds")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="Non-secret environment variables only")


class ExecutionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    stdout: str = Field(default="", description="Standard output stream")
    stderr: str = Field(default="", description="Standard error stream")
    exit_code: int = Field(description="Process exit code (0 for success)")
    duration_seconds: float = Field(description="Actual elapsed execution time in seconds")
    timed_out: bool = Field(default=False, description="Whether execution was terminated due to timeout")
    guest_kernel: Optional[str] = Field(default=None, description="Reported guest kernel version")


class ArtifactMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str = Field(description="Validated safe filename")
    storage_path: str = Field(description="Absolute path on host storage")
    relative_path: str = Field(description="Relative storage path")
    mime_type: str = Field(default="text/plain", description="MIME content type")
    size_bytes: int = Field(description="File size in bytes")
    sha256: str = Field(description="SHA-256 cryptographic checksum")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    execution_id: str
    sandbox_id: str
    status: str = Field(description="'succeeded' | 'failed' | 'timed_out'")
    output: ExecutionOutput
    artifacts: List[ArtifactMetadata] = Field(default_factory=list)
    cleanup_status: str = Field(default="pending", description="'verified_destroyed' | 'failed' | 'pending'")
    execution_mode: str = Field(description="'mock' | 'microsandbox'")
    error_message: Optional[str] = None


# ============================================================================
# Abstract Sandbox Adapter Interface
# ============================================================================

class BaseSandboxAdapter(ABC):
    """
    Abstract interface for sandbox execution providers.
    Both the local MockSandboxAdapter and the Linux MicrosandboxAdapter implement this interface.
    """

    def __init__(self, config: SandboxConfig):
        self.config = config
        self._is_created: bool = False
        self._is_destroyed: bool = False

    @abstractmethod
    async def create(self) -> str:
        """
        Provisions and starts the isolated sandbox environment.
        Returns the confirmed sandbox_id.
        """
        pass

    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionOutput:
        """
        Transfers source code into the guest and executes it under isolated boundaries.
        Returns the captured execution output (stdout, stderr, exit_code, duration).
        """
        pass

    @abstractmethod
    async def collect_artifacts(self, expected_names: List[str], destination_dir: str) -> List[ArtifactMetadata]:
        """
        Extracts designated output files from the guest, verifies path safety,
        and saves them into host storage.
        """
        pass

    @abstractmethod
    async def destroy(self) -> str:
        """
        Terminates the sandbox, destroys guest storage, and confirms cleanup.
        Returns 'verified_destroyed' or raises SandboxCleanupError.
        """
        pass

    async def __aenter__(self):
        await self.create()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.destroy()
        except Exception:
            # Destruction must attempt cleanup even if an exception occurred
            if not self._is_destroyed:
                try:
                    await self.destroy()
                except Exception:
                    pass
            raise
