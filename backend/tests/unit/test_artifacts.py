import hashlib
import os
import pytest
from pathlib import Path
from app.services.artifacts.manager import ArtifactManager
from app.services.sandbox.base import (
    ArtifactCollectionError,
    PolicyViolationError,
)


@pytest.fixture
def temp_artifact_dir(tmp_path):
    storage_dir = tmp_path / "artifacts"
    storage_dir.mkdir()
    return storage_dir


@pytest.fixture
def artifact_manager(temp_artifact_dir):
    return ArtifactManager(
        base_storage_dir=str(temp_artifact_dir),
        max_artifacts=5,
        max_file_size=1024 * 1024,      # 1 MB
        max_total_size=2 * 1024 * 1024,  # 2 MB
        max_source_size=10 * 1024,       # 10 KB
    )


def test_valid_artifact_storage_and_sha256(artifact_manager, temp_artifact_dir):
    data = b"col1,col2\nval1,val2\n"
    expected_hash = hashlib.sha256(data).hexdigest()

    meta = artifact_manager.store_artifact_from_bytes(
        task_id="task-1234",
        execution_id="exec-5678",
        filename="report.csv",
        data=data,
    )

    assert meta.filename == "report.csv"
    assert meta.size_bytes == len(data)
    assert meta.sha256 == expected_hash
    assert meta.mime_type in ["text/csv", "application/vnd.ms-excel"]
    assert os.path.exists(meta.storage_path)
    assert Path(meta.storage_path).read_bytes() == data


def test_directory_traversal_detection(artifact_manager):
    # Traversal in filename
    with pytest.raises(ArtifactCollectionError, match="Path traversal"):
        artifact_manager.store_artifact_from_bytes(
            task_id="task-1234",
            execution_id="exec-5678",
            filename="../secret.txt",
            data=b"leak",
        )

    with pytest.raises(ArtifactCollectionError, match="Path traversal"):
        artifact_manager.store_artifact_from_bytes(
            task_id="task-1234",
            execution_id="exec-5678",
            filename="subdir/../../etc/passwd",
            data=b"leak",
        )


def test_absolute_path_rejection(artifact_manager):
    with pytest.raises(ArtifactCollectionError, match="Path traversal|Absolute paths|illegal characters"):
        artifact_manager.store_artifact_from_bytes(
            task_id="task-1234",
            execution_id="exec-5678",
            filename="/etc/shadow",
            data=b"leak",
        )


def test_hidden_dotfiles_rejection(artifact_manager):
    with pytest.raises(ArtifactCollectionError, match="Hidden dotfiles"):
        artifact_manager.store_artifact_from_bytes(
            task_id="task-1234",
            execution_id="exec-5678",
            filename=".env",
            data=b"SECRET=123",
        )


def test_unsafe_filename_characters(artifact_manager):
    with pytest.raises(ArtifactCollectionError, match="illegal characters"):
        artifact_manager.store_artifact_from_bytes(
            task_id="task-1234",
            execution_id="exec-5678",
            filename="report;rm -rf.csv",
            data=b"exploit",
        )


def test_oversized_artifact_rejection(artifact_manager):
    oversized_data = b"X" * (1024 * 1024 + 10)  # > 1 MB
    with pytest.raises(ArtifactCollectionError, match="exceeds limit"):
        artifact_manager.store_artifact_from_bytes(
            task_id="task-1234",
            execution_id="exec-5678",
            filename="large.bin",
            data=oversized_data,
        )


def test_batch_limits_exceeded(artifact_manager):
    # Test too many artifacts limit
    artifacts = []
    for i in range(6):  # max_artifacts is 5
        artifacts.append(
            artifact_manager.store_artifact_from_bytes(
                task_id="task-1234",
                execution_id="exec-5678",
                filename=f"file_{i}.txt",
                data=b"test",
            )
        )

    with pytest.raises(ArtifactCollectionError, match="Artifact count .* exceeds maximum"):
        artifact_manager.validate_artifact_collection_limits(artifacts)


def test_duplicate_filenames_rejection(artifact_manager):
    art1 = artifact_manager.store_artifact_from_bytes(
        task_id="task-1234",
        execution_id="exec-5678",
        filename="data.csv",
        data=b"row1",
    )
    # Duplicate entry
    with pytest.raises(ArtifactCollectionError, match="Duplicate filenames"):
        artifact_manager.validate_artifact_collection_limits([art1, art1])


def test_source_code_validation(artifact_manager):
    # Valid source code
    artifact_manager.validate_source_code("print('Hello PartProof')")

    # Empty source code
    with pytest.raises(PolicyViolationError, match="cannot be empty"):
        artifact_manager.validate_source_code("   ")

    # Null byte in source code
    with pytest.raises(PolicyViolationError, match="null bytes"):
        artifact_manager.validate_source_code("print('test')\x00malicious")

    # Oversized source code (> 10 KB in fixture)
    oversized_code = "# " + ("A" * 12000)
    with pytest.raises(PolicyViolationError, match="exceeds maximum allowed size"):
        artifact_manager.validate_source_code(oversized_code)
