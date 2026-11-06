import logging
from datetime import datetime, timezone
from typing import List, Optional
from app.core.config import settings
from app.schemas.plan import PolicyEvaluationResult, TaskPlanSchema
from app.services.artifacts.manager import ArtifactManager
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.policy.exceptions import PolicyDeniedError
from app.services.policy.models import RuleResult
from app.services.policy.rules import (
    evaluate_artifacts_rule,
    evaluate_capabilities_rule,
    evaluate_execution_type_rule,
    evaluate_network_mode_rule,
    evaluate_source_size_rule,
    evaluate_step_count_rule,
)

logger = logging.getLogger("partproof.policy")


class DeterministicPolicyEngine:
    """
    Independent policy evaluation engine enforcing server-side safety boundaries.
    The LLM proposes; the deterministic policy engine verifies and restricts.
    """

    POLICY_NAME = "blast_radius_zero_strict"
    POLICY_VERSION = "1.0.0"

    def __init__(self, artifact_manager: Optional[ArtifactManager] = None):
        self.artifact_manager = artifact_manager or ArtifactManager()

    def evaluate(self, plan: TaskPlanSchema) -> PolicyEvaluationResult:
        """
        Executes all security rules against the proposed task plan.
        Produces an immutable PolicyEvaluationResult with canonical plan hash.
        """
        rule_results: List[RuleResult] = [
            evaluate_execution_type_rule(plan),
            evaluate_step_count_rule(plan),
            evaluate_network_mode_rule(plan),
            evaluate_capabilities_rule(plan),
            evaluate_source_size_rule(plan),
            evaluate_artifacts_rule(plan, self.artifact_manager),
        ]

        violations: List[str] = []
        warnings: List[str] = []
        reasons: List[str] = []

        for r in rule_results:
            if not r.passed:
                if r.severity == "error":
                    violations.append(f"[{r.rule_id} {r.rule_name}] {r.message}")
                elif r.severity == "warning":
                    warnings.append(f"[{r.rule_id} {r.rule_name}] {r.message}")
            else:
                reasons.append(f"[{r.rule_id}] {r.message}")

        allowed = len(violations) == 0
        plan_hash = compute_plan_hash(plan)

        logger.info(
            f"Policy evaluation completed: plan='{plan.title}' allowed={allowed} "
            f"violations={len(violations)} warnings={len(warnings)} hash={plan_hash[:12]}..."
        )

        return PolicyEvaluationResult(
            allowed=allowed,
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            image=settings.SANDBOX_DEFAULT_IMAGE,
            cpu_limit=settings.SANDBOX_DEFAULT_CPUS,
            memory_limit_mb=settings.SANDBOX_DEFAULT_MEMORY_MB,
            timeout_seconds=settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS,
            network_mode="none",
            approval_required=True,
            plan_hash=plan_hash,
            evaluated_at=datetime.now(timezone.utc),
            reasons=reasons,
            violations=violations,
            warnings=warnings,
            rule_results=[r.model_dump() for r in rule_results],
        )

    def evaluate_and_enforce(self, plan: TaskPlanSchema) -> PolicyEvaluationResult:
        """Evaluates policy and raises PolicyDeniedError if not allowed."""
        result = self.evaluate(plan)
        if not result.allowed:
            raise PolicyDeniedError(
                f"Policy engine denied task plan: {'; '.join(result.violations)}",
                violations=result.violations,
            )
        return result
