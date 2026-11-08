from fastapi import APIRouter
from app.api.v1.endpoints import artifacts, auth, health, procurement, tasks

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["Task Planning & Lifecycle"])
api_router.include_router(artifacts.router, prefix="/artifacts", tags=["Artifacts"])
api_router.include_router(procurement.router, prefix="/procurement", tags=["Procurement Intelligence"])
api_router.include_router(health.router, tags=["Health & System Status"])
