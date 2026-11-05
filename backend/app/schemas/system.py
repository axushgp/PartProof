from typing import Optional, Dict, Any
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"
    environment: str
    database_connected: bool
    sandbox_backend: str


class SystemStatus(BaseModel):
    status: str
    environment: str
    vultr_inference_configured: bool
    vultr_inference_model: str
    sandbox_backend: str
    sandbox_ready: bool
    database_connected: bool
    active_sandboxes: int
    max_concurrent_sandboxes: int
    security_invariants: Dict[str, Any]
