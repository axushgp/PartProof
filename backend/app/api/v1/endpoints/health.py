from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Body
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.api.deps import get_inference_client
from app.core.config import settings
from app.database.session import get_db
from app.schemas.system import HealthResponse, SystemStatus
from app.services.inference.base import ProviderHealth
from app.services.inference.vultr_client import VultrInferenceClient
from app.services.receipt import get_receipt_signer, verify_execution_receipt, ReceiptVerificationResult

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


@router.get("/system/inference", response_model=ProviderHealth)
async def check_inference_provider(
    client: VultrInferenceClient = Depends(get_inference_client),
):
    """
    Explicit connectivity check for Vultr Serverless Inference.
    Does not issue completion requests; verifies authentication and endpoint reachability.
    Uses the managed inference client to prevent HTTP connection leaks.
    """
    return await client.check_health()


class ReceiptVerificationRequest(BaseModel):
    receipt: Dict[str, Any]
    expected_plan_hash: Optional[str] = None


@router.get("/system/verification-key")
async def get_verification_key():
    """
    Returns the active Ed25519 public verification key and key ID.
    Enables independent, offline or third-party verification of cryptographic execution receipts.
    Private signing keys remain strictly server-side and are never exposed.
    """
    signer = get_receipt_signer()
    return {
        "key_id": signer.key_id,
        "algorithm": "Ed25519",
        "public_key_hex": signer.public_key_hex,
        "public_key_b64": signer.public_key_b64,
    }


@router.post("/system/receipt-verify", response_model=ReceiptVerificationResult)
async def verify_receipt_endpoint(
    payload: ReceiptVerificationRequest,
):
    """
    Independent verification endpoint for cryptographic execution receipts.
    Evaluates Ed25519 digital signature, canonical SHA-256 digest integrity,
    teardown verification status, and plan/artifact consistency.
    """
    return verify_execution_receipt(
        receipt=payload.receipt,
        expected_plan_hash=payload.expected_plan_hash,
    )
