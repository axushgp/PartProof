import base64
import logging
from typing import Any, Dict, List, Optional
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import BaseModel
from app.services.receipt.canonical import (
    canonicalize_json,
    compute_receipt_digest,
    extract_bound_payload_from_receipt,
)
from app.services.receipt.signer import get_receipt_signer

logger = logging.getLogger("partproof.receipt.verifier")


class ReceiptVerificationResult(BaseModel):
    """Structured report returned by independent execution receipt verification."""

    is_valid: bool
    signature_valid: bool
    digest_valid: bool
    plan_hash_valid: bool
    artifacts_valid: bool
    cleanup_verified: bool
    key_id: Optional[str] = None
    receipt_digest: Optional[str] = None
    verification_hash: Optional[str] = None
    errors: List[str] = []


def verify_execution_receipt(
    receipt: Optional[Dict[str, Any]],
    public_key: Optional[ed25519.Ed25519PublicKey | str | bytes] = None,
    expected_plan_hash: Optional[str] = None,
    expected_artifacts: Optional[List[Dict[str, Any]]] = None,
) -> ReceiptVerificationResult:
    """
    Independently verifies an execution receipt against all security invariants:
    1. Signature validity (Ed25519)
    2. Receipt digest integrity (SHA-256 of canonical payload)
    3. Cleanup status ('verified_destroyed')
    4. Approved plan hash consistency (if expected_plan_hash provided)
    5. Artifact metadata consistency (if expected_artifacts provided)
    """
    errors: List[str] = []

    if not receipt or not isinstance(receipt, dict):
        return ReceiptVerificationResult(
            is_valid=False,
            signature_valid=False,
            digest_valid=False,
            plan_hash_valid=False,
            artifacts_valid=False,
            cleanup_verified=False,
            errors=["Receipt document is empty, missing, or malformed."],
        )

    key_id = receipt.get("key_id", "")
    recorded_digest = receipt.get("receipt_digest") or receipt.get("verification_hash")

    # 1. Resolve verification public key
    resolved_pubkey: Optional[ed25519.Ed25519PublicKey] = None
    if public_key is not None:
        if isinstance(public_key, ed25519.Ed25519PublicKey):
            resolved_pubkey = public_key
        elif isinstance(public_key, bytes):
            resolved_pubkey = ed25519.Ed25519PublicKey.from_public_bytes(public_key)
        elif isinstance(public_key, str):
            try:
                # Try hex (64 chars)
                if len(public_key.strip()) == 64:
                    resolved_pubkey = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key.strip()))
                else:
                    # Try base64
                    raw_b64 = base64.b64decode(public_key.strip())
                    resolved_pubkey = ed25519.Ed25519PublicKey.from_public_bytes(raw_b64)
            except Exception as e:
                errors.append(f"Failed to parse provided public key: {e}")
    else:
        # Default to server's verification key
        resolved_pubkey = get_receipt_signer().public_key

    # 2. Extract bound payload and compute canonical digest
    bound_payload = extract_bound_payload_from_receipt(receipt)
    canonical_bytes = canonicalize_json(bound_payload)
    computed_digest = compute_receipt_digest(canonical_bytes)

    # 3. Verify digest integrity
    digest_valid = False
    if recorded_digest and recorded_digest == computed_digest:
        digest_valid = True
    else:
        errors.append(
            f"Digest integrity failure: receipt specifies digest '{recorded_digest}', "
            f"but canonical payload digest is '{computed_digest}'."
        )

    # 4. Verify Ed25519 digital signature
    signature_valid = False
    signature_hex = receipt.get("signature")
    if not signature_hex or not isinstance(signature_hex, str):
        errors.append("Digital signature missing from receipt.")
    elif resolved_pubkey is None:
        errors.append("No valid Ed25519 public key available for signature verification.")
    else:
        try:
            signature_bytes = bytes.fromhex(signature_hex)
            resolved_pubkey.verify(signature_bytes, canonical_bytes)
            signature_valid = True
        except InvalidSignature:
            errors.append("Ed25519 digital signature verification failed: signature does not match canonical payload.")
        except Exception as e:
            errors.append(f"Failed to verify digital signature: {e}")

    # 5. Verify cleanup status
    cleanup_status = receipt.get("cleanup_status")
    cleanup_verified = cleanup_status == "verified_destroyed"
    if not cleanup_verified:
        errors.append(
            f"MicroVM destruction invariant failure: teardown was '{cleanup_status}' "
            "(must be 'verified_destroyed')."
        )

    # 6. Verify approved plan hash consistency (if provided)
    plan_hash_valid = True
    if expected_plan_hash is not None:
        receipt_plan_hash = receipt.get("approved_plan_hash") or receipt.get("plan_hash")
        if receipt_plan_hash != expected_plan_hash:
            plan_hash_valid = False
            errors.append(
                f"Approved plan hash mismatch: expected '{expected_plan_hash}', "
                f"receipt bound '{receipt_plan_hash}'."
            )

    # 7. Verify artifact metadata consistency (if provided)
    artifacts_valid = True
    if expected_artifacts is not None:
        receipt_arts = {
            a["filename"]: a for a in receipt.get("artifacts", []) if isinstance(a, dict)
        }
        for exp in expected_artifacts:
            fname = exp.get("filename")
            if not fname or fname not in receipt_arts:
                artifacts_valid = False
                errors.append(f"Expected artifact '{fname}' missing from receipt artifacts.")
                continue
            rec_art = receipt_arts[fname]
            if exp.get("sha256") and exp["sha256"] != rec_art.get("sha256"):
                artifacts_valid = False
                errors.append(
                    f"Artifact '{fname}' SHA-256 mismatch: expected '{exp['sha256']}', "
                    f"receipt bound '{rec_art.get('sha256')}'."
                )
            if exp.get("size_bytes") is not None and exp["size_bytes"] != rec_art.get("size_bytes"):
                artifacts_valid = False
                errors.append(
                    f"Artifact '{fname}' size mismatch: expected {exp['size_bytes']} bytes, "
                    f"receipt bound {rec_art.get('size_bytes')} bytes."
                )

    is_overall_valid = (
        signature_valid
        and digest_valid
        and cleanup_verified
        and plan_hash_valid
        and artifacts_valid
    )

    return ReceiptVerificationResult(
        is_valid=is_overall_valid,
        signature_valid=signature_valid,
        digest_valid=digest_valid,
        plan_hash_valid=plan_hash_valid,
        artifacts_valid=artifacts_valid,
        cleanup_verified=cleanup_verified,
        key_id=key_id,
        receipt_digest=computed_digest,
        verification_hash=recorded_digest,
        errors=errors,
    )
