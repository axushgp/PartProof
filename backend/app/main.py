import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.database.init_db import init_db
from app.database.session import engine
from app.services.inference.vultr_client import VultrInferenceClient

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("partproof")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing PartProof Backend Service...")
    # 1. Enforce hard invariants
    settings.validate_production_invariants()
    logger.info(f"Environment: {settings.PARTPROOF_ENV} | Sandbox Backend: {settings.SANDBOX_BACKEND}")

    # 2. Initialize database schema & seed demo credentials
    try:
        await init_db()
        logger.info("Database schema initialized and seed user verified.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise e

    # 3. Initialize shared Vultr inference client
    app.state.inference_client = VultrInferenceClient()
    logger.info("Shared Vultr inference client initialized.")

    yield

    # Shutdown
    logger.info("Shutting down PartProof Backend Service...")
    if hasattr(app.state, "inference_client") and app.state.inference_client is not None:
        await app.state.inference_client.close()
        logger.info("Shared Vultr inference client closed.")
    await engine.dispose()
    logger.info("Database connections closed.")


app = FastAPI(
    title="PartProof API",
    description="Autonomous Engineering Task & Procurement Auditor with Blast Radius Zero",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": "PartProof API",
        "tagline": "Autonomous Engineering Task Execution with Blast Radius Zero",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "sandbox_backend": settings.SANDBOX_BACKEND,
    }
