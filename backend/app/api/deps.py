from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.entities import User
from app.services.inference.planner import TaskPlanner
from app.services.inference.vultr_client import VultrInferenceClient

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        return None
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_inference_client(request: Request) -> AsyncGenerator[VultrInferenceClient, None]:
    """
    Provides the application-shared VultrInferenceClient if initialized by app lifespan.
    Otherwise, provisions a per-request client and deterministically closes it in finally.
    Ensures no HTTP connection leaks and avoids unhandled event loop termination warnings.
    """
    shared_client = getattr(request.app.state, "inference_client", None)
    if shared_client is not None:
        yield shared_client
    else:
        per_request_client = VultrInferenceClient()
        try:
            yield per_request_client
        finally:
            await per_request_client.close()


async def get_task_planner(
    client: VultrInferenceClient = Depends(get_inference_client),
) -> TaskPlanner:
    """Provides a TaskPlanner instance wired to the active inference client."""
    return TaskPlanner(client=client)
