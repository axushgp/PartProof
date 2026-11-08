import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def format_iso_timestamp(dt: Optional[datetime]) -> Optional[str]:
    """
    Deterministically formats datetime to ISO 8601 UTC string (e.g., '2026-11-08T10:00:00Z').
    Ensures identical string representation across platforms and timezones.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    # Output standard RFC 3339 / ISO 8601 with Z suffix
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


try:
    import rfc8785
    _HAS_RFC8785 = True
except ImportError:
    _HAS_RFC8785 = False


def _canonicalize_fallback(obj: Any) -> str:
    """
    Pure Python RFC 8785 conformant fallback:
    - Object keys sorted by UTF-16 code units (k.encode('utf-16-be'))
    - Numbers formatted per ECMAScript Number.prototype.toString(10)
    - Compact separators (no whitespace)
    - Unicode code points unescaped (ensure_ascii=False)
    """
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        if obj == 0.0:
            return "0"
        if obj.is_integer() and abs(obj) < 1e21:
            return str(int(obj))
        return repr(obj)
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, list):
        return "[" + ",".join(_canonicalize_fallback(item) for item in obj) + "]"
    if isinstance(obj, dict):
        sorted_keys = sorted(obj.keys(), key=lambda k: k.encode("utf-16-be"))
        parts = [
            f'{json.dumps(k, ensure_ascii=False)}:{_canonicalize_fallback(obj[k])}'
            for k in sorted_keys
        ]
        return "{" + ",".join(parts) + "}"
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def canonicalize_json(data: Dict[str, Any]) -> bytes:
    """
    Canonicalizes dictionary deterministically according to RFC 8785 (JSON Canonicalization Scheme):
    - UTF-8 encoding
    - Keys sorted by UTF-16 code unit ordering
    - Numbers serialized per ECMAScript standards (e.g. 1.0 -> 1, -0.0 -> 0)
    - Compact separators (no whitespace after ':' or ',')
    - Non-ASCII preserved (ensure_ascii=False)
    """
    if _HAS_RFC8785:
        return rfc8785.dumps(data)
    return _canonicalize_fallback(data).encode("utf-8")


def compute_receipt_digest(canonical_bytes: bytes) -> str:
    """Computes SHA-256 hexadecimal digest of canonical receipt payload bytes."""
    return hashlib.sha256(canonical_bytes).hexdigest()


def build_bound_receipt_payload(
    receipt_version: str,
    key_id: str,
    task_id: str,
    execution_id: str,
    approved_plan_hash: Optional[str],
    sandbox_id: Optional[str],
    runtime_image: str,
    guest_kernel: Optional[str],
    cpu_limit: int,
    memory_limit_mb: int,
    timeout_seconds: int,
    network_mode: str,
    started_at: Optional[datetime | str],
    completed_at: Optional[datetime | str],
    duration_seconds: Optional[float],
    exit_code: Optional[int],
    status: str,
    cleanup_status: str,
    steps: List[Dict[str, Any]],
    artifacts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Constructs the canonical dictionary of items cryptographically bound into the receipt:
    1. Task ID and execution ID
    2. Approved plan SHA-256 hash
    3. Sandbox ID
    4. Runtime image and guest kernel
    5. CPU, memory and timeout limits
    6. Network mode
    7. Execution start/end timestamps and duration
    8. Exit code and final execution status
    9. Individual step descriptions, outcomes and exit codes (sorted by step_number)
    10. Artifact filenames, sizes and SHA-256 hashes (sorted by filename)
    11. Cleanup status
    12. Receipt schema version and signing key ID
    """
    started_iso = (
        format_iso_timestamp(started_at)
        if isinstance(started_at, datetime)
        else started_at
    )
    completed_iso = (
        format_iso_timestamp(completed_at)
        if isinstance(completed_at, datetime)
        else completed_at
    )

    # Normalize and sort steps by step_number
    normalized_steps = []
    for s in steps:
        normalized_steps.append({
            "step_number": int(s.get("step_number", 0)),
            "description": str(s.get("description", "")),
            "status": str(s.get("status", "")),
            "exit_code": s.get("exit_code"),
        })
    normalized_steps.sort(key=lambda s: s["step_number"])

    # Normalize and sort artifacts by filename
    normalized_artifacts = []
    for a in artifacts:
        normalized_artifacts.append({
            "filename": str(a.get("filename", "")),
            "size_bytes": int(a.get("size_bytes", 0)),
            "sha256": str(a.get("sha256", "")),
        })
    normalized_artifacts.sort(key=lambda a: a["filename"])

    return {
        "receipt_version": receipt_version,
        "key_id": key_id,
        "task_id": str(task_id),
        "execution_id": str(execution_id),
        "approved_plan_hash": str(approved_plan_hash) if approved_plan_hash else None,
        "sandbox_id": str(sandbox_id) if sandbox_id else None,
        "runtime_image": str(runtime_image),
        "guest_kernel": str(guest_kernel) if guest_kernel else None,
        "cpu_limit": int(cpu_limit),
        "memory_limit_mb": int(memory_limit_mb),
        "timeout_seconds": int(timeout_seconds),
        "network_mode": str(network_mode),
        "started_at": started_iso,
        "completed_at": completed_iso,
        "duration_seconds": round(float(duration_seconds), 4) if duration_seconds is not None else None,
        "exit_code": int(exit_code) if exit_code is not None else None,
        "status": str(status),
        "cleanup_status": str(cleanup_status),
        "steps": normalized_steps,
        "artifacts": normalized_artifacts,
    }


def extract_bound_payload_from_receipt(receipt_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts and normalizes the bound payload fields from an existing receipt document
    for independent verification and digest checking.
    """
    return build_bound_receipt_payload(
        receipt_version=receipt_dict.get("receipt_version", "1.0.0"),
        key_id=receipt_dict.get("key_id", ""),
        task_id=receipt_dict.get("task_id", ""),
        execution_id=receipt_dict.get("execution_id", ""),
        approved_plan_hash=receipt_dict.get("approved_plan_hash") or receipt_dict.get("plan_hash"),
        sandbox_id=receipt_dict.get("sandbox_id"),
        runtime_image=receipt_dict.get("runtime_image", "python:3.12-slim"),
        guest_kernel=receipt_dict.get("guest_kernel"),
        cpu_limit=receipt_dict.get("cpu_limit", 1),
        memory_limit_mb=receipt_dict.get("memory_limit_mb", 512),
        timeout_seconds=receipt_dict.get("timeout_seconds", 30),
        network_mode=receipt_dict.get("network_mode", "none"),
        started_at=receipt_dict.get("started_at"),
        completed_at=receipt_dict.get("completed_at"),
        duration_seconds=receipt_dict.get("duration_seconds"),
        exit_code=receipt_dict.get("exit_code"),
        status=receipt_dict.get("status", ""),
        cleanup_status=receipt_dict.get("cleanup_status", ""),
        steps=receipt_dict.get("steps") or [],
        artifacts=receipt_dict.get("artifacts") or [],
    )
