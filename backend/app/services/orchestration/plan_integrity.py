import hashlib
import json
from typing import Any, Dict, Union
from app.schemas.plan import TaskPlanSchema


def canonicalize_plan(plan: Union[TaskPlanSchema, Dict[str, Any]]) -> str:
    """
    Produces deterministic, canonical JSON representation of a task plan.
    Enforces sorted keys, deterministic comma/colon separators, and consistent UTF-8 encoding.
    """
    if isinstance(plan, TaskPlanSchema):
        data = plan.model_dump()
    elif isinstance(plan, dict):
        data = plan
    else:
        raise TypeError(f"Expected TaskPlanSchema or dict, got {type(plan).__name__}")

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_plan_hash(plan: Union[TaskPlanSchema, Dict[str, Any]]) -> str:
    """
    Calculates cryptographic SHA-256 digest of the canonicalized plan JSON.
    Guarantees deterministic identity for plan approval and execution binding.
    """
    canonical_json = canonicalize_plan(plan)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def verify_plan_hash(plan: Union[TaskPlanSchema, Dict[str, Any]], expected_hash: str) -> bool:
    """
    Validates whether the given plan matches an expected canonical SHA-256 hash.
    """
    if not expected_hash:
        return False
    computed = compute_plan_hash(plan)
    return computed.lower() == expected_hash.strip().lower()
