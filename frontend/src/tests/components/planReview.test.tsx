import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlanIntegrityCard } from "@/components/plans/plan-integrity-card";
import { PolicyInspector } from "@/components/plans/policy-inspector";
import { ApprovalModal } from "@/components/plans/approval-modal";
import { RejectModal } from "@/components/plans/reject-modal";
import { PolicyEvaluationResult } from "@/types/backend";

const SAMPLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

const ALLOWED_POLICY: PolicyEvaluationResult = {
  allowed: true,
  policy_name: "default-sandbox-v1",
  policy_version: "1.0",
  network_mode: "none",
  cpu_limit: 2,
  memory_limit_mb: 2048,
  timeout_seconds: 120,
  max_output_bytes: 1048576,
  violations: [],
  evaluated_at: new Date().toISOString(),
};

const DISALLOWED_POLICY: PolicyEvaluationResult = {
  allowed: false,
  policy_name: "default-sandbox-v1",
  policy_version: "1.0",
  network_mode: "host",
  cpu_limit: 8,
  memory_limit_mb: 8192,
  timeout_seconds: 3600,
  max_output_bytes: 1048576,
  violations: [
    "Direct host network access forbidden in zero-trust policy",
    "Timeout exceeds safe limit of 300s",
  ],
  evaluated_at: new Date().toISOString(),
};

describe("Plan Review & Policy Inspection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("PlanIntegrityCard", () => {
    it("renders the complete 64-character SHA-256 hash in monospace font", () => {
      render(<PlanIntegrityCard planHash={SAMPLE_HASH} />);

      const hashElement = screen.getByText(SAMPLE_HASH);
      expect(hashElement).toBeInTheDocument();
      expect(hashElement.textContent?.length).toBe(64);
      expect(hashElement.className).toContain("font-mono");
    });

    it("copies exact 64-character hash string to clipboard on click", async () => {
      const user = userEvent.setup();
      render(<PlanIntegrityCard planHash={SAMPLE_HASH} />);

      const copyButton = screen.getByTitle(/Copy SHA-256 hash/i);
      await user.click(copyButton);

      await waitFor(async () => {
        expect(await navigator.clipboard.readText()).toBe(SAMPLE_HASH);
        expect(screen.getByText("Copied")).toBeInTheDocument();
      });
    });
  });

  describe("PolicyInspector", () => {
    it("renders ALLOWED badge, zero-network mode, and resource limits", () => {
      render(<PolicyInspector policy={ALLOWED_POLICY} />);

      expect(screen.getByText("ALLOWED")).toBeInTheDocument();
      expect(screen.getByText("default-sandbox-v1 v1.0")).toBeInTheDocument();
      expect(screen.getByText(/none/i)).toBeInTheDocument();
      expect(screen.getByText("2 vCPU")).toBeInTheDocument();
      expect(screen.getByText("2048 MB")).toBeInTheDocument();
      expect(screen.getByText("120s")).toBeInTheDocument();
    });

    it("renders DISALLOWED badge and violation list when policy fails", () => {
      render(<PolicyInspector policy={DISALLOWED_POLICY} />);

      expect(screen.getByText("DISALLOWED")).toBeInTheDocument();
      expect(screen.getByText(/Policy Violations Detected \(2\)/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Direct host network access forbidden/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/Timeout exceeds safe limit/i)).toBeInTheDocument();
    });
  });

  describe("ApprovalModal", () => {
    it("disables approval trigger button when policy is disallowed", () => {
      const onApprove = vi.fn();
      render(
        <ApprovalModal
          planHash={SAMPLE_HASH}
          policy={DISALLOWED_POLICY}
          onApprove={onApprove}
        />
      );

      const triggerBtn = screen.getByRole("button", { name: /Approve Plan/i });
      expect(triggerBtn).toBeDisabled();
    });

    it("opens dialog on click and displays canonical SHA-256 digest for audit", async () => {
      const user = userEvent.setup();
      const onApprove = vi.fn();
      render(
        <ApprovalModal
          planHash={SAMPLE_HASH}
          policy={ALLOWED_POLICY}
          onApprove={onApprove}
        />
      );

      const triggerBtn = screen.getByRole("button", { name: /Approve Plan/i });
      expect(triggerBtn).toBeEnabled();
      await user.click(triggerBtn);

      await waitFor(() => {
        expect(screen.getByText(/Confirm Plan Approval & Authorize Execution/i)).toBeInTheDocument();
        expect(screen.getByText(SAMPLE_HASH)).toBeInTheDocument();
      });
    });

    it("submits approval with justification reason without client-supplied plan_hash", async () => {
      const user = userEvent.setup();
      const onApprove = vi.fn().mockResolvedValue(undefined);
      render(
        <ApprovalModal
          planHash={SAMPLE_HASH}
          policy={ALLOWED_POLICY}
          onApprove={onApprove}
        />
      );

      const triggerBtn = screen.getByRole("button", { name: /Approve Plan/i });
      await user.click(triggerBtn);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/e\.g\. Plan verified/i)).toBeInTheDocument();
      });

      const reasonInput = screen.getByPlaceholderText(/e\.g\. Plan verified/i);
      await user.type(reasonInput, "Verified safety compliance and network isolation.");

      const confirmBtn = screen.getByRole("button", { name: /Confirm & Queue Execution/i });
      await user.click(confirmBtn);

      await waitFor(() => {
        // Must be called with reason only; client must NEVER send plan_hash to approve endpoint
        expect(onApprove).toHaveBeenCalledWith("Verified safety compliance and network isolation.");
      });
    });
  });

  describe("RejectModal", () => {
    it("opens rejection modal and submits rejection reason", async () => {
      const user = userEvent.setup();
      const onReject = vi.fn().mockResolvedValue(undefined);
      render(<RejectModal onReject={onReject} />);

      const triggerBtn = screen.getByRole("button", { name: /Reject Plan/i });
      await user.click(triggerBtn);

      await waitFor(() => {
        expect(screen.getByText(/Reject Execution Plan/i)).toBeInTheDocument();
      });

      const reasonInput = screen.getByPlaceholderText(/e\.g\. Plan steps require external network/i);
      await user.type(reasonInput, "Commands violate security policy.");

      const confirmBtn = screen.getByRole("button", { name: /Confirm Rejection/i });
      await user.click(confirmBtn);

      await waitFor(() => {
        expect(onReject).toHaveBeenCalledWith("Commands violate security policy.");
      });
    });
  });
});
