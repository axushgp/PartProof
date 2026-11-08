import hashlib
import mimetypes
import os
import re
import stat
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import quote
from app.core.config import settings
from app.services.sandbox.base import (
    ArtifactCollectionError,
    ArtifactMetadata,
    PolicyViolationError,
)

# Allow only safe, alphanumeric, dot, underscore, and hyphen characters in filenames
SAFE_FILENAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


class ArtifactNotFoundError(ArtifactCollectionError):
    """Raised when an artifact file does not exist on disk."""
    pass


class ArtifactSecurityError(ArtifactCollectionError):
    """Raised when path traversal, symlink, or non-regular file is encountered."""
    pass


class ArtifactIntegrityError(ArtifactCollectionError):
    """Raised when file size or SHA-256 digest fails verification."""
    pass


def build_content_disposition(filename: str) -> str:
    """
    Builds RFC 6266 compliant Content-Disposition attachment header.
    Includes both safe ASCII filename fallback and UTF-8 encoded filename*.
    Prevents header injection by stripping carriage returns and newlines.
    """
    clean_name = filename.replace("\r", "").replace("\n", "").replace('"', "").strip()
    ascii_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", clean_name) or "artifact.bin"
    encoded_name = quote(clean_name, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'


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
        self._base_storage_dir = Path(base_storage_dir).resolve() if base_storage_dir else None
        self.max_artifacts = max_artifacts or settings.MAX_ARTIFACTS_PER_EXECUTION
        self.max_file_size = max_file_size or settings.MAX_ARTIFACT_SIZE_BYTES
        self.max_total_size = max_total_size or settings.MAX_TOTAL_ARTIFACT_BYTES
        self.max_source_size = max_source_size or settings.MAX_SOURCE_INPUT_BYTES

    @property
    def base_storage_dir(self) -> Path:
        if self._base_storage_dir is not None:
            return self._base_storage_dir
        return Path(settings.ARTIFACT_STORAGE_DIR).resolve()

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

    def resolve_artifact_path(
        self,
        task_id: str,
        execution_id: Optional[str],
        filename: str,
        storage_key: Optional[str] = None,
    ) -> Path:
        """
        Safely resolves an artifact file path inside base_storage_dir.
        Enforces strict boundary containment, symlink rejection, and safe fallback.
        Supports both existing absolute paths and relative storage_keys.
        """
        base_dir = self.base_storage_dir.resolve()

        # 1. If storage_key is supplied, evaluate candidate safely
        if storage_key and storage_key.strip():
            raw_key = storage_key.strip()
            # Explicitly reject directory traversal tokens in relative keys
            if ".." in raw_key:
                raise ArtifactSecurityError(f"Directory traversal detected in storage_key: '{raw_key}'")

            candidate = Path(raw_key)
            if candidate.is_absolute():
                try:
                    resolved_cand = candidate.resolve()
                    if resolved_cand.is_relative_to(base_dir) and resolved_cand.exists():
                        if os.path.islink(resolved_cand) or resolved_cand.is_symlink():
                            raise ArtifactSecurityError("Security violation: Artifact target is a symlink")
                        return resolved_cand
                except (ValueError, OSError):
                    pass
            else:
                try:
                    resolved_cand = (base_dir / candidate).resolve()
                    if resolved_cand.is_relative_to(base_dir) and resolved_cand.exists():
                        if os.path.islink(resolved_cand) or resolved_cand.is_symlink():
                            raise ArtifactSecurityError("Security violation: Artifact target is a symlink")
                        return resolved_cand
                except (ValueError, OSError):
                    pass

        # 2. Canonical DB fallback: base_storage_dir / safe_task_id / [safe_execution_id] / safe_filename
        self.validate_identifier(task_id, "task_id")
        safe_filename = self.sanitize_and_validate_filename(filename)
        if execution_id:
            self.validate_identifier(execution_id, "execution_id")
            canonical_path = (base_dir / task_id / execution_id / safe_filename).resolve()
        else:
            canonical_path = (base_dir / task_id / safe_filename).resolve()

        if not canonical_path.is_relative_to(base_dir):
            raise ArtifactSecurityError("Directory traversal detected in canonical artifact path")

        if os.path.islink(canonical_path) or canonical_path.is_symlink():
            raise ArtifactSecurityError("Security violation: Artifact canonical file is a symlink")

        if not canonical_path.exists():
            # If an absolute or custom storage_key was given that resolved outside base_dir, report security violation
            if storage_key and storage_key.strip():
                try:
                    cand = Path(storage_key.strip()).resolve()
                    if not cand.is_relative_to(base_dir):
                        raise ArtifactSecurityError(
                            "Security violation: storage_key points outside artifact storage directory"
                        )
                except (ValueError, OSError):
                    pass
            raise ArtifactNotFoundError("Artifact file does not exist on storage")

        return canonical_path

    def open_and_verify_artifact(
        self,
        task_id: str,
        execution_id: Optional[str],
        filename: str,
        expected_size: int,
        expected_sha256: str,
        storage_key: Optional[str] = None,
    ) -> Tuple[int, Path]:
        """
        Resolves the artifact path, opens a secure file descriptor (O_NOFOLLOW),
        validates regular file status, checks size and computes streaming SHA-256
        against expected values.
        Rewinds the descriptor to offset 0 and returns (fd, resolved_path).
        Caller is responsible for closing fd (e.g. in StreamingResponse generator).
        """
        path = self.resolve_artifact_path(
            task_id=task_id,
            execution_id=execution_id,
            filename=filename,
            storage_key=storage_key,
        )

        if path.is_dir() or not path.is_file():
            raise ArtifactSecurityError("Security violation: Artifact target is not a regular file")

        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        try:
            fd = os.open(path, flags)
        except OSError as e:
            if hasattr(os, "ELOOP") and getattr(e, "errno", None) == os.ELOOP:
                raise ArtifactSecurityError("Security violation: Symlink detected in artifact target")
            if isinstance(e, (PermissionError, IsADirectoryError)) or getattr(e, "errno", None) in (getattr(os, "EISDIR", 21), 13):
                if path.is_dir():
                    raise ArtifactSecurityError("Security violation: Artifact target is a directory") from e
            raise ArtifactNotFoundError(f"Artifact file could not be opened: {e}") from e

        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ArtifactSecurityError("Security violation: Artifact is not a regular file")

            if st.st_size != expected_size:
                raise ArtifactIntegrityError(
                    f"Artifact size mismatch: expected {expected_size} bytes, found {st.st_size} bytes"
                )

            # Streaming SHA-256 check
            hasher = hashlib.sha256()
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                hasher.update(chunk)

            actual_sha256 = hasher.hexdigest()
            if actual_sha256.lower() != expected_sha256.lower():
                raise ArtifactIntegrityError(
                    f"Artifact SHA-256 digest mismatch: expected {expected_sha256}, calculated {actual_sha256}"
                )

            # Rewind file descriptor to start for streaming
            os.lseek(fd, 0, os.SEEK_SET)
            return fd, path
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
