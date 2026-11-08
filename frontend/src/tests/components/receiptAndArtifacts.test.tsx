import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ExecutionReceiptCard,
  formatCleanupStatus,
  getVerificationStatus,
  resolveApprovedPlanHash,
} from "@/components/artifacts/execution-receipt";
import { ArtifactsTable } from "@/components/artifacts/artifacts-table";
import {
  ApprovalRead,
  ArtifactRead,
  ExecutionRead,
  ExecutionReceipt,
  TaskPlanRead,
} from "@/types/backend";

describe("Execution Receipt & Artifacts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockReceipt: ExecutionReceipt = {
    task_id: "task-100",
    execution_id: "exec-100",
    sandbox_id: "guest-microsandbox-prod-42",
    status: "succeeded",
    runtime_image: "python:3.12-slim",
    guest_kernel: "vmlinux-6.6",
    cpu_limit: 1,
    memory_limit_mb: 512,
    network_mode: "none",
    plan_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    policy_name: "default-sandbox-v1",
    policy_version: "1.0",
    steps_executed: 1,
    steps_failed: 0,
    exit_code: 0,
    cleanup_status: "verified_destroyed",
    duration_seconds: 5.2,
    started_at: "2026-03-24T12:00:00Z",
    completed_at: "2026-03-24T12:00:05Z",
    verification_hash: "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
    security_verified: true,
    signature: "sig_7f83b1657ff1fc53",
    artifacts: [],
  };

  const mockExecution: ExecutionRead = {
    id: "exec-100",
    task_id: "task-100",
    status: "succeeded",
    worker_id: "worker-node-alpha",
    sandbox_id: "guest-microsandbox-prod-42",
    runtime_image: "python:3.12-slim",
    cpu_limit: 1,
    memory_limit_mb: 512,
    network_mode: "none",
    cleanup_status: "verified_destroyed",
    started_at: "2026-03-24T12:00:00Z",
    completed_at: "2026-03-24T12:00:05Z",
    duration_seconds: 5.2,
    receipt_json: mockReceipt,
    steps: [],
    artifacts: [],
    created_at: "2026-03-24T11:59:59Z",
    updated_at: "2026-03-24T12:00:05Z",
  };

  describe("formatCleanupStatus Helper", () => {
    it("formats verified_destroyed correctly", () => {
      const res = formatCleanupStatus("verified_destroyed");
      expect(res.label).toBe("Verified Destruction");
      expect(res.colorClass).toContain("emerald");
    });

    it("formats leak_detected correctly", () => {
      const res = formatCleanupStatus("leak_detected");
      expect(res.label).toBe("Leak Detected");
      expect(res.colorClass).toContain("rose");
    });

    it("formats pending_cleanup correctly", () => {
      const res = formatCleanupStatus("pending_cleanup");
      expect(res.label).toBe("Pending Cleanup");
      expect(res.colorClass).toContain("amber");
    });

    it("formats known backend values (untracked, timeout, failed)", () => {
      expect(formatCleanupStatus("untracked").label).toBe("Untracked");
      expect(formatCleanupStatus("timeout").label).toBe("Cleanup Timeout");
      expect(formatCleanupStatus("failed").label).toBe("Cleanup Failed");
    });

    it("falls back to neutral label and color for unknown cleanup status", () => {
      const res = formatCleanupStatus("custom_quarantine_mode");
      expect(res.label).toBe("custom_quarantine_mode");
      expect(res.colorClass).toContain("zinc-400");
    });

    it("handles null or undefined cleanup status safely", () => {
      expect(formatCleanupStatus(null).label).toBe("Unknown");
      expect(formatCleanupStatus(undefined).label).toBe("Unknown");
    });
  });

  describe("getVerificationStatus Helper", () => {
    it("returns LEAK DETECTED / RECONCILIATION REQUIRED when cleanup is leak_detected", () => {
      const res = getVerificationStatus({ cleanupStatus: "leak_detected" });
      expect(res.label).toBe("LEAK DETECTED / RECONCILIATION REQUIRED");
      expect(res.variant).toBe("destructive");
    });

    it("returns LEAK DETECTED / RECONCILIATION REQUIRED when execution is needs_reconciliation", () => {
      const res = getVerificationStatus({ executionStatus: "needs_reconciliation" });
      expect(res.label).toBe("LEAK DETECTED / RECONCILIATION REQUIRED");
      expect(res.variant).toBe("destructive");
    });

    it("returns VERIFICATION FAILED / UNVERIFIED when security_verified is explicitly false", () => {
      const res = getVerificationStatus({
        receipt: { ...mockReceipt, security_verified: false },
        cleanupStatus: "verified_destroyed",
      });
      expect(res.label).toBe("VERIFICATION FAILED / UNVERIFIED");
      expect(res.variant).toBe("destructive");
    });

    it("returns SECURITY VERIFIED when security_verified is explicitly true", () => {
      const res = getVerificationStatus({
        receipt: mockReceipt,
        cleanupStatus: "verified_destroyed",
      });
      expect(res.label).toBe("SECURITY VERIFIED");
      expect(res.variant).toBe("success");
    });

    it("returns UNVERIFIED when receipt is missing (never infers verification or leak)", () => {
      const res = getVerificationStatus({
        receipt: null,
        cleanupStatus: "verified_destroyed",
      });
      expect(res.label).toBe("UNVERIFIED");
      expect(res.variant).toBe("secondary");
    });

    it("returns UNVERIFIED when security_verified field is missing from receipt", () => {
      const receiptNoField = { ...mockReceipt, security_verified: undefined as unknown as boolean };
      const res = getVerificationStatus({
        receipt: receiptNoField,
        cleanupStatus: "verified_destroyed",
      });
      expect(res.label).toBe("UNVERIFIED");
      expect(res.variant).toBe("secondary");
    });
  });

  describe("resolveApprovedPlanHash Helper", () => {
    const approvedPlan: TaskPlanRead = {
      id: "plan-200",
      task_id: "task-100",
      model: "glm-5.3",
      plan_json: {
        title: "New Approved Plan",
        summary: "Plan summary",
        reasoning_summary: "Reasoning summary",
        steps: [],
        required_capabilities: [],
        network_required: false,
        success_criteria: [],
        expected_artifacts: [],
      },
      plan_hash: "2222222222222222222222222222222222222222222222222222222222222222",
      policy_result: {
        allowed: true,
        policy_name: "default-sandbox-v1",
        policy_version: "1.0",
        cpu_limit: 1,
        memory_limit_mb: 512,
        timeout_seconds: 30,
        network_mode: "none",
      },
      policy_version: "1.0",
      approval_status: "approved",
      created_at: "2026-03-24T12:00:00Z",
    };

    it("flags mismatch when task contains an older rejected approval and a newer approved plan with mismatched hash", () => {
      const olderRejectedApproval: ApprovalRead = {
        id: "appr-old-1",
        task_id: "task-100",
        decision: "rejected",
        approved_plan_hash: "1111111111111111111111111111111111111111111111111111111111111111",
        reason: "Disallowed command detected in previous plan iteration",
        created_at: "2026-03-24T11:00:00Z",
      };

      const result = resolveApprovedPlanHash({
        plan: approvedPlan,
        latestApproval: olderRejectedApproval,
      });

      expect(result.hasMismatch).toBe(true);
      expect(result.authoritativePlanHash).toBeNull();
      expect(result.warningMessage).toContain("Plan approval integrity warning");
      expect(result.warningMessage).toContain(approvedPlan.plan_hash.slice(0, 16));
      expect(result.warningMessage).toContain(olderRejectedApproval.approved_plan_hash!.slice(0, 16));
    });

    it("flags mismatch when latest approval reflects historical rejection even without approved_plan_hash", () => {
      const rejectedNoHash: ApprovalRead = {
        id: "appr-old-2",
        task_id: "task-100",
        decision: "rejected",
        approved_plan_hash: null,
        reason: "Operator rejected plan manually",
        created_at: "2026-03-24T11:00:00Z",
      };

      const result = resolveApprovedPlanHash({
        plan: approvedPlan,
        latestApproval: rejectedNoHash,
      });

      expect(result.hasMismatch).toBe(true);
      expect(result.authoritativePlanHash).toBeNull();
      expect(result.warningMessage).toContain("Plan approval association warning");
    });

    it("resolves authoritative plan hash when approval record matches the active plan hash", () => {
      const matchingApproval: ApprovalRead = {
        id: "appr-valid",
        task_id: "task-100",
        decision: "approved",
        approved_plan_hash: approvedPlan.plan_hash,
        reason: "Operator approved verified plan",
        created_at: "2026-03-24T12:05:00Z",
      };

      const result = resolveApprovedPlanHash({
        plan: approvedPlan,
        latestApproval: matchingApproval,
      });

      expect(result.hasMismatch).toBe(false);
      expect(result.authoritativePlanHash).toBe(approvedPlan.plan_hash);
      expect(result.warningMessage).toBeNull();
    });

    it("does not select older approval hash when current plan is not approved (pending review)", () => {
      const pendingPlan: TaskPlanRead = { ...approvedPlan, approval_status: "pending" };
      const olderApproval: ApprovalRead = {
        id: "appr-old-3",
        task_id: "task-100",
        decision: "rejected",
        approved_plan_hash: "1111111111111111111111111111111111111111111111111111111111111111",
        created_at: "2026-03-24T11:00:00Z",
      };

      const result = resolveApprovedPlanHash({
        plan: pendingPlan,
        latestApproval: olderApproval,
      });

      expect(result.hasMismatch).toBe(false);
      expect(result.authoritativePlanHash).toBeNull();
      expect(result.isApproved).toBe(false);
    });
  });

  describe("ExecutionReceiptCard Component", () => {
    it("renders cryptographic receipt with verified badge, Ed25519 signature status, and evidence parameters when receipt is present", () => {
      render(
        <ExecutionReceiptCard
          receipt={{
            ...mockReceipt,
            key_id: "partproof-ed25519-v1",
            signature_scheme: "ed25519",
            signature_verified: true,
          }}
          execution={mockExecution}
          approvedPlanHash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        />
      );

      expect(screen.getByText("Cryptographic Execution Receipt")).toBeInTheDocument();
      expect(screen.getByText("SECURITY VERIFIED")).toBeInTheDocument();
      expect(screen.getByText("Cryptographic Receipt Available")).toBeInTheDocument();
      expect(screen.getByText("Ed25519 Signature Verified")).toBeInTheDocument();
      expect(screen.getByText(/Algorithm: ED25519 · Key ID: partproof-ed25519-v1/)).toBeInTheDocument();
      expect(screen.getByText("exec-100")).toBeInTheDocument();
      expect(screen.getByText("guest-microsandbox-prod-42")).toBeInTheDocument();
      expect(screen.getByText("vmlinux-6.6")).toBeInTheDocument();
      expect(screen.getByText("1 vCPU / 512 MB")).toBeInTheDocument();
      expect(screen.getByText(/none/i)).toBeInTheDocument();
      expect(screen.getByText("5.2s")).toBeInTheDocument();
      expect(screen.getByText("0")).toBeInTheDocument();
      expect(screen.getByText("Exit Code")).toBeInTheDocument();
      expect(
        screen.getByText("7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069")
      ).toBeInTheDocument();
    });

    it("renders Signature Invalid badge and VERIFICATION FAILED when signature_verified is false", () => {
      render(
        <ExecutionReceiptCard
          receipt={{
            ...mockReceipt,
            signature_verified: false,
          }}
          execution={mockExecution}
        />
      );

      expect(screen.getByText("Signature Invalid")).toBeInTheDocument();
      expect(screen.getByText("VERIFICATION FAILED / UNVERIFIED")).toBeInTheDocument();
    });

    it("renders Legacy execution: receipt unavailable notice when receipt is null", () => {
      render(
        <ExecutionReceiptCard
          receipt={null}
          execution={mockExecution}
        />
      );

      expect(screen.getByText(/Legacy execution: receipt unavailable/)).toBeInTheDocument();
    });

    it("copies the verification hash to clipboard when copy button is clicked", async () => {
      const user = userEvent.setup();
      render(<ExecutionReceiptCard receipt={mockReceipt} execution={mockExecution} />);

      const copyBtn = screen.getByRole("button", { name: /Copy/i });
      await user.click(copyBtn);

      await waitFor(async () => {
        expect(await navigator.clipboard.readText()).toBe(
          "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069"
        );
        expect(screen.getByText("Copied")).toBeInTheDocument();
      });
    });

    it("handles missing receipt: renders UNVERIFIED badge, backend gap notice, and no fabricated hash", () => {
      const executionNoReceipt: ExecutionRead = {
        ...mockExecution,
        receipt_json: null,
      };

      render(
        <ExecutionReceiptCard
          receipt={null}
          execution={executionNoReceipt}
          approvedPlanHash="approved-plan-hash-12345"
        />
      );

      // Must display UNVERIFIED badge
      expect(screen.getByText("UNVERIFIED")).toBeInTheDocument();
      // Must NOT display LEAK DETECTED merely because receipt is missing
      expect(screen.queryByText(/LEAK DETECTED/i)).not.toBeInTheDocument();
      // Must NOT display SECURITY VERIFIED
      expect(screen.queryByText("SECURITY VERIFIED")).not.toBeInTheDocument();

      // Displays clear "Receipt not generated by backend" message
      expect(
        screen.getByText(/Receipt not generated by backend \(Execution receipt unavailable\)/i)
      ).toBeInTheDocument();

      // Displays operational records without fabricated verification hash
      expect(screen.getByText("exec-100")).toBeInTheDocument();
      expect(screen.getByText("guest-microsandbox-prod-42")).toBeInTheDocument();
      expect(
        screen.getByText(/Unavailable \(Receipt not generated by backend\)/i)
      ).toBeInTheDocument();

      // Displays approved plan hash from task detail
      expect(screen.getByText(/approved-plan-ha\.\.\./i)).toBeInTheDocument();

      // Copy button for verification hash must not exist
      expect(screen.queryByRole("button", { name: /Copy/i })).not.toBeInTheDocument();
    });

    it("handles missing security_verified field on receipt: renders UNVERIFIED badge", () => {
      const receiptNoField = {
        ...mockReceipt,
        security_verified: undefined as unknown as boolean,
      };

      render(
        <ExecutionReceiptCard
          receipt={receiptNoField}
          execution={mockExecution}
        />
      );

      expect(screen.getByText("UNVERIFIED")).toBeInTheDocument();
      expect(screen.queryByText("SECURITY VERIFIED")).not.toBeInTheDocument();
      expect(screen.queryByText(/LEAK DETECTED/i)).not.toBeInTheDocument();
    });

    it("handles explicit security_verified === false: renders VERIFICATION FAILED / UNVERIFIED", () => {
      const failedReceipt: ExecutionReceipt = {
        ...mockReceipt,
        security_verified: false,
      };

      render(
        <ExecutionReceiptCard
          receipt={failedReceipt}
          execution={mockExecution}
        />
      );

      expect(screen.getByText("VERIFICATION FAILED / UNVERIFIED")).toBeInTheDocument();
      expect(screen.queryByText("SECURITY VERIFIED")).not.toBeInTheDocument();
      expect(screen.queryByText(/LEAK DETECTED/i)).not.toBeInTheDocument();
    });

    it("handles explicit cleanup leak: renders LEAK DETECTED / RECONCILIATION REQUIRED badge and label", () => {
      const leakyExecution: ExecutionRead = {
        ...mockExecution,
        cleanup_status: "leak_detected",
        status: "needs_reconciliation",
      };

      render(
        <ExecutionReceiptCard
          receipt={null}
          execution={leakyExecution}
        />
      );

      expect(screen.getByText("LEAK DETECTED / RECONCILIATION REQUIRED")).toBeInTheDocument();
      expect(screen.getByText("Leak Detected")).toBeInTheDocument();
    });

    it("handles pending_cleanup status: displays Pending Cleanup in teardown status", () => {
      const pendingExecution: ExecutionRead = {
        ...mockExecution,
        cleanup_status: "pending_cleanup",
      };

      render(
        <ExecutionReceiptCard
          receipt={null}
          execution={pendingExecution}
        />
      );

      expect(screen.getByText("Pending Cleanup")).toBeInTheDocument();
    });

    it("handles verified_destroyed status: displays Verified Destruction in teardown status", () => {
      const verifiedExecution: ExecutionRead = {
        ...mockExecution,
        cleanup_status: "verified_destroyed",
      };

      render(
        <ExecutionReceiptCard
          receipt={null}
          execution={verifiedExecution}
        />
      );

      expect(screen.getByText("Verified Destruction")).toBeInTheDocument();
    });

    it("handles unknown cleanup status: renders neutral fallback label", () => {
      const unknownCleanupExecution: ExecutionRead = {
        ...mockExecution,
        cleanup_status: "custom_hypervisor_state_99",
      };

      render(
        <ExecutionReceiptCard
          receipt={null}
          execution={unknownCleanupExecution}
        />
      );

      expect(screen.getByText("custom_hypervisor_state_99")).toBeInTheDocument();
    });

    it("renders integrity warning and Discrepancy indicator when planHashMismatch is true", () => {
      render(
        <ExecutionReceiptCard
          receipt={mockReceipt}
          execution={mockExecution}
          planHashMismatch={true}
          planHashWarning="Plan approval hash mismatch detected."
        />
      );

      expect(
        screen.getByText("Integrity Warning: Approval Record Hash Discrepancy")
      ).toBeInTheDocument();
      expect(
        screen.getByText("Plan approval hash mismatch detected.")
      ).toBeInTheDocument();
      expect(screen.getByText("Discrepancy (Hash Mismatch)")).toBeInTheDocument();
    });

    it("clearly distinguishes Approved Plan Hash from Execution Verification Digest", () => {
      render(
        <ExecutionReceiptCard
          receipt={mockReceipt}
          execution={mockExecution}
          approvedPlanHash="1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff"
        />
      );

      // Verify label for approved plan hash
      expect(screen.getByText("Approved Plan Hash")).toBeInTheDocument();
      expect(screen.getByText(/1111222233334444\.\.\./)).toBeInTheDocument();

      // Verify label for execution verification digest
      expect(
        screen.getByText(/Execution Verification Digest \(Distinct from Plan Hash\)/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText("7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069")
      ).toBeInTheDocument();
    });
  });

  describe("ArtifactsTable Component", () => {
    const mockArtifacts: ArtifactRead[] = [
      {
        id: "art-1",
        execution_id: "exec-100",
        task_id: "task-100",
        filename: "audit-report.json",
        size_bytes: 4096,
        sha256: "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
        mime_type: "application/json",
        created_at: "2026-03-24T12:00:05Z",
      },
    ];

    it("renders authenticated download info note and download action button for each artifact", () => {
      render(<ArtifactsTable artifacts={mockArtifacts} />);

      expect(screen.getByText(/Authenticated Artifact Downloads:/i)).toBeInTheDocument();
      expect(screen.getByText(/Host Bound Verified/i)).toBeInTheDocument();

      const downloadButton = screen.getByRole("button", { name: /Download/i });
      expect(downloadButton).toBeInTheDocument();
      expect(downloadButton).toHaveAttribute("title", "Download audit-report.json");
    });

    it("triggers file download via authenticated BFF route when Download button is clicked", async () => {
      const user = userEvent.setup();
      const mockCreateObjectURL = vi.fn().mockReturnValue("blob:http://localhost/dummy");
      const mockRevokeObjectURL = vi.fn();
      window.URL.createObjectURL = mockCreateObjectURL;
      window.URL.revokeObjectURL = mockRevokeObjectURL;

      const mockBlob = new Blob(['{"audit": true}'], { type: "application/json" });
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        blob: () => Promise.resolve(mockBlob),
        headers: new Headers({
          "content-type": "application/json",
          "content-disposition": 'attachment; filename="audit-report.json"',
        }),
      });
      global.fetch = fetchSpy;

      render(<ArtifactsTable artifacts={mockArtifacts} />);

      const downloadButton = screen.getByRole("button", { name: /Download/i });
      await user.click(downloadButton);

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith("/api/artifacts/art-1/download");
        expect(mockCreateObjectURL).toHaveBeenCalled();
        expect(mockRevokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/dummy");
      });
    });

    it("displays meaningful error message when download fails with non-ok response", async () => {
      const user = userEvent.setup();
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: "Access denied: task belongs to another user" }),
      });
      global.fetch = fetchSpy;

      render(<ArtifactsTable artifacts={mockArtifacts} />);

      const downloadButton = screen.getByRole("button", { name: /Download/i });
      await user.click(downloadButton);

      await waitFor(() => {
        expect(screen.getByText(/Access denied: task belongs to another user/i)).toBeInTheDocument();
      });
    });

    it("handles download failure when integrity verification fails (409)", async () => {
      const user = userEvent.setup();
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ detail: "Artifact integrity verification failed: SHA-256 digest mismatch" }),
      });
      global.fetch = fetchSpy;

      render(<ArtifactsTable artifacts={mockArtifacts} />);

      const downloadButton = screen.getByRole("button", { name: /Download/i });
      await user.click(downloadButton);

      await waitFor(() => {
        expect(screen.getByText(/Artifact integrity verification failed/i)).toBeInTheDocument();
      });
    });

    it("renders artifact metadata including name, formatted size, and SHA-256 digest", () => {
      render(<ArtifactsTable artifacts={mockArtifacts} />);

      expect(screen.getByText("audit-report.json")).toBeInTheDocument();
      expect(screen.getByText("application/json")).toBeInTheDocument();
      expect(screen.getByText("4.0 KB")).toBeInTheDocument();
      expect(
        screen.getByText(/2c26b46b\.\.\.6266e7ae/)
      ).toBeInTheDocument();
    });

    it("renders empty state message when artifacts list is empty", () => {
      render(<ArtifactsTable artifacts={[]} />);

      expect(
        screen.getByText(/No artifacts were emitted during this execution/i)
      ).toBeInTheDocument();
    });
  });
});
