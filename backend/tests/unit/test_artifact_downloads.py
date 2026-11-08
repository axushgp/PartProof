import hashlib
import os
import tempfile
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.entities import Artifact, Task, User
from app.services.artifacts.manager import ArtifactManager


@pytest.fixture
def temp_storage(tmp_path, monkeypatch):
    storage_dir = tmp_path / "partproof_artifacts"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "ARTIFACT_STORAGE_DIR", str(storage_dir))
    return storage_dir


@pytest.fixture
async def users_and_task(db_session: AsyncSession, temp_storage):
    # Owner user
    owner = User(
        email="owner@partproof.dev",
        password_hash=get_password_hash("SecretPass123!"),
        role="engineer",
        is_active=True,
    )
    # Admin user
    admin = User(
        email="admin@partproof.dev",
        password_hash=get_password_hash("AdminPass123!"),
        role="admin",
        is_active=True,
    )
    # Other auditor user
    other = User(
        email="other@partproof.dev",
        password_hash=get_password_hash("OtherPass123!"),
        role="auditor",
        is_active=True,
    )
    db_session.add_all([owner, admin, other])
    await db_session.commit()
    await db_session.refresh(owner)
    await db_session.refresh(admin)
    await db_session.refresh(other)

    # Owner's task
    task = Task(
        user_id=owner.id,
        title="Artifact Download Test Task",
        description="Task used for validating secure artifact downloads",
        status="succeeded",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    return {
        "owner": owner,
        "admin": admin,
        "other": other,
        "task": task,
        "owner_token": create_access_token(subject=owner.id),
        "admin_token": create_access_token(subject=admin.id),
        "other_token": create_access_token(subject=other.id),
    }


def create_disk_artifact(storage_dir: Path, task_id: str, execution_id: str, filename: str, content: bytes) -> Path:
    target_dir = storage_dir / task_id / execution_id
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / filename
    file_path.write_bytes(content)
    return file_path


@pytest.mark.asyncio
async def test_authenticated_owner_downloads_successfully(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    content = b"header1,header2\nvalue1,value2\n"
    sha = hashlib.sha256(content).hexdigest()
    exec_id = "exec-test-101"
    filename = "report.csv"

    disk_path = create_disk_artifact(temp_storage, task.id, exec_id, filename, content)

    artifact = Artifact(
        task_id=task.id,
        execution_id=exec_id,
        filename=filename,
        storage_key=str(disk_path),
        mime_type="text/csv",
        size_bytes=len(content),
        sha256=sha,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 200
    assert response.content == content
    assert "text/csv" in response.headers.get("content-type", "")
    assert f'filename="report.csv"' in response.headers.get("content-disposition", "")
    assert response.headers.get("content-length") == str(len(content))
    assert "no-store" in response.headers.get("cache-control", "")
    assert response.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_admin_can_download_authorized_artifacts(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    content = b'{"status": "ok", "audit": true}'
    sha = hashlib.sha256(content).hexdigest()
    exec_id = "exec-test-102"
    filename = "audit.json"

    disk_path = create_disk_artifact(temp_storage, task.id, exec_id, filename, content)

    artifact = Artifact(
        task_id=task.id,
        execution_id=exec_id,
        filename=filename,
        storage_key=str(disk_path),
        mime_type="application/json",
        size_bytes=len(content),
        sha256=sha,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    # Admin downloads owner's artifact
    headers = {"Authorization": f"Bearer {data['admin_token']}"}
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 200
    assert response.content == content


@pytest.mark.asyncio
async def test_unauthenticated_access_is_rejected(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    content = b"secret content"
    sha = hashlib.sha256(content).hexdigest()
    disk_path = create_disk_artifact(temp_storage, task.id, "exec-103", "data.txt", content)

    artifact = Artifact(
        task_id=task.id,
        execution_id="exec-103",
        filename="data.txt",
        storage_key=str(disk_path),
        mime_type="text/plain",
        size_bytes=len(content),
        sha256=sha,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    # No Authorization header
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_different_user_cannot_download_artifact(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    content = b"owner only data"
    sha = hashlib.sha256(content).hexdigest()
    disk_path = create_disk_artifact(temp_storage, task.id, "exec-104", "private.txt", content)

    artifact = Artifact(
        task_id=task.id,
        execution_id="exec-104",
        filename="private.txt",
        storage_key=str(disk_path),
        mime_type="text/plain",
        size_bytes=len(content),
        sha256=sha,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    # User 'other' attempts to download owner's artifact
    headers = {"Authorization": f"Bearer {data['other_token']}"}
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 403
    assert "access denied" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_missing_artifact_handled_correctly(client: AsyncClient, users_and_task):
    data = users_and_task
    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    response = await client.get("/api/v1/artifacts/00000000-0000-0000-0000-000000000000/download", headers=headers)

    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_missing_file_on_storage_handled_correctly(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]

    artifact = Artifact(
        task_id=task.id,
        execution_id="exec-105",
        filename="vanished.txt",
        storage_key=str(temp_storage / task.id / "exec-105" / "vanished.txt"),
        mime_type="text/plain",
        size_bytes=100,
        sha256="0" * 64,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_path_traversal_attempts_rejected(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]

    # Traversal in storage_key
    artifact = Artifact(
        task_id=task.id,
        execution_id="exec-106",
        filename="secret.txt",
        storage_key="../../etc/passwd",
        mime_type="text/plain",
        size_bytes=20,
        sha256="0" * 64,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code in (400, 404)


@pytest.mark.asyncio
async def test_symlink_rejected(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]

    # Create real target file outside storage
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(b"sensitive host file")
        external_path = Path(tf.name)

    try:
        # Create a symlink inside storage pointing outside
        target_dir = temp_storage / task.id / "exec-symlink"
        target_dir.mkdir(parents=True, exist_ok=True)
        link_path = target_dir / "symlink_file.txt"

        try:
            link_path.symlink_to(external_path)
        except OSError:
            pytest.skip("Symlink creation not permitted in this environment")

        artifact = Artifact(
            task_id=task.id,
            execution_id="exec-symlink",
            filename="symlink_file.txt",
            storage_key=str(link_path),
            mime_type="text/plain",
            size_bytes=len(b"sensitive host file"),
            sha256=hashlib.sha256(b"sensitive host file").hexdigest(),
        )
        db_session.add(artifact)
        await db_session.commit()
        await db_session.refresh(artifact)

        headers = {"Authorization": f"Bearer {data['owner_token']}"}
        response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

        assert response.status_code in (400, 404)
        assert "symlink" in response.text.lower() or "policy violation" in response.text.lower() or response.status_code == 404
    finally:
        if external_path.exists():
            external_path.unlink()


def test_symlink_detection_and_rejection_direct(monkeypatch, temp_storage):
    from app.services.artifacts.manager import ArtifactSecurityError
    mgr = ArtifactManager(base_storage_dir=str(temp_storage))
    dummy_file = temp_storage / "task-symlink" / "exec-symlink" / "dummy.txt"
    dummy_file.parent.mkdir(parents=True, exist_ok=True)
    dummy_file.write_bytes(b"dummy content")

    real_islink = os.path.islink
    monkeypatch.setattr(os.path, "islink", lambda p: True if "dummy.txt" in str(p) else real_islink(p))

    with pytest.raises(ArtifactSecurityError, match="symlink"):
        mgr.resolve_artifact_path("task-symlink", "exec-symlink", "dummy.txt", storage_key=str(dummy_file))


def test_directory_target_rejected_as_non_regular(temp_storage):
    from app.services.artifacts.manager import ArtifactSecurityError
    mgr = ArtifactManager(base_storage_dir=str(temp_storage))
    sub_dir = temp_storage / "task-dir" / "exec-dir" / "somedir"
    sub_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ArtifactSecurityError, match="not a regular file"):
        mgr.open_and_verify_artifact(
            task_id="task-dir",
            execution_id="exec-dir",
            filename="somedir",
            expected_size=0,
            expected_sha256="0" * 64,
            storage_key=str(sub_dir),
        )


@pytest.mark.asyncio
async def test_modified_file_with_sha256_mismatch_rejected(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    original = b"original content 123"
    tampered = b"tampered content 456"
    exec_id = "exec-tampered"
    filename = "tampered.log"

    # Write tampered content on disk
    disk_path = create_disk_artifact(temp_storage, task.id, exec_id, filename, tampered)

    # Register with original content hash and original size
    artifact = Artifact(
        task_id=task.id,
        execution_id=exec_id,
        filename=filename,
        storage_key=str(disk_path),
        mime_type="text/plain",
        size_bytes=len(tampered),  # same length, different bytes
        sha256=hashlib.sha256(original).hexdigest(),
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 409
    assert "integrity verification failed" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_file_size_mismatch_rejected(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    content = b"short"
    exec_id = "exec-size-mismatch"
    filename = "size_error.bin"

    disk_path = create_disk_artifact(temp_storage, task.id, exec_id, filename, content)

    # Registered with a different size
    artifact = Artifact(
        task_id=task.id,
        execution_id=exec_id,
        filename=filename,
        storage_key=str(disk_path),
        mime_type="application/octet-stream",
        size_bytes=len(content) + 50,  # size discrepancy
        sha256=hashlib.sha256(content).hexdigest(),
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 409
    assert "size mismatch" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_filename_and_mime_type_handled_safely(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    content = b"%PDF-1.4 test binary PDF content"
    sha = hashlib.sha256(content).hexdigest()
    exec_id = "exec-mime"
    filename = "Quarterly_Report_Final.pdf"

    disk_path = create_disk_artifact(temp_storage, task.id, exec_id, filename, content)

    artifact = Artifact(
        task_id=task.id,
        execution_id=exec_id,
        filename=filename,
        storage_key=str(disk_path),
        mime_type="application/pdf",
        size_bytes=len(content),
        sha256=sha,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/pdf"
    content_disp = response.headers.get("content-disposition", "")
    assert "attachment" in content_disp
    assert "filename=" in content_disp
    assert "filename*=" in content_disp


@pytest.mark.asyncio
async def test_task_scoped_artifact_download_endpoint(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    content = b"task-scoped artifact data"
    sha = hashlib.sha256(content).hexdigest()
    exec_id = "exec-scoped"
    filename = "scoped.txt"

    disk_path = create_disk_artifact(temp_storage, task.id, exec_id, filename, content)

    artifact = Artifact(
        task_id=task.id,
        execution_id=exec_id,
        filename=filename,
        storage_key=str(disk_path),
        mime_type="text/plain",
        size_bytes=len(content),
        sha256=sha,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    # Download via /tasks/{task_id}/artifacts/{artifact_id}/download
    response = await client.get(f"/api/v1/tasks/{task.id}/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 200
    assert response.content == content


@pytest.mark.asyncio
async def test_task_scoped_mismatched_task_id_rejected(client: AsyncClient, db_session: AsyncSession, users_and_task, temp_storage):
    data = users_and_task
    task = data["task"]
    content = b"mismatched task test data"
    sha = hashlib.sha256(content).hexdigest()
    exec_id = "exec-mismatch"
    filename = "mismatch.txt"

    disk_path = create_disk_artifact(temp_storage, task.id, exec_id, filename, content)

    artifact = Artifact(
        task_id=task.id,
        execution_id=exec_id,
        filename=filename,
        storage_key=str(disk_path),
        mime_type="text/plain",
        size_bytes=len(content),
        sha256=sha,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    headers = {"Authorization": f"Bearer {data['owner_token']}"}
    # Attempt download with a different/fake task ID in the URL
    other_task_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/tasks/{other_task_id}/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 404
    assert "not found for this task" in response.json().get("detail", "").lower()
