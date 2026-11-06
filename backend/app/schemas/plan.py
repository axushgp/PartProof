from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class PlanStepSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(description="Unique step identifier, e.g. step_1")
    description: str = Field(description="Concise description of the step")
    execution_type: str = Field(default="python", description="Execution runtime, currently 'python'")
    code: str = Field(description="Strictly valid, self-contained Python code to execute inside the sandbox")
    expected_output: Optional[str] = Field(default=None, description="Expected console output or artifact")


class TaskPlanSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(description="Concise task title")
    summary: str = Field(description="What the agent intends to accomplish")
    reasoning_summary: str = Field(description="High-level reasoning explaining the execution approach")
    steps: List[PlanStepSchema] = Field(description="Ordered list of execution steps")
    required_capabilities: List[str] = Field(default_factory=list, description="Capabilities requested, e.g. 'file_write', 'math_computation'")
    network_required: bool = Field(default=False, description="Whether network access is requested (Default: False)")
    success_criteria: List[str] = Field(default_factory=list, description="Measurable conditions for task success")
    expected_artifacts: List[str] = Field(default_factory=list, description="Filenames expected to be generated, e.g. ['report.csv']")


class PolicyEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowed: bool
    policy_name: str = "blast_radius_zero_strict"
    policy_version: str = "1.0.0"
    image: str = "python:3.12-slim"
    cpu_limit: int = 1
    memory_limit_mb: int = 512
    timeout_seconds: int = 30
    network_mode: str = "none"
    approval_required: bool = True
    plan_hash: Optional[str] = None
    evaluated_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    reasons: List[str] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    rule_results: List[Dict[str, Any]] = Field(default_factory=list)
