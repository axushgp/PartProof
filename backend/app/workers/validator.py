import logging
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.models.entities import Approval, Execution
from app.schemas.plan import TaskPlanSchema
from app.services.artifacts.manager import ArtifactManager
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.policy.engine import DeterministicPolicyEngine

logger = logging.getLogger("partproof.worker.validator")


class SecurityValidationError(Exception):
    """Raised when pre-execution security verification fails."""
    def __init__(self, message: str, violations: Optional[List[str]] = None):
        super().__init__(message)
        self.message = message
        self.violations = violations or [message]

    def __str__(self) -> str:
        if self.violations:
            return f"{self.message} Violations: {'; '.join(self.violations)}"
        return self.message


class SecurityExecutionValidator:
    """
    Performs defense-in-depth pre-execution security verification across 12 distinct checks
    before any microVM is created or code is run.
    """

    def __init__(
        self,
        policy_engine: Optional[DeterministicPolicyEngine] = None,
        artifact_manager: Optional[ArtifactManager] = None,
    ):
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.policy_engine = policy_engine or DeterministicPolicyEngine(artifact_manager=self.artifact_manager)

    def validate(self, execution: Execution, approval: Optional[Approval]) -> TaskPlanSchema:
        """
        Validates all 12 security items against the execution record and approval.
        Returns the validated TaskPlanSchema if all checks pass.
        Raises SecurityValidationError if any check fails.
        """
        violations: List[str] = []

        # 1. State verification
        if execution.status not in ("queued", "preparing"):
            violations.append(f"Invalid execution state '{execution.status}'. Expected 'queued' or 'preparing'.")

        # 2. Approval existence & decision
        if approval is None:
            violations.append("Missing associated Approval record.")
        elif approval.decision != "approved":
            violations.append(f"Approval record decision is '{approval.decision}'. Expected 'approved'.")

        # 3. Approval plan hash match
        if approval and approval.approved_plan_hash != execution.plan_hash:
            violations.append(
                f"Approval hash mismatch: approved_plan_hash='{approval.approved_plan_hash}' != "
                f"execution.plan_hash='{execution.plan_hash}'"
            )

        # 4. Plan snapshot existence
        if not execution.plan_snapshot or not isinstance(execution.plan_snapshot, dict):
            violations.append("Execution plan_snapshot is missing or not a dictionary.")
            raise SecurityValidationError("Plan snapshot is missing or invalid.", violations)

        # 5. Schema validation
        try:
            plan_schema = TaskPlanSchema.model_validate(execution.plan_snapshot)
        except Exception as e:
            violations.append(f"Plan snapshot failed schema validation: {e}")
            raise SecurityValidationError("Plan schema validation failed.", violations)

        # 6. Cryptographic plan integrity
        recomputed_hash = compute_plan_hash(execution.plan_snapshot)
        if recomputed_hash != execution.plan_hash:
            violations.append(
                f"Cryptographic hash integrity mismatch: recomputed='{recomputed_hash}' != "
                f"execution.plan_hash='{execution.plan_hash}'"
            )

        # 7. Deterministic policy evaluation
        policy_res = self.policy_engine.evaluate(plan_schema)
        if not policy_res.allowed:
            for v in policy_res.violations:
                violations.append(f"Policy violation: {v}")

        # 8. Step count bounds
        step_count = len(plan_schema.steps)
        if step_count < 1 or step_count > settings.MAX_PLAN_STEPS:
            violations.append(
                f"Step count ({step_count}) is outside permitted bounds (1 to {settings.MAX_PLAN_STEPS})."
            )

        # 9. Permitted execution types
        for idx, s in enumerate(plan_schema.steps, start=1):
            if s.execution_type != "python":
                violations.append(
                    f"Step {s.step_id or idx} requests disallowed execution type '{s.execution_type}'. Only 'python' is permitted."
                )

        # 10. Zero-network enforcement
        if execution.network_mode != "none" or plan_schema.network_required:
            violations.append(
                f"Non-zero network mode requested (execution='{execution.network_mode}', "
                f"plan.network_required={plan_schema.network_required}). Only 'none' is permitted."
            )

        # 11. Allowlisted runtime image
        if execution.runtime_image not in settings.SANDBOX_ALLOWED_IMAGES:
            violations.append(
                f"Requested image '{execution.runtime_image}' is not allowlisted: {settings.SANDBOX_ALLOWED_IMAGES}"
            )

        # 12. Resource bounds & artifact safety
        if execution.cpu_limit > settings.SANDBOX_MAX_CPUS:
            violations.append(f"CPU limit ({execution.cpu_limit}) exceeds max ({settings.SANDBOX_MAX_CPUS}).")

        if execution.memory_limit_mb > settings.SANDBOX_MAX_MEMORY_MB:
            violations.append(f"Memory limit ({execution.memory_limit_mb}MB) exceeds max ({settings.SANDBOX_MAX_MEMORY_MB}MB).")

        if execution.timeout_seconds > settings.SANDBOX_MAX_TIMEOUT_SECONDS:
            violations.append(f"Timeout ({execution.timeout_seconds}s) exceeds max ({settings.SANDBOX_MAX_TIMEOUT_SECONDS}s).")

        for art in plan_schema.expected_artifacts:
            try:
                self.artifact_manager.sanitize_and_validate_filename(art)
            except Exception as e:
                violations.append(f"Artifact filename '{art}' violates safety bounds: {e}")

        for idx, s in enumerate(plan_schema.steps, start=1):
            try:
                self.artifact_manager.validate_source_code(s.code)
            except Exception as e:
                violations.append(f"Step {s.step_id or idx} code violates safety bounds: {e}")

        if violations:
            logger.warning(
                "Security validation failed for execution %s with %d violations: %s",
                execution.id,
                len(violations),
                "; ".join(violations),
            )
            raise SecurityValidationError("Security execution validation failed.", violations)

        logger.info("Security validation passed all 12 checks for execution %s", execution.id)
        return plan_schema
