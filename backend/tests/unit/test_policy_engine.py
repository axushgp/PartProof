import copy
import pytest
from app.core.config import settings
from app.schemas.plan import PlanStepSchema, TaskPlanSchema
from app.services.artifacts.manager import ArtifactManager
from app.services.policy.engine import DeterministicPolicyEngine
from app.services.policy.exceptions import PolicyDeniedError

VALID_PLAN = TaskPlanSchema(
    title="Engineering BOM Discrepancy Audit",
    summary="Scans fasteners and machined brackets for discrepancies",
    reasoning_summary="Reconciles ERP part counts with vendor quotation quantities",
    steps=[
        PlanStepSchema(
            step_id="step_1",
            description="Reconcile bracket quantities",
            execution_type="python",
            code="print('Reconciling BOM')\nwith open('/workspace/output/bom_summary.csv', 'w') as f: f.write('sku,qty\\nBKT-01,50\\n')",
            expected_output="bom_summary.csv written",
        )
    ],
    required_capabilities=["math_computation", "file_read", "file_write"],
    network_required=False,
    success_criteria=["bom_summary.csv generated and verified"],
    expected_artifacts=["bom_summary.csv"],
)


@pytest.fixture
def policy_engine() -> DeterministicPolicyEngine:
    return DeterministicPolicyEngine()


def test_valid_offline_plan_passes_policy(policy_engine: DeterministicPolicyEngine):
    """A well-formed offline python audit plan must pass policy evaluation with zero violations."""
    result = policy_engine.evaluate(VALID_PLAN)

    assert result.allowed is True
    assert len(result.violations) == 0
    assert result.policy_name == "blast_radius_zero_strict"
    assert result.policy_version == "1.0.0"
    assert result.network_mode == "none"
    assert result.approval_required is True
    assert result.plan_hash is not None
    assert len(result.plan_hash) == 64
    assert len(result.rule_results) == 6
    assert all(r["passed"] for r in result.rule_results)


def test_network_mode_violation(policy_engine: DeterministicPolicyEngine):
    """Enforce strict zero network access: network_required=True must fail policy."""
    invalid_plan = copy.deepcopy(VALID_PLAN)
    invalid_plan.network_required = True

    result = policy_engine.evaluate(invalid_plan)

    assert result.allowed is False
    assert any("SEC-003" in v and "ZeroNetworkEnforcement" in v for v in result.violations)


def test_unknown_capability_rejected(policy_engine: DeterministicPolicyEngine):
    """Capabilities not in the strict allowlist must be rejected."""
    invalid_plan = copy.deepcopy(VALID_PLAN)
    invalid_plan.required_capabilities.append("arbitrary_system_call")

    result = policy_engine.evaluate(invalid_plan)

    assert result.allowed is False
    assert any("SEC-004" in v and "Unallowlisted capabilities" in v for v in result.violations)


def test_forbidden_capabilities_rejected(policy_engine: DeterministicPolicyEngine):
    """Explicitly dangerous capabilities (e.g. host_filesystem, docker_socket) must trigger denial."""
    forbidden = ["host_filesystem", "docker_socket", "raw_socket", "process_spawn_unrestricted"]
    for cap in forbidden:
        invalid_plan = copy.deepcopy(VALID_PLAN)
        invalid_plan.required_capabilities = ["file_read", cap]

        result = policy_engine.evaluate(invalid_plan)
        assert result.allowed is False
        assert any("SEC-004" in v and "Forbidden security capabilities" in v for v in result.violations)


def test_step_count_bounds(policy_engine: DeterministicPolicyEngine):
    """Step count must be > 0 and <= MAX_PLAN_STEPS."""
    # Zero steps
    zero_plan = copy.deepcopy(VALID_PLAN)
    zero_plan.steps = []
    res_zero = policy_engine.evaluate(zero_plan)
    assert res_zero.allowed is False
    assert any("SEC-002" in v and "zero execution steps" in v for v in res_zero.violations)

    # Exceeding MAX_PLAN_STEPS
    too_many_plan = copy.deepcopy(VALID_PLAN)
    base_step = VALID_PLAN.steps[0]
    too_many_plan.steps = [
        PlanStepSchema(
            step_id=f"step_{i}",
            description=f"Step {i}",
            execution_type="python",
            code="pass",
            expected_output=None,
        )
        for i in range(settings.MAX_PLAN_STEPS + 1)
    ]
    res_too_many = policy_engine.evaluate(too_many_plan)
    assert res_too_many.allowed is False
    assert any("SEC-002" in v and "exceeds maximum allowed limit" in v for v in res_too_many.violations)


def test_unsupported_execution_type_rejected(policy_engine: DeterministicPolicyEngine):
    """Execution types other than 'python' must fail policy."""
    invalid_plan = copy.deepcopy(VALID_PLAN)
    invalid_plan.steps[0].execution_type = "bash"

    result = policy_engine.evaluate(invalid_plan)
    assert result.allowed is False
    assert any("SEC-001" in v and "Unsupported execution_type" in v for v in result.violations)


def test_source_code_null_byte_detected(policy_engine: DeterministicPolicyEngine):
    """Embedded null byte in python code must be rejected."""
    invalid_plan = copy.deepcopy(VALID_PLAN)
    invalid_plan.steps[0].code = "print('hello\x00world')"

    result = policy_engine.evaluate(invalid_plan)
    assert result.allowed is False
    assert any("SEC-005" in v and "Illegal null byte detected" in v for v in result.violations)


def test_source_code_size_limit_exceeded(policy_engine: DeterministicPolicyEngine):
    """Code exceeding MAX_SOURCE_INPUT_BYTES must be rejected."""
    invalid_plan = copy.deepcopy(VALID_PLAN)
    oversized_comment = "# " + ("X" * (settings.MAX_SOURCE_INPUT_BYTES + 100))
    invalid_plan.steps[0].code = oversized_comment

    result = policy_engine.evaluate(invalid_plan)
    assert result.allowed is False
    assert any("SEC-005" in v and "exceeds limit" in v for v in result.violations)


def test_unsafe_artifact_filenames_rejected(policy_engine: DeterministicPolicyEngine):
    """Artifact filenames with path traversal, forbidden extensions, or illegal chars must fail."""
    unsafe_artifacts = [
        "../etc/passwd",
        "/absolute/path/file.csv",
        "nested/sub/dir/file.csv",
        "executable.exe",
        "script.sh",
        "file;bad.csv",
    ]

    for bad_art in unsafe_artifacts:
        invalid_plan = copy.deepcopy(VALID_PLAN)
        invalid_plan.expected_artifacts = [bad_art]

        result = policy_engine.evaluate(invalid_plan)
        assert result.allowed is False, f"Expected {bad_art} to fail policy"
        assert any("SEC-006" in v and "Unsafe artifact filenames" in v for v in result.violations), f"Failed for {bad_art}: {result.violations}"


def test_artifact_count_exceeded_rejected(policy_engine: DeterministicPolicyEngine):
    """Artifact count exceeding MAX_ARTIFACTS_PER_EXECUTION must fail policy."""
    invalid_plan = copy.deepcopy(VALID_PLAN)
    invalid_plan.expected_artifacts = [f"report_{i}.csv" for i in range(settings.MAX_ARTIFACTS_PER_EXECUTION + 1)]

    result = policy_engine.evaluate(invalid_plan)
    assert result.allowed is False
    assert any("SEC-006" in v and "Artifact count" in v for v in result.violations)


def test_evaluate_and_enforce_success(policy_engine: DeterministicPolicyEngine):
    """evaluate_and_enforce returns PolicyEvaluationResult for compliant plan."""
    result = policy_engine.evaluate_and_enforce(VALID_PLAN)
    assert result.allowed is True
    assert result.plan_hash is not None


def test_evaluate_and_enforce_raises_policy_denied(policy_engine: DeterministicPolicyEngine):
    """evaluate_and_enforce raises PolicyDeniedError with violations for non-compliant plan."""
    invalid_plan = copy.deepcopy(VALID_PLAN)
    invalid_plan.network_required = True

    with pytest.raises(PolicyDeniedError) as exc_info:
        policy_engine.evaluate_and_enforce(invalid_plan)

    assert "Policy engine denied task plan" in str(exc_info.value)
    assert len(exc_info.value.violations) > 0
