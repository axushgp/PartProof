import json
import logging
import re
from typing import Optional, Tuple
from app.core.config import settings
from app.schemas.plan import TaskInputProvenance, TaskPlanSchema
from app.services.artifacts.manager import ArtifactManager
from app.services.inference.base import InferenceMetadata
from app.services.inference.exceptions import PlanValidationError, TaskPlanningError
from app.services.inference.prompts import build_planning_messages
from app.services.inference.vultr_client import VultrInferenceClient

logger = logging.getLogger("partproof.planner")


class TaskPlanner:
    """
    Translates natural-language engineering/audit objectives into typed, validated TaskPlanSchemas.
    Enforces step bounds, execution type restrictions, and safe artifact naming.
    """

    def __init__(
        self,
        client: Optional[VultrInferenceClient] = None,
        artifact_manager: Optional[ArtifactManager] = None,
        max_steps: Optional[int] = None,
    ):
        self._owns_client = client is None
        self.client = client or VultrInferenceClient()
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.max_steps = max_steps or settings.MAX_PLAN_STEPS

    async def close(self) -> None:
        """Closes the underlying client if owned by this planner."""
        if self._owns_client and self.client is not None:
            await self.client.close()

    async def aclose(self) -> None:
        """Alias for close()."""
        await self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _clean_json_content(self, raw_content: str) -> str:
        """Strips markdown code fences and extraneous whitespace if present."""
        cleaned = raw_content.strip()
        # Strip markdown ```json ... ``` wrappers if the model emitted them
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    def validate_plan_constraints(self, plan: TaskPlanSchema, raw_json: str) -> None:
        """Enforces hard domain constraints on parsed TaskPlan."""
        violations = []

        # 1. Step count validation
        if not plan.steps:
            violations.append("Plan must contain at least one execution step.")
        elif len(plan.steps) > self.max_steps:
            violations.append(
                f"Plan step count ({len(plan.steps)}) exceeds maximum allowed ({self.max_steps})."
            )

        # 2. Step-level validation
        for step in plan.steps:
            if step.execution_type != "python":
                violations.append(
                    f"Unsupported execution_type '{step.execution_type}' in {step.step_id}. Only 'python' is permitted."
                )
            if not step.code or not step.code.strip():
                violations.append(f"Step '{step.step_id}' contains empty code.")
            else:
                try:
                    self.artifact_manager.validate_source_code(step.code)
                except Exception as e:
                    violations.append(f"Step '{step.step_id}' code rejected: {e}")

        # 3. Artifact filename validation
        for art_name in plan.expected_artifacts:
            try:
                self.artifact_manager.sanitize_and_validate_filename(art_name)
            except Exception as e:
                violations.append(f"Invalid artifact name '{art_name}': {e}")

        # 4. Measurable success criteria
        if not plan.success_criteria:
            violations.append("Plan must specify at least one measurable success criterion.")

        if violations:
            logger.warning(f"Plan validation rejected: {violations}")
            raise PlanValidationError(
                f"Generated plan violated safety constraints: {'; '.join(violations)}",
                raw_output=raw_json,
                violations=violations,
            )

    async def plan_task(
        self,
        task_description: str,
        model: Optional[str] = None,
        input_provenance: Optional[TaskInputProvenance] = None,
    ) -> Tuple[TaskPlanSchema, InferenceMetadata]:
        """
        Coordinates full planning flow: prompt preparation, inference, parsing, and validation.
        """
        if not task_description or not task_description.strip():
            raise TaskPlanningError("Task description cannot be empty.")

        input_files = [f.filename for f in input_provenance.files] if input_provenance and input_provenance.files else None
        messages = build_planning_messages(task_description, input_files=input_files)

        try:
            inference_resp = await self.client.chat_completion(
                messages=messages,
                model=model,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            logger.error(f"Inference call failed during planning: {e}")
            raise e

        raw_content = inference_resp.content
        cleaned_json = self._clean_json_content(raw_content)

        # Parse JSON
        try:
            parsed_data = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            logger.error(f"Model returned invalid JSON: {e}\nRaw content:\n{raw_content}")
            raise PlanValidationError(
                f"Model response was not valid JSON: {e}",
                raw_output=raw_content,
            ) from e

        # Validate against Pydantic TaskPlanSchema
        try:
            if input_provenance and "input_provenance" not in parsed_data:
                parsed_data["input_provenance"] = input_provenance.model_dump(mode="json")
            plan = TaskPlanSchema.model_validate(parsed_data)
            if input_provenance and not plan.input_provenance:
                plan.input_provenance = input_provenance
        except Exception as e:
            logger.error(f"JSON failed TaskPlanSchema validation: {e}")
            raise PlanValidationError(
                f"JSON structure does not match TaskPlanSchema: {e}",
                raw_output=raw_content,
            ) from e

        # Enforce domain safety constraints
        self.validate_plan_constraints(plan, raw_content)

        logger.info(f"Task plan successfully generated and validated: '{plan.title}' ({len(plan.steps)} steps)")
        return plan, inference_resp.metadata
