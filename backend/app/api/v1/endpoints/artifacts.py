import os
from typing import Generator, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.entities import Artifact, Task, User
from app.services.artifacts.manager import (
    ArtifactManager,
    ArtifactNotFoundError,
    ArtifactSecurityError,
    ArtifactIntegrityError,
    build_content_disposition,
)

router = APIRouter()
artifact_manager = ArtifactManager()


def _iter_fd(fd: int, chunk_size: int = 65536) -> Generator[bytes, None, None]:
    """
    Streams data from an open file descriptor in binary chunks.
    Guarantees descriptor closure via finally block upon completion or connection termination.
    """
    try:
        while True:
            chunk = os.read(fd, chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    expected_task_id: Optional[str] = None,
):
    """
    Authenticated artifact download endpoint.
    Retrieves artifact metadata by ID, verifies ownership (task owner or admin),
    verifies file integrity (size and SHA-256 digest), and streams the file securely.
    """
    stmt = (
        select(Artifact)
        .options(selectinload(Artifact.task))
        .where(Artifact.id == artifact_id)
    )
    result = await db.execute(stmt)
    artifact = result.scalar_one_or_none()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )

    # If task-scoped request, verify artifact belongs to the specified task
    if expected_task_id and artifact.task_id != expected_task_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found for this task",
        )

    task = artifact.task
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact task not found",
        )

    # Check ownership: only task owner or admin can download
    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    try:
        fd, _ = artifact_manager.open_and_verify_artifact(
            task_id=artifact.task_id,
            execution_id=artifact.execution_id,
            filename=artifact.filename,
            expected_size=artifact.size_bytes,
            expected_sha256=artifact.sha256,
            storage_key=artifact.storage_key,
        )
    except ArtifactNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact file not found in storage",
        )
    except ArtifactSecurityError as sec_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security policy violation: {sec_err}",
        )
    except ArtifactIntegrityError as int_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Artifact integrity verification failed: {int_err}",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve artifact file",
        )

    content_disposition = build_content_disposition(artifact.filename)
    media_type = artifact.mime_type or "application/octet-stream"

    headers = {
        "Content-Disposition": content_disposition,
        "Content-Length": str(artifact.size_bytes),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }

    return StreamingResponse(
        _iter_fd(fd),
        media_type=media_type,
        headers=headers,
    )
