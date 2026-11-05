import os
import subprocess
import sys
import pytest
from app.services.artifacts.manager import ArtifactManager
from app.services.sandbox.base import ExecutionRequest, SandboxConfig
from app.services.sandbox.microsandbox_adapter import MicrosandboxAdapter

# This test requires Linux, KVM, and explicit opt-in: RUN_MICROSANDBOX_INTEGRATION=1
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MICROSANDBOX_INTEGRATION") != "1" or sys.platform != "linux",
    reason="Requires Linux host with KVM and RUN_MICROSANDBOX_INTEGRATION=1 (run on Vultr VM)",
)


@pytest.mark.asyncio
async def test_real_microsandbox_full_lifecycle(tmp_path):
    """
    Validates true microVM isolation on Vultr Cloud Compute:
    - Independent guest kernel verified against host kernel.
    - Code execution inside microVM.
    - Output artifact generation and retrieval via SDK.
    - Zero outbound network access verified.
    - Guaranteed cleanup verified via 'msb ls'.
    """
    task_id = "vultr-audit-task"
    execution_id = "vultr-run-001"
    sandbox_id = "vultr-real-sb-test"

    config = SandboxConfig(
        sandbox_id=sandbox_id,
        task_id=task_id,
        execution_id=execution_id,
        image="python:3.12-slim",
        cpus=1,
        memory_mb=512,
        network="none",
        timeout_seconds=30.0,
    )

    art_manager = ArtifactManager(base_storage_dir=str(tmp_path / "artifacts"))
    adapter = MicrosandboxAdapter(config, art_manager)

    host_kernel = os.uname().release if hasattr(os, "uname") else "unknown"

    # Python script that generates a CSV artifact and tests network isolation
    test_script = """
import os
import socket

# 1. Output guest environment diagnostics
print("PARTPROOF_REAL_MICROSANDBOX_RUNNING")

# 2. Generate sample audit artifact
os.makedirs("/workspace/output", exist_ok=True)
with open("/workspace/output/bom_audit.csv", "w") as f:
    f.write("part_id,vendor,quote_usd,verified\\nP-501,VultrVendor,42.50,True\\n")

# 3. Verify Network.none() isolation: attempting outbound connection must fail
try:
    s = socket.create_connection(("1.1.1.1", 443), timeout=3.0)
    s.close()
    print("NETWORK_LEAK_DETECTED")
except Exception as e:
    print(f"NETWORK_CONTAINMENT_SUCCESS: {e}")
"""

    async with adapter:
        request = ExecutionRequest(
            code=test_script,
            filename="real_test.py",
            expected_artifacts=["bom_audit.csv"],
        )

        output = await adapter.execute(request)

        # 1. Verification of output and exit status
        assert output.exit_code == 0
        assert "PARTPROOF_REAL_MICROSANDBOX_RUNNING" in output.stdout
        assert "NETWORK_CONTAINMENT_SUCCESS" in output.stdout
        assert "NETWORK_LEAK_DETECTED" not in output.stdout

        # 2. Verification of independent guest kernel
        assert output.guest_kernel is not None
        assert output.guest_kernel != host_kernel, (
            f"Isolation failure: guest kernel ({output.guest_kernel}) matched host ({host_kernel})"
        )

        # 3. Verification of artifact extraction and checksum
        dest_dir = art_manager.get_execution_storage_dir(task_id, execution_id)
        artifacts = await adapter.collect_artifacts(["bom_audit.csv"], str(dest_dir))

        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert artifact.filename == "bom_audit.csv"
        assert os.path.exists(artifact.storage_path)
        assert len(artifact.sha256) == 64
        with open(artifact.storage_path, "r") as f:
            content = f.read()
            assert "VultrVendor" in content

    # 4. Verification of cleanup: sandbox context exited
    assert adapter._is_destroyed is True

    # 5. External confirmation via CLI
    msb_bin = os.environ.get("MSB_BIN", "/home/linuxuser/.local/bin/msb")
    if os.path.exists(msb_bin):
        res = subprocess.run([msb_bin, "ls"], capture_output=True, text=True)
        assert sandbox_id not in res.stdout, f"Sandbox {sandbox_id} leaked in msb ls: {res.stdout}"
