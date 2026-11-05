from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.task import TaskRead, TaskPlanRead


class ExecutionStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    step_number: int
    description: str
    execution_type: str
    code: Optional[str]
    status: str
    stdout: Optional[str]
    stderr: Optional[str]
    exit_code: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    execution_id: Optional[str]
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ExecutionReceipt(BaseModel):
    task_id: str
    execution_id: str
    sandbox_id: Optional[str]
    status: str
    runtime_image: str
    guest_kernel: Optional[str]
    cpu_limit: int
    memory_limit_mb: int
    network_mode: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    exit_code: Optional[int]
    cleanup_status: str
    steps_executed: int
    artifacts: List[ArtifactRead]
    security_verified: bool
    verification_hash: str


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    sandbox_id: Optional[str]
    status: str
    runtime_image: str
    cpu_limit: int
    memory_limit_mb: int
    network_mode: str
    guest_kernel: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    exit_code: Optional[int]
    cleanup_status: str
    receipt_json: Optional[Dict[str, Any]]
    steps: List[ExecutionStepRead] = []
    artifacts: List[ArtifactRead] = []


class ExecutionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    execution_id: Optional[str]
    event_type: str
    message: str
    metadata_json: Optional[Dict[str, Any]]
    timestamp: datetime


class TaskDetail(BaseModel):
    task: TaskRead
    plan: Optional[TaskPlanRead]
    latest_execution: Optional[ExecutionRead]
    artifacts: List[ArtifactRead] = []
    events: List[ExecutionEventRead] = []
