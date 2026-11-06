import copy
import pytest
from app.schemas.plan import PlanStepSchema, TaskPlanSchema
from app.services.orchestration.plan_integrity import (
    canonicalize_plan,
    compute_plan_hash,
    verify_plan_hash,
)

SAMPLE_PLAN = TaskPlanSchema(
    title="Structural Fastener Audit",
    summary="Compares bolt quantities and torque ratings",
    reasoning_summary="Evaluates grade 8.8 vs 10.9 steel fasteners across quote sheets",
    steps=[
        PlanStepSchema(
            step_id="step_1",
            description="Parse fasteners and calculate total mass",
            execution_type="python",
            code="print('Parsing fasteners')\nwith open('/workspace/output/fasteners.csv', 'w') as f: f.write('id,qty\\nF-01,100\\n')",
            expected_output="fasteners.csv created",
        )
    ],
    required_capabilities=["math_computation", "file_write"],
    network_required=False,
    success_criteria=["fasteners.csv generated and verified"],
    expected_artifacts=["fasteners.csv"],
)


def test_canonicalize_plan_deterministic():
    """Validates that dictionary key order or object creation order does not affect canonical JSON."""
    dict_a = {
        "title": "Audit",
        "summary": "Check",
        "reasoning_summary": "Details",
        "steps": [{"step_id": "1", "description": "D", "execution_type": "python", "code": "pass", "expected_output": None}],
        "required_capabilities": ["math_computation"],
        "network_required": False,
        "success_criteria": ["Done"],
        "expected_artifacts": [],
    }
    # Reverse key order
    dict_b = {k: dict_a[k] for k in reversed(list(dict_a.keys()))}

    canon_a = canonicalize_plan(dict_a)
    canon_b = canonicalize_plan(dict_b)

    assert canon_a == canon_b
    assert ":" in canon_a and "," in canon_a
    # No whitespace around separators
    assert ": " not in canon_a and ", " not in canon_a


def test_compute_plan_hash_stability():
    """Hash must be stable across multiple computations for the same plan."""
    hash_1 = compute_plan_hash(SAMPLE_PLAN)
    hash_2 = compute_plan_hash(SAMPLE_PLAN)

    assert hash_1 == hash_2
    assert len(hash_1) == 64  # SHA-256 length


def test_compute_plan_hash_sensitivity_to_code_change():
    """Any change in code must result in a different hash."""
    modified_plan = copy.deepcopy(SAMPLE_PLAN)
    modified_plan.steps[0].code += "\n# modified code comment"

    hash_original = compute_plan_hash(SAMPLE_PLAN)
    hash_modified = compute_plan_hash(modified_plan)

    assert hash_original != hash_modified


def test_compute_plan_hash_sensitivity_to_title_change():
    """Any change in plan metadata must alter the hash."""
    modified_plan = copy.deepcopy(SAMPLE_PLAN)
    modified_plan.title = "Modified Fastener Audit"

    assert compute_plan_hash(SAMPLE_PLAN) != compute_plan_hash(modified_plan)


def test_compute_plan_hash_sensitivity_to_artifact_change():
    """Changes in expected artifacts must alter the hash."""
    modified_plan = copy.deepcopy(SAMPLE_PLAN)
    modified_plan.expected_artifacts.append("extra_output.json")

    assert compute_plan_hash(SAMPLE_PLAN) != compute_plan_hash(modified_plan)


def test_compute_plan_hash_sensitivity_to_network_flag():
    """Flipping network_required must alter the hash."""
    modified_plan = copy.deepcopy(SAMPLE_PLAN)
    modified_plan.network_required = True

    assert compute_plan_hash(SAMPLE_PLAN) != compute_plan_hash(modified_plan)


def test_verify_plan_hash():
    """Validates verification helper with positive and negative cases."""
    plan_hash = compute_plan_hash(SAMPLE_PLAN)

    assert verify_plan_hash(SAMPLE_PLAN, plan_hash) is True
    assert verify_plan_hash(SAMPLE_PLAN, plan_hash.upper()) is True
    assert verify_plan_hash(SAMPLE_PLAN, "0" * 64) is False
    assert verify_plan_hash(SAMPLE_PLAN, "") is False
