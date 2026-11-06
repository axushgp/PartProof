from pathlib import Path
from typing import List, Tuple
from app.core.config import settings
from app.schemas.plan import TaskPlanSchema
from app.services.artifacts.manager import ArtifactManager
from app.services.policy.models import (
    FORBIDDEN_CAPABILITIES,
    PERMITTED_ARTIFACT_EXTENSIONS,
    PERMITTED_CAPABILITIES,
    RuleResult,
)


def evaluate_execution_type_rule(plan: TaskPlanSchema) -> RuleResult:
    """Verifies that all execution steps strictly specify Python."""
    invalid_steps = [s.step_id for s in plan.steps if s.execution_type != "python"]
    if invalid_steps:
        return RuleResult(
            rule_id="SEC-001",
            rule_name="PermittedExecutionType",
            passed=False,
            message=f"Unsupported execution_type in steps: {invalid_steps}. Only 'python' is permitted.",
            severity="error",
        )
    return RuleResult(
        rule_id="SEC-001",
        rule_name="PermittedExecutionType",
        passed=True,
        message="All steps use permitted 'python' runtime.",
        severity="info",
    )


def evaluate_step_count_rule(plan: TaskPlanSchema) -> RuleResult:
    """Verifies step count is within server-enforced bounds."""
    count = len(plan.steps)
    if count == 0:
        return RuleResult(
            rule_id="SEC-002",
            rule_name="StepCountBounds",
            passed=False,
            message="Plan contains zero execution steps.",
            severity="error",
        )
    if count > settings.MAX_PLAN_STEPS:
        return RuleResult(
            rule_id="SEC-002",
            rule_name="StepCountBounds",
            passed=False,
            message=f"Plan step count ({count}) exceeds maximum allowed limit ({settings.MAX_PLAN_STEPS}).",
            severity="error",
        )
    return RuleResult(
        rule_id="SEC-002",
        rule_name="StepCountBounds",
        passed=True,
        message=f"Step count ({count}) is within limit ({settings.MAX_PLAN_STEPS}).",
        severity="info",
    )


def evaluate_network_mode_rule(plan: TaskPlanSchema) -> RuleResult:
    """Strictly enforces zero outbound network access."""
    if plan.network_required is True:
        return RuleResult(
            rule_id="SEC-003",
            rule_name="ZeroNetworkEnforcement",
            passed=False,
            message="Network access is strictly forbidden under Blast Radius Zero policy.",
            severity="error",
        )
    return RuleResult(
        rule_id="SEC-003",
        rule_name="ZeroNetworkEnforcement",
        passed=True,
        message="Network access disabled (Network.none() enforced).",
        severity="info",
    )


def evaluate_capabilities_rule(plan: TaskPlanSchema) -> RuleResult:
    """Validates requested capabilities against the strict allowlist."""
    req_caps = set(c.strip().lower() for c in plan.required_capabilities)

    # Check for explicitly forbidden capabilities
    forbidden_matches = req_caps.intersection(FORBIDDEN_CAPABILITIES)
    if forbidden_matches:
        return RuleResult(
            rule_id="SEC-004",
            rule_name="CapabilityAllowlist",
            passed=False,
            message=f"Forbidden security capabilities requested: {sorted(list(forbidden_matches))}.",
            severity="error",
        )

    # Check for unallowlisted capabilities
    unknown_caps = req_caps.difference(PERMITTED_CAPABILITIES)
    if unknown_caps:
        return RuleResult(
            rule_id="SEC-004",
            rule_name="CapabilityAllowlist",
            passed=False,
            message=f"Unallowlisted capabilities requested: {sorted(list(unknown_caps))}. "
                    f"Permitted: {sorted(list(PERMITTED_CAPABILITIES))}.",
            severity="error",
        )

    return RuleResult(
        rule_id="SEC-004",
        rule_name="CapabilityAllowlist",
        passed=True,
        message="All requested capabilities belong to the strict allowlist.",
        severity="info",
    )


def evaluate_source_size_rule(plan: TaskPlanSchema) -> RuleResult:
    """Enforces source code size limits and checks for illegal control bytes."""
    total_bytes = sum(len(s.code.encode("utf-8")) for s in plan.steps if s.code)
    if total_bytes > settings.MAX_SOURCE_INPUT_BYTES:
        return RuleResult(
            rule_id="SEC-005",
            rule_name="SourceCodeBounds",
            passed=False,
            message=f"Total source code size ({total_bytes} bytes) exceeds limit ({settings.MAX_SOURCE_INPUT_BYTES} bytes).",
            severity="error",
        )

    for step in plan.steps:
        if "\x00" in step.code:
            return RuleResult(
                rule_id="SEC-005",
                rule_name="SourceCodeBounds",
                passed=False,
                message=f"Illegal null byte detected in step '{step.step_id}'.",
                severity="error",
            )

    return RuleResult(
        rule_id="SEC-005",
        rule_name="SourceCodeBounds",
        passed=True,
        message=f"Source code size ({total_bytes} bytes) is within limits.",
        severity="info",
    )


def evaluate_artifacts_rule(plan: TaskPlanSchema, artifact_manager: ArtifactManager) -> RuleResult:
    """Validates all expected artifact filenames against path traversal, extensions, and limits."""
    if len(plan.expected_artifacts) > settings.MAX_ARTIFACTS_PER_EXECUTION:
        return RuleResult(
            rule_id="SEC-006",
            rule_name="ArtifactSafety",
            passed=False,
            message=(
                f"Artifact count ({len(plan.expected_artifacts)}) exceeds maximum "
                f"allowed limit ({settings.MAX_ARTIFACTS_PER_EXECUTION})."
            ),
            severity="error",
        )

    invalid_artifacts = []
    for art_name in plan.expected_artifacts:
        try:
            artifact_manager.sanitize_and_validate_filename(art_name)
            ext = Path(art_name).suffix.lower()
            if not ext or ext not in PERMITTED_ARTIFACT_EXTENSIONS:
                invalid_artifacts.append(
                    f"'{art_name}' (disallowed extension '{ext}', allowed: {sorted(list(PERMITTED_ARTIFACT_EXTENSIONS))})"
                )
        except Exception as e:
            invalid_artifacts.append(f"'{art_name}' ({e})")

    if invalid_artifacts:
        return RuleResult(
            rule_id="SEC-006",
            rule_name="ArtifactSafety",
            passed=False,
            message=f"Unsafe artifact filenames: {'; '.join(invalid_artifacts)}.",
            severity="error",
        )

    return RuleResult(
        rule_id="SEC-006",
        rule_name="ArtifactSafety",
        passed=True,
        message=f"All expected artifacts ({len(plan.expected_artifacts)}) passed safety and extension validation.",
        severity="info",
    )
