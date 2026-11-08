from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.plan import (
    PolicyEvaluationResult,
    TaskInputFileManifest,
    TaskInputProvenance,
    TaskPlanSchema,
)


class TaskCreate(BaseModel):
    title: Optional[str] = Field(default=None, description="Optional title; if omitted, the planner assigns one")
    description: str = Field(min_length=5, description="Natural language task or engineering audit objective")
    input_mode: str = Field(default="prompt_only", description="'prompt_only', 'user_upload', or 'synthetic_sample'")
    input_files: List[TaskInputFileManifest] = Field(default_factory=list, description="Attached or selected input file manifest")


class TaskPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    model: str
    plan_json: TaskPlanSchema
    plan_hash: str
    policy_result: PolicyEvaluationResult
    policy_version: str = "1.0.0"
    policy_evaluated_at: Optional[datetime] = None
    approval_status: str
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str]
    title: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class TaskApproveRequest(BaseModel):
    decision: str = Field(default="approved", description="'approved' or 'rejected'")
    reason: Optional[str] = Field(default=None, description="Optional justification note")


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    approved_by: Optional[str] = None
    approved_plan_hash: Optional[str] = None
    decision: str
    reason: Optional[str] = None
    created_at: datetime


class TaskCancelRequest(BaseModel):
    reason: Optional[str] = Field(default="Cancelled by user")
