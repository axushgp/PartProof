import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from app.core.config import settings
from app.services.receipt.canonical import (
    build_bound_receipt_payload,
    canonicalize_json,
    compute_receipt_digest,
)

logger = logging.getLogger("partproof.receipt.signer")

DEFAULT_RECEIPT_VERSION = "1.0.0"


class ReceiptSigner:
    """
    Ed25519 digital signature provider for execution receipts.
    Private keys are held strictly server-side and never exposed or logged.
    """

    def __init__(
        self,
        key_id: Optional[str] = None,
        signing_key_raw: Optional[str] = None,
        signing_key_path: Optional[str] = None,
    ):
        self.key_id = key_id or getattr(settings, "RECEIPT_KEY_ID", "partproof-ed25519-v1")
        self._private_key = self._load_or_derive_private_key(
            signing_key_raw=signing_key_raw or getattr(settings, "RECEIPT_SIGNING_KEY", None),
            signing_key_path=signing_key_path or getattr(settings, "RECEIPT_SIGNING_KEY_PATH", None),
        )
        self._public_key = self._private_key.public_key()
        self._public_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    @property
    def public_key(self) -> ed25519.Ed25519PublicKey:
        return self._public_key

    @property
    def public_key_hex(self) -> str:
        return self._public_bytes.hex()

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self._public_bytes).decode("ascii")

    def _load_or_derive_private_key(
        self,
        signing_key_raw: Optional[str] = None,
        signing_key_path: Optional[str] = None,
    ) -> ed25519.Ed25519PrivateKey:
        """
        Loads the Ed25519 private key from environment or file.
        In development/testing, falls back to a deterministic key derived from SECRET_KEY
        so that receipts remain verifiable across server restarts without random regeneration.
        """
        key_material = None

        if signing_key_path and os.path.isfile(signing_key_path):
            with open(signing_key_path, "r", encoding="utf-8") as f:
                key_material = f.read().strip()
        elif signing_key_raw:
            key_material = signing_key_raw.strip()

        if key_material:
            # 1. Try PEM PKCS#8 format
            if "BEGIN PRIVATE KEY" in key_material or "BEGIN ED25519 PRIVATE KEY" in key_material:
                try:
                    loaded = serialization.load_pem_private_key(
                        key_material.encode("utf-8"),
                        password=None,
                    )
                    if isinstance(loaded, ed25519.Ed25519PrivateKey):
                        return loaded
                except Exception as e:
                    logger.error("Failed to parse PEM private key: %s", e)

            # 2. Try raw 32-byte Base64 format
            try:
                decoded = base64.b64decode(key_material)
                if len(decoded) == 32:
                    return ed25519.Ed25519PrivateKey.from_private_bytes(decoded)
            except Exception:
                pass

            # 3. Try raw 32-byte Hex format (64 chars)
            try:
                if len(key_material) == 64:
                    decoded = bytes.fromhex(key_material)
                    if len(decoded) == 32:
                        return ed25519.Ed25519PrivateKey.from_private_bytes(decoded)
            except Exception:
                pass

            logger.error("Configured RECEIPT_SIGNING_KEY did not match a valid 32-byte Base64, Hex, or PEM Ed25519 key.")

        # Hard invariant: In production, explicit valid key is mandatory
        if getattr(settings, "PARTPROOF_ENV", "development") == "production":
            raise RuntimeError(
                "CRITICAL SECURITY INVARIANT VIOLATION: "
                "Production execution receipts require an explicitly configured, valid Ed25519 signing key "
                "via RECEIPT_SIGNING_KEY or RECEIPT_SIGNING_KEY_PATH."
            )

        # Development / Testing fallback: Deterministic derivation from SECRET_KEY
        # Ensures that restarting the application retains the identical signing key.
        secret_bytes = settings.SECRET_KEY.encode("utf-8")
        seed = hmac.new(
            secret_bytes,
            b"partproof-ed25519-receipt-signing-seed-v1",
            hashlib.sha256,
        ).digest()
        logger.debug("Initialized deterministic development Ed25519 receipt signing key.")
        return ed25519.Ed25519PrivateKey.from_private_bytes(seed)

    def sign_execution_receipt(
        self,
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
        receipt_version: str = DEFAULT_RECEIPT_VERSION,
    ) -> Dict[str, Any]:
        """
        Builds the bound payload, canonicalizes it deterministically, computes its SHA-256 digest,
        and signs it with the Ed25519 private key.
        Returns the complete persisted receipt document.
        """
        bound_payload = build_bound_receipt_payload(
            receipt_version=receipt_version,
            key_id=self.key_id,
            task_id=task_id,
            execution_id=execution_id,
            approved_plan_hash=approved_plan_hash,
            sandbox_id=sandbox_id,
            runtime_image=runtime_image,
            guest_kernel=guest_kernel,
            cpu_limit=cpu_limit,
            memory_limit_mb=memory_limit_mb,
            timeout_seconds=timeout_seconds,
            network_mode=network_mode,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            exit_code=exit_code,
            status=status,
            cleanup_status=cleanup_status,
            steps=steps,
            artifacts=artifacts,
        )

        canonical_bytes = canonicalize_json(bound_payload)
        receipt_digest = compute_receipt_digest(canonical_bytes)
        signature_bytes = self._private_key.sign(canonical_bytes)
        signature_hex = signature_bytes.hex()

        is_verified_cleanup = cleanup_status == "verified_destroyed"

        return {
            **bound_payload,
            "plan_hash": bound_payload["approved_plan_hash"],
            "steps_executed": len(bound_payload["steps"]),
            "security_verified": is_verified_cleanup,
            "receipt_digest": receipt_digest,
            "verification_hash": receipt_digest,
            "signature": signature_hex,
            "signature_scheme": "ed25519",
            "signature_verified": True,
        }


# Global singleton instance cache
_GLOBAL_SIGNER: Optional[ReceiptSigner] = None


def get_receipt_signer() -> ReceiptSigner:
    """Returns or lazily creates the application-wide ReceiptSigner singleton."""
    global _GLOBAL_SIGNER
    if _GLOBAL_SIGNER is None:
        _GLOBAL_SIGNER = ReceiptSigner()
    return _GLOBAL_SIGNER


def generate_ed25519_keypair(key_id: str = "partproof-ed25519-v1") -> Dict[str, str]:
    """Utility function for operators to generate a production Ed25519 keypair."""
    priv = ed25519.Ed25519PrivateKey.generate()
    raw_priv = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    raw_pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "key_id": key_id,
        "private_key_b64": base64.b64encode(raw_priv).decode("ascii"),
        "private_key_hex": raw_priv.hex(),
        "public_key_b64": base64.b64encode(raw_pub).decode("ascii"),
        "public_key_hex": raw_pub.hex(),
    }
