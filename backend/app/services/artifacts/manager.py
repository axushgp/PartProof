import hashlib
import mimetypes
import os
import re
from pathlib import Path
from typing import List, Optional
from app.core.config import settings
from app.services.sandbox.base import (
    ArtifactCollectionError,
    ArtifactMetadata,
    PolicyViolationError,
)

# Allow only safe, alphanumeric, dot, underscore, and hyphen characters in filenames
SAFE_FILENAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


class ArtifactManager:
    """
    Manages safe artifact validation, storage, and cryptographic hashing.
    Enforces strict path-traversal prevention, file size bounds, and non-symlink checks.
    """

    def __init__(
        self,
        base_storage_dir: Optional[str] = None,
        max_artifacts: Optional[int] = None,
        max_file_size: Optional[int] = None,
        max_total_size: Optional[int] = None,
        max_source_size: Optional[int] = None,
    ):
        self.base_storage_dir = Path(base_storage_dir or settings.ARTIFACT_STORAGE_DIR).resolve()
        self.max_artifacts = max_artifacts or settings.MAX_ARTIFACTS_PER_EXECUTION
        self.max_file_size = max_file_size or settings.MAX_ARTIFACT_SIZE_BYTES
        self.max_total_size = max_total_size or settings.MAX_TOTAL_ARTIFACT_BYTES
        self.max_source_size = max_source_size or settings.MAX_SOURCE_INPUT_BYTES

    def get_execution_storage_dir(self, task_id: str, execution_id: str) -> Path:
        """
        Creates and returns a deterministic, isolated storage directory for a task execution.
        """
        # Validate that task_id and execution_id are safe identifiers
        self.validate_identifier(task_id, "task_id")
        self.validate_identifier(execution_id, "execution_id")

        target_dir = (self.base_storage_dir / task_id / execution_id).resolve()
        
        # Verify target_dir is strictly within base_storage_dir
        if not str(target_dir).startswith(str(self.base_storage_dir)):
            raise ArtifactCollectionError(
                "Directory traversal detected in artifact destination path",
                task_id=task_id,
                execution_id=execution_id,
            )
        
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def validate_identifier(self, identifier: str, field_name: str) -> None:
        """Ensures identifiers contain only safe characters."""
        if not identifier or not SAFE_FILENAME_REGEX.match(identifier):
            raise ArtifactCollectionError(f"Invalid {field_name}: contains unsafe characters: '{identifier}'")

    def validate_source_code(self, code: str) -> None:
        """
        Validates source code input size and character constraints before dispatch.
        """
        if not code or not code.strip():
            raise PolicyViolationError("Source code cannot be empty.")
        
        code_bytes = code.encode("utf-8")
        if len(code_bytes) > self.max_source_size:
            raise PolicyViolationError(
                f"Source code exceeds maximum allowed size ({len(code_bytes)} bytes > {self.max_source_size} bytes limit)."
            )
        
        if "\x00" in code:
            raise PolicyViolationError("Source code contains illegal null bytes.")

    def sanitize_and_validate_filename(self, filename: str) -> str:
        """
        Validates that a filename does not contain path traversal, slashes, or special characters.
        """
        if not filename or not filename.strip():
            raise ArtifactCollectionError("Artifact filename cannot be empty.")
        
        cleaned = filename.strip()
        
        # Explicit checks for path separators and traversal patterns
        if "/" in cleaned or "\\" in cleaned or ".." in cleaned or "\x00" in cleaned:
            raise ArtifactCollectionError(f"Path traversal or directory separator detected in filename: '{filename}'")
        
        # Reject absolute paths (POSIX or Windows drive letter)
        if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
            raise ArtifactCollectionError(f"Absolute paths not permitted for artifacts: '{filename}'")
        
        # Must match safe character set
        if not SAFE_FILENAME_REGEX.match(cleaned):
            raise ArtifactCollectionError(f"Filename contains illegal characters: '{filename}'")
        
        # Disallow hidden dotfiles like .bashrc or .env
        if cleaned.startswith("."):
            raise ArtifactCollectionError(f"Hidden dotfiles are not permitted as artifacts: '{filename}'")
        
        return cleaned

    def compute_sha256(self, file_path: Path) -> str:
        """Computes SHA-256 hash using streaming chunks."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def store_artifact_from_bytes(
        self,
        task_id: str,
        execution_id: str,
        filename: str,
        data: bytes,
    ) -> ArtifactMetadata:
        """
        Stores bytes as an artifact with full safety checks.
        """
        safe_name = self.sanitize_and_validate_filename(filename)
        size_bytes = len(data)

        if size_bytes > self.max_file_size:
            raise ArtifactCollectionError(
                f"Artifact '{safe_name}' size {size_bytes} exceeds limit of {self.max_file_size} bytes."
            )

        storage_dir = self.get_execution_storage_dir(task_id, execution_id)
        target_file = (storage_dir / safe_name).resolve()

        # Write data
        with open(target_file, "wb") as f:
            f.write(data)

        sha256_hash = hashlib.sha256(data).hexdigest()
        mime_type, _ = mimetypes.guess_type(safe_name)

        relative_path = f"{task_id}/{execution_id}/{safe_name}"

        return ArtifactMetadata(
            filename=safe_name,
            storage_path=str(target_file),
            relative_path=relative_path,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=size_bytes,
            sha256=sha256_hash,
        )

    def register_host_artifact(
        self,
        task_id: str,
        execution_id: str,
        source_path: Path,
        filename: Optional[str] = None,
    ) -> ArtifactMetadata:
        """
        Validates an existing host file (e.g. copied from microVM), checks constraints,
        and returns validated ArtifactMetadata.
        """
        target_name = self.sanitize_and_validate_filename(filename or source_path.name)
        
        # Verify source file exists and is a regular file (not symlink or directory)
        if not source_path.exists():
            raise ArtifactCollectionError(f"Artifact source file '{source_path}' does not exist.")
        
        if source_path.is_symlink():
            raise ArtifactCollectionError(f"Security violation: Artifact '{target_name}' is a symlink.")
        
        if not source_path.is_file():
            raise ArtifactCollectionError(f"Artifact '{target_name}' is not a regular file.")

        size_bytes = source_path.stat().st_size
        if size_bytes > self.max_file_size:
            raise ArtifactCollectionError(
                f"Artifact '{target_name}' size {size_bytes} exceeds maximum allowed {self.max_file_size} bytes."
            )

        sha256_hash = self.compute_sha256(source_path)
        mime_type, _ = mimetypes.guess_type(target_name)
        relative_path = f"{task_id}/{execution_id}/{target_name}"

        return ArtifactMetadata(
            filename=target_name,
            storage_path=str(source_path.resolve()),
            relative_path=relative_path,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=size_bytes,
            sha256=sha256_hash,
        )

    def validate_artifact_collection_limits(self, artifacts: List[ArtifactMetadata]) -> None:
        """
        Enforces batch constraints on collected artifacts.
        """
        if len(artifacts) > self.max_artifacts:
            raise ArtifactCollectionError(
                f"Artifact count {len(artifacts)} exceeds maximum allowed {self.max_artifacts}."
            )

        total_bytes = sum(a.size_bytes for a in artifacts)
        if total_bytes > self.max_total_size:
            raise ArtifactCollectionError(
                f"Total artifact size {total_bytes} bytes exceeds maximum allowed {self.max_total_size} bytes."
            )

        # Ensure no duplicate filenames in the batch
        names = [a.filename for a in artifacts]
        if len(names) != len(set(names)):
            raise ArtifactCollectionError("Duplicate filenames detected in collected artifacts batch.")
