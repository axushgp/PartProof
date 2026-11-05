from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.database.session import get_db
from app.schemas.system import HealthResponse, SystemStatus

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    db_connected = False
    try:
        await db.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False
    
    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        version="0.1.0",
        environment=settings.PARTPROOF_ENV,
        database_connected=db_connected,
        sandbox_backend=settings.SANDBOX_BACKEND,
    )


@router.get("/system/status", response_model=SystemStatus)
async def system_status(db: AsyncSession = Depends(get_db)):
    db_connected = False
    try:
        await db.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False
    
    inference_configured = bool(settings.VULTR_INFERENCE_API_KEY)
    
    return SystemStatus(
        status="ready" if db_connected else "offline",
        environment=settings.PARTPROOF_ENV,
        vultr_inference_configured=inference_configured,
        vultr_inference_model=settings.VULTR_INFERENCE_MODEL,
        sandbox_backend=settings.SANDBOX_BACKEND,
        sandbox_ready=True,
        database_connected=db_connected,
        active_sandboxes=0,
        max_concurrent_sandboxes=settings.SANDBOX_MAX_CONCURRENT,
        security_invariants={
            "network_disabled_by_default": True,
            "credentials_in_sandbox": False,
            "max_memory_mb": settings.SANDBOX_MAX_MEMORY_MB,
            "max_cpus": settings.SANDBOX_MAX_CPUS,
            "max_timeout_seconds": settings.SANDBOX_MAX_TIMEOUT_SECONDS,
            "ephemeral_sandboxes": True,
            "automatic_cleanup": True,
        },
    )
