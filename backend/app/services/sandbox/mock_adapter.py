import asyncio
import time
from typing import List, Optional, TYPE_CHECKING
from app.services.sandbox.base import (
    ArtifactMetadata,
    BaseSandboxAdapter,
    ExecutionOutput,
    ExecutionRequest,
    SandboxCleanupError,
    SandboxConfig,
    SandboxTimeoutError,
)

if TYPE_CHECKING:
    from app.services.artifacts.manager import ArtifactManager


class MockSandboxAdapter(BaseSandboxAdapter):
    """
    Deterministic simulated sandbox adapter for local Windows/Mac development and test suites.
    CRITICAL SAFETY GUARANTEE: Never executes arbitrary user code on the host OS.
    Produces deterministic simulated outputs marked explicitly with execution_mode='mock'.
    """

    def __init__(self, config: SandboxConfig, artifact_manager: Optional["ArtifactManager"] = None):
        super().__init__(config)
        if artifact_manager is None:
            from app.services.artifacts.manager import ArtifactManager
            self.artifact_manager = ArtifactManager()
        else:
            self.artifact_manager = artifact_manager
            
        self.simulated_guest_kernel = "simulated-kernel-6.12.113-mock"
        self._last_request: Optional[ExecutionRequest] = None
        self.executed_requests: List[ExecutionRequest] = []

    async def create(self) -> str:
        """Simulates microVM provisioning."""
        self._provision_attempted = True
        if self._is_created:
            return self.config.sandbox_id

        if (
            getattr(self, "_simulate_provision_timeout", False)
            or "SIMULATE_PROVISION_TIMEOUT" in self.config.sandbox_id
        ):
            await asyncio.sleep(0.3)
            raise SandboxTimeoutError(
                "Simulated provisioning deadline exceeded.",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        await asyncio.sleep(0.01)
        self._is_created = True
        return self.config.sandbox_id

    async def execute(self, request: ExecutionRequest) -> ExecutionOutput:
        """
        Simulates code execution without running any untrusted code on the host.
        Recognizes explicit deterministic test markers inside the code string.
        """
        if not self._is_created:
            await self.create()

        self._last_request = request
        self.executed_requests.append(request)
        self.artifact_manager.validate_source_code(request.code)

        start_time = time.monotonic()

        # 1. Deterministic simulation: Source transfer timeout simulation
        if "SIMULATE_SOURCE_TRANSFER_TIMEOUT" in request.code:
            raise SandboxTimeoutError(
                f"Simulated source transfer deadline ({request.timeout_seconds}s) exceeded.",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        # 2. Deterministic simulation: Execution timeout simulation
        if "SIMULATE_TIMEOUT" in request.code or (request.timeout_seconds and request.timeout_seconds < 0.05):
            elapsed = 0.05
            raise SandboxTimeoutError(
                f"Simulated execution deadline ({self.config.timeout_seconds}s) exceeded.",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        # 2. Deterministic simulation: Failure simulation
        if (
            "SIMULATE_ERROR" in request.code
            or "raise " in request.code
            or "sys.exit(1)" in request.code
            or "def invalid syntax" in request.code
        ):
            await asyncio.sleep(0.02)
            elapsed = time.monotonic() - start_time
            return ExecutionOutput(
                stdout="[MOCK SANDBOX] Initializing isolated execution environment...\n[MOCK SANDBOX] Executing task script...",
                stderr="Traceback (most recent call last):\n  File 'audit_task.py', line 8, in <module>\nValueError: Simulated error trigger detected inside mock adapter\n",
                exit_code=1,
                duration_seconds=round(elapsed, 4),
                timed_out=False,
                guest_kernel=self.simulated_guest_kernel,
            )

        # 3. Standard successful deterministic execution simulation
        if "SIMULATE_SLEEP" in request.code:
            await asyncio.sleep(0.6)
        else:
            await asyncio.sleep(0.02)
        elapsed = time.monotonic() - start_time

        stdout_text = (
            f"[MOCK SANDBOX] Running in deterministic simulated environment (execution_mode=mock)\n"
            f"[MOCK SANDBOX] Sandbox ID: {self.config.sandbox_id}\n"
            f"[MOCK SANDBOX] Guest Kernel: {self.simulated_guest_kernel}\n"
            f"[MOCK SANDBOX] Resource Bounds: {self.config.cpus} vCPU, {self.config.memory_mb} MB RAM\n"
            f"[MOCK SANDBOX] Network: {self.config.network}\n"
            f"[MOCK SANDBOX] Execution completed with status 0."
        )

        return ExecutionOutput(
            stdout=stdout_text,
            stderr="",
            exit_code=0,
            duration_seconds=round(elapsed, 4),
            timed_out=False,
            guest_kernel=self.simulated_guest_kernel,
        )

    async def collect_artifacts(self, expected_names: List[str], destination_dir: str) -> List[ArtifactMetadata]:
        """
        Generates simulated output artifacts corresponding to expected filenames.
        """
        if "SIMULATE_MISSING_ARTIFACT" in getattr(self._last_request, "code", ""):
            raise ArtifactCollectionError(
                "Simulated missing artifact failure during extraction",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        collected: List[ArtifactMetadata] = []
        if not expected_names:
            return collected

        for raw_name in expected_names:
            safe_name = self.artifact_manager.sanitize_and_validate_filename(raw_name)
            
            if safe_name == "bom_audit.csv":
                content = (
                    "item_id,part_number,description,category,required_qty,uom,target_price\n"
                    "bom-001,BRG-6204-2RS,Deep Groove Ball Bearing,Bearings,200,pcs,12.00\n"
                    "bom-002,FST-M8-ST-88,Hex Flange Bolt M8x35,Fasteners,800,pcs,0.45\n"
                    "bom-003,CTR-BLDC-72V,72V 150A BLDC Controller,Electronics,100,pcs,185.00\n"
                ).encode("utf-8")
            elif safe_name == "supplier_comparison.csv":
                content = (
                    "supplier_id,supplier_name,headline_price,moq_excess_cost,freight_cost,tax_amount,true_landed_cost,is_compliant,compliance_status,commercial_status\n"
                    "sup-b,Beacon Precision Dynamics,27948.00,0.00,0.00,5030.64,32978.64,YES,COMPLIANT,RECOMMENDED\n"
                    "sup-a,Apex Industrial Components,25680.00,2920.00,1850.00,5481.00,35931.00,YES,COMPLIANT,EXPENSIVE\n"
                    "sup-c,Crestline Manufacturing Group,26860.00,0.00,0.00,4834.80,31694.80,NO,DISQUALIFIED,DISQUALIFIED\n"
                ).encode("utf-8")
            elif safe_name == "discrepancy_register.csv":
                content = (
                    "discrepancy_id,supplier,category,severity,item,financial_impact,status\n"
                    "disc-001,Apex Industrial Components,MOQ-induced excess purchases,CRITICAL,BRG-6204-2RS,2850.00,CONFIRMED\n"
                    "disc-002,Apex Industrial Components,MOQ-induced excess purchases,WARNING,FST-M8-ST-88,70.00,CONFIRMED\n"
                    "disc-003,Apex Industrial Components,Missing freight or tooling charges,CRITICAL,LOGISTICS,1850.00,CONFIRMED\n"
                    "disc-004,Crestline Manufacturing Group,Specification substitutions,CRITICAL,CTR-BLDC-48V,0.00,CONFIRMED\n"
                    "disc-005,Crestline Manufacturing Group,Lead-time differences,CRITICAL,SCHEDULE,0.00,CONFIRMED\n"
                ).encode("utf-8")
            elif safe_name == "procurement_decision.json":
                content = (
                    '{\n  "engine": "PartProof Procurement Intelligence",\n  "recommended_winner": "Beacon Precision Dynamics",\n  "recommended_supplier_id": "sup-b",\n  "true_landed_cost": 32978.64,\n  "net_savings": 2952.36\n}\n'
                ).encode("utf-8")
            elif safe_name == "negotiation_brief.md":
                content = (
                    "# PARTPROOF PROCUREMENT FORENSICS - NEGOTIATION BRIEF\n\n"
                    "## 1. Executive Summary\n"
                    "Beacon Precision Dynamics is the recommended awardee at $32,978.64 true landed cost.\n\n"
                    "## 2. Supplier Vulnerabilities & Forensic Leverage\n"
                    "- Apex Industrial Components: Trapped by $2,920 total MOQ excess ($2,850 bearing + $70 bolt) and $1,850 excluded freight.\n"
                    "- Crestline Manufacturing Group: Disqualified due to 48V motor controller substitution and 42-day lead time.\n\n"
                    "## 3. Counter-Offer Potential\n"
                    "If Apex waives $2,920 MOQ excess and $1,850 freight, revised landed cost is $30,302.40 ($2,676.24 net savings vs Beacon).\n"
                ).encode("utf-8")
            elif safe_name.endswith(".csv"):
                content = (
                    "line_item,part_number,description,qty,unit_cost,extended_cost,discrepancy\n"
                    "1,P-8801,Hex Cap Screw M8x30,500,0.45,225.00,0.00\n"
                    "2,P-8802,Structural Flange Bracket,100,18.50,1850.00,12.50\n"
                    "3,P-8803,EPDM Gasket Seal,200,3.20,640.00,0.00\n"
                ).encode("utf-8")
            elif safe_name.endswith(".json"):
                content = (
                    '{"audit_id": "audit-mock-01", "total_cost": 2715.00, "verified": true, "variance": 12.50}\n'
                ).encode("utf-8")
            else:
                content = f"PartProof Audit Log - Output for {safe_name}\nStatus: Verified\n".encode("utf-8")

            metadata = self.artifact_manager.store_artifact_from_bytes(
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
                filename=safe_name,
                data=content,
            )
            collected.append(metadata)

        self.artifact_manager.validate_artifact_collection_limits(collected)
        return collected

    async def destroy(self) -> str:
        """Simulates microVM destruction and verification."""
        if (
            getattr(self, "_simulate_cleanup_timeout", False)
            or "SIMULATE_CLEANUP_TIMEOUT" in getattr(self._last_request, "code", "")
        ):
            await asyncio.sleep(0.3)
            raise SandboxTimeoutError(
                "Simulated timeout during sandbox cleanup verification",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        if not self._is_created:
            return "verified_destroyed"

        if "SIMULATE_CLEANUP_FAILURE" in getattr(self._last_request, "code", ""):
            raise SandboxCleanupError(
                "Simulated failure during sandbox cleanup verification",
                task_id=self.config.task_id,
                execution_id=self.config.execution_id,
            )

        self._is_destroyed = True
        return "verified_destroyed"
