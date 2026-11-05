from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class InferenceMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str = Field(description="'system' | 'user' | 'assistant'")
    content: str = Field(description="Message text content")


class InferenceMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = "vultr"
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: float
    retries: int = 0


class InferenceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    metadata: InferenceMetadata


class ProviderHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str = Field(description="'reachable' | 'not_configured' | 'auth_failed' | 'rate_limited' | 'unreachable' | 'degraded'")
    model: str
    latency_ms: Optional[float] = None
    message: Optional[str] = None
