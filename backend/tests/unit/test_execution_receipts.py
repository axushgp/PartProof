import copy
import os
import tempfile
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.entities import Approval, Artifact, Execution, Task, User
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.receipt import (
    ReceiptSigner,
    generate_ed25519_keypair,
    get_receipt_signer,
    verify_execution_receipt,
)
from app.workers.execution_worker import ExecutionWorker
from app.workers.host_lock import HostLock


@pytest.fixture
def sample_receipt():
    signer = get_receipt_signer()
    now = datetime.now(timezone.utc)
    return signer.sign_execution_receipt(
        task_id="task-test-123",
        execution_id="exec-test-456",
        approved_plan_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        sandbox_id="partproof-test-sbx",
        runtime_image="python:3.12-slim",
        guest_kernel="vmlinux-6.1.102-msb",
        cpu_limit=1,
        memory_limit_mb=512,
        timeout_seconds=30,
        network_mode="none",
        started_at=now,
        completed_at=now,
        duration_seconds=5.234,
        exit_code=0,
        status="succeeded",
        cleanup_status="verified_destroyed",
        steps=[
            {
                "step_number": 1,
                "description": "Run security check",
                "status": "succeeded",
                "exit_code": 0,
            }
        ],
        artifacts=[
            {
                "filename": "audit.json",
                "size_bytes": 1024,
                "sha256": "8a25dc25e971e4650b616871b571ddcba26b2f3b128a1c308251a5d2d9bad371",
            }
        ],
    )


def test_valid_signature_verification(sample_receipt):
    result = verify_execution_receipt(sample_receipt)
    assert result.is_valid is True
    assert result.signature_valid is True
    assert result.digest_valid is True
    assert result.cleanup_verified is True
    assert result.plan_hash_valid is True
    assert result.artifacts_valid is True
    assert len(result.errors) == 0
    assert result.receipt_digest == sample_receipt["receipt_digest"]


def test_tampered_receipt_payload_rejection(sample_receipt):
    # Attacker alters runtime image in receipt payload
    tampered = copy.deepcopy(sample_receipt)
    tampered["runtime_image"] = "ubuntu:24.04-insecure"

    result = verify_execution_receipt(tampered)
    assert result.is_valid is False
    assert result.digest_valid is False
    assert result.signature_valid is False
    assert any("Digest integrity failure" in e for e in result.errors)


def test_invalid_signature_rejection(sample_receipt):
    # Attacker replaces signature with signature from another key
    other_key = generate_ed25519_keypair(key_id="rogue-key")
    other_signer = ReceiptSigner(key_id="rogue-key", signing_key_raw=other_key["private_key_b64"])
    other_receipt = other_signer.sign_execution_receipt(
        task_id="task-test-123",
        execution_id="exec-test-456",
        approved_plan_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        sandbox_id="partproof-test-sbx",
        runtime_image="python:3.12-slim",
        guest_kernel="vmlinux-6.1.102-msb",
        cpu_limit=1,
        memory_limit_mb=512,
        timeout_seconds=30,
        network_mode="none",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=5.0,
        exit_code=0,
        status="succeeded",
        cleanup_status="verified_destroyed",
        steps=[],
        artifacts=[],
    )

    tampered = copy.deepcopy(sample_receipt)
    tampered["signature"] = other_receipt["signature"]

    result = verify_execution_receipt(tampered)
    assert result.is_valid is False
    assert result.signature_valid is False
    assert any("signature verification failed" in e.lower() for e in result.errors)


def test_modified_artifact_hash_detection(sample_receipt):
    # Expecting report with different hash
    expected_artifacts = [
        {
            "filename": "audit.json",
            "size_bytes": 1024,
            "sha256": "different_hash_0000000000000000000000000000000000000000000000000000",
        }
    ]

    result = verify_execution_receipt(sample_receipt, expected_artifacts=expected_artifacts)
    assert result.is_valid is False
    assert result.artifacts_valid is False
    assert any("SHA-256 mismatch" in e for e in result.errors)


def test_plan_hash_mismatch(sample_receipt):
    result = verify_execution_receipt(
        sample_receipt,
        expected_plan_hash="mismatched_plan_hash_99999999999999999999999999999999999999999999",
    )
    assert result.is_valid is False
    assert result.plan_hash_valid is False
    assert any("Approved plan hash mismatch" in e for e in result.errors)


def test_cleanup_failure_rejection():
    signer = get_receipt_signer()
    unverified_cleanup_receipt = signer.sign_execution_receipt(
        task_id="task-leak-1",
        execution_id="exec-leak-1",
        approved_plan_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        sandbox_id="partproof-leak-sbx",
        runtime_image="python:3.12-slim",
        guest_kernel="vmlinux-6.1.102-msb",
        cpu_limit=1,
        memory_limit_mb=512,
        timeout_seconds=30,
        network_mode="none",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=5.0,
        exit_code=0,
        status="succeeded",
        cleanup_status="leak_detected",
        steps=[],
        artifacts=[],
    )

    result = verify_execution_receipt(unverified_cleanup_receipt)
    assert result.is_valid is False
    assert result.cleanup_verified is False
    assert any("MicroVM destruction invariant failure" in e for e in result.errors)


def test_failed_execution_with_verified_cleanup():
    signer = get_receipt_signer()
    failed_exec_receipt = signer.sign_execution_receipt(
        task_id="task-fail-1",
        execution_id="exec-fail-1",
        approved_plan_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        sandbox_id="partproof-fail-sbx",
        runtime_image="python:3.12-slim",
        guest_kernel="vmlinux-6.1.102-msb",
        cpu_limit=1,
        memory_limit_mb=512,
        timeout_seconds=30,
        network_mode="none",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=3.2,
        exit_code=1,
        status="failed",
        cleanup_status="verified_destroyed",
        steps=[
            {
                "step_number": 1,
                "description": "Failed guest operation",
                "status": "failed",
                "exit_code": 1,
            }
        ],
        artifacts=[],
    )

    result = verify_execution_receipt(failed_exec_receipt)
    # The receipt itself is valid and digitally signed, teardown was verified destroyed
    assert result.is_valid is True
    assert result.signature_valid is True
    assert result.digest_valid is True
    assert result.cleanup_verified is True
    assert failed_exec_receipt["status"] == "failed"
    assert failed_exec_receipt["exit_code"] == 1


def test_historical_executions_without_receipts():
    # Null receipt
    result = verify_execution_receipt(None)
    assert result.is_valid is False
    assert result.signature_valid is False
    assert any("empty, missing, or malformed" in e for e in result.errors)


def test_persistent_signing_key_across_application_restarts():
    # Two separate instances sharing SECRET_KEY (simulating server restart)
    signer1 = ReceiptSigner()
    signer2 = ReceiptSigner()

    assert signer1.public_key_hex == signer2.public_key_hex
    assert signer1.key_id == signer2.key_id

    receipt = signer1.sign_execution_receipt(
        task_id="t1",
        execution_id="e1",
        approved_plan_hash="h1",
        sandbox_id="s1",
        runtime_image="python:3.12-slim",
        guest_kernel="k1",
        cpu_limit=1,
        memory_limit_mb=512,
        timeout_seconds=30,
        network_mode="none",
        started_at="2026-11-08T10:00:00Z",
        completed_at="2026-11-08T10:00:05Z",
        duration_seconds=5.0,
        exit_code=0,
        status="succeeded",
        cleanup_status="verified_destroyed",
        steps=[],
        artifacts=[],
    )

    # Verification using signer2's public key succeeds
    res = verify_execution_receipt(receipt, public_key=signer2.public_key)
    assert res.is_valid is True
    assert res.signature_valid is True


@pytest.mark.asyncio
async def test_api_system_verification_endpoints(client: AsyncClient, sample_receipt):
    # 1. GET /api/v1/system/verification-key
    key_resp = await client.get("/api/v1/system/verification-key")
    assert key_resp.status_code == 200
    key_data = key_resp.json()
    assert "public_key_hex" in key_data
    assert "public_key_b64" in key_data
    assert key_data["algorithm"] == "Ed25519"
    assert "key_id" in key_data

    # 2. POST /api/v1/system/receipt-verify with valid receipt
    verify_resp = await client.post(
        "/api/v1/system/receipt-verify",
        json={"receipt": sample_receipt},
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["is_valid"] is True
    assert verify_data["signature_valid"] is True
    assert verify_data["digest_valid"] is True
    assert verify_data["cleanup_verified"] is True

    # 3. POST /api/v1/system/receipt-verify with tampered receipt
    tampered = copy.deepcopy(sample_receipt)
    tampered["runtime_image"] = "tampered:image"
    tampered_resp = await client.post(
        "/api/v1/system/receipt-verify",
        json={"receipt": tampered},
    )
    assert tampered_resp.status_code == 200
    tampered_data = tampered_resp.json()
    assert tampered_data["is_valid"] is False
    assert tampered_data["digest_valid"] is False


@pytest.mark.asyncio
async def test_worker_generates_signed_receipt_on_verified_cleanup(db_session: AsyncSession):
    # Verify that ExecutionWorker actually generates and persists signed receipt_json
    class MockSessionFactory:
        def __init__(self, session: AsyncSession):
            self.session = session
        def __call__(self):
            return self
        async def __aenter__(self):
            return self.session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    user = User(email="receipt-worker@partproof.io", password_hash="dummy")
    db_session.add(user)
    await db_session.flush()

    plan_dict = {
        "title": "Receipt Generation Plan",
        "summary": "Validates line items against contract catalog",
        "reasoning_summary": "Systematic audit",
        "steps": [
            {
                "step_id": "step_1",
                "description": "Execute audit script",
                "execution_type": "python",
                "code": "print('Receipt worker test success')\n",
            }
        ],
        "required_capabilities": ["file_read", "file_write"],
        "network_required": False,
        "success_criteria": ["Receipt generated"],
        "expected_artifacts": ["audit_summary.csv"],
    }
    plan_hash = compute_plan_hash(plan_dict)

    task = Task(user_id=user.id, title="Receipt Worker Task", description="Testing signed receipt generation", status="queued")
    db_session.add(task)
    await db_session.flush()

    approval = Approval(
        task_id=task.id,
        approved_by=user.email,
        approved_plan_hash=plan_hash,
        decision="approved",
    )
    db_session.add(approval)
    await db_session.flush()

    execution = Execution(
        task_id=task.id,
        approval_id=approval.id,
        plan_hash=plan_hash,
        plan_snapshot=plan_dict,
        status="queued",
        runtime_image="python:3.12-slim",
        cpu_limit=1,
        memory_limit_mb=512,
        network_mode="none",
        timeout_seconds=30,
    )
    db_session.add(execution)
    await db_session.commit()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        lock_file = f.name

    try:
        worker = ExecutionWorker(
            session_factory=MockSessionFactory(db_session),
            worker_id="worker-receipt-test",
        )
        worker.host_lock = HostLock(lock_file)
        await worker.run(run_once=True)

        await db_session.refresh(execution)
        assert execution.status == "succeeded"
        assert execution.cleanup_status == "verified_destroyed"

        # Verify cryptographic receipt was generated and persisted
        assert execution.receipt_json is not None
        receipt = execution.receipt_json
        assert receipt["task_id"] == task.id
        assert receipt["execution_id"] == execution.id
        assert receipt["signature"] is not None
        assert receipt["receipt_digest"] is not None
        assert receipt["cleanup_status"] == "verified_destroyed"
        assert receipt["security_verified"] is True

        # Independently verify the generated receipt
        verification = verify_execution_receipt(receipt)
        assert verification.is_valid is True
        assert verification.signature_valid is True
        assert verification.digest_valid is True
    finally:
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass


def test_rfc8785_standards_conformance_vectors():
    """
    Validates adherence to RFC 8785 (JSON Canonicalization Scheme - JCS) standards:
    1. Whitespace elimination
    2. Numbers: integer floats (1.0 -> 1), -0.0 -> 0, ECMAScript scientific notation thresholds
    3. Object key sorting by UTF-16 code units (surrogate pairs sort before higher BMP code points)
    4. Unescaped UTF-8 string encoding (ensure_ascii=False)
    """
    from app.services.receipt.canonical import canonicalize_json

    # Vector 1: Whitespace and key sorting
    res1 = canonicalize_json({"z": 1, "a": 2, "m": 3})
    assert res1 == b'{"a":2,"m":3,"z":1}'

    # Vector 2: Number serialization per ECMAScript / RFC 8785 Section 3.2.2.3
    res2 = canonicalize_json({
        "integer": 42,
        "float_as_int": 1.0,
        "negative_zero": -0.0,
        "decimal": 5.234,
        "small_threshold": 1e-6,
        "scientific_threshold": 1e21,
    })
    # Float 1.0 must be serialized as 1, -0.0 as 0, 1e-6 as 0.000001, 1e21 as 1e+21
    decoded2 = res2.decode("utf-8")
    assert '"float_as_int":1' in decoded2
    assert '"negative_zero":0' in decoded2
    assert '"small_threshold":0.000001' in decoded2
    assert '"scientific_threshold":1e+21' in decoded2

    # Vector 3: UTF-16 code unit ordering with non-BMP characters
    # In UTF-16, \U00010000 is represented as surrogate pair 0xD800, 0xDC00.
    # Since 0xD800 < 0xFFFF, \U00010000 must sort BEFORE \uFFFF.
    res3 = canonicalize_json({"\uffff": "high_bmp", "\U00010000": "supplementary"})
    assert res3 == b'{"\xf0\x90\x80\x80":"supplementary","\xef\xbf\xbf":"high_bmp"}'

    # Vector 4: Unicode string preservation
    res4 = canonicalize_json({"emoji": "\U0001f512", "text": "PartProof \u00e4\u00f6\u00fc"})
    decoded4 = res4.decode("utf-8")
    assert '\U0001f512' in decoded4
    assert '\u00e4\u00f6\u00fc' in decoded4
    assert "\\u" not in decoded4
