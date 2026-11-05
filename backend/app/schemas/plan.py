from typing import List, Optional
from pydantic import BaseModel, Field


class PlanStepSchema(BaseModel):
    step_id: str = Field(description="Unique step identifier, e.g. step_1")
    description: str = Field(description="Concise description of the step")
    execution_type: str = Field(default="python", description="Execution runtime, currently 'python'")
    code: str = Field(description="Strictly valid, self-contained Python code to execute inside the sandbox")
    expected_output: Optional[str] = Field(default=None, description="Expected console output or artifact")


class TaskPlanSchema(BaseModel):
    title: str = Field(description="Concise task title")
    summary: str = Field(description="What the agent intends to accomplish")
    reasoning_summary: str = Field(description="High-level reasoning explaining the execution approach")
    steps: List[PlanStepSchema] = Field(description="Ordered list of execution steps")
    required_capabilities: List[str] = Field(default_factory=list, description="Capabilities requested, e.g. 'file_write', 'math_computation'")
    network_required: bool = Field(default=False, description="Whether network access is requested (Default: False)")
    success_criteria: List[str] = Field(default_factory=list, description="Measurable conditions for task success")
    expected_artifacts: List[str] = Field(default_factory=list, description="Filenames expected to be generated, e.g. ['report.csv']")


class PolicyEvaluationResult(BaseModel):
    allowed: bool
    policy_name: str = "blast_radius_zero_strict"
    image: str = "python:3.12-slim"
    cpu_limit: int = 1
    memory_limit_mb: int = 512
    timeout_seconds: int = 30
    network_mode: str = "none"
    approval_required: bool = True
    reasons: List[str] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)
