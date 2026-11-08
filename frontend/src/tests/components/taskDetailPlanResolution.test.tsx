import { describe, it, expect, vi, beforeEach } from "vitest";
import React, { Suspense } from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TaskDetailPage from "@/app/(dashboard)/app/tasks/[taskId]/page";
import { api } from "@/lib/api/client";
import { TaskDetail } from "@/types/backend";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client");
  return {
    ...actual,
    api: {
      tasks: {
        get: vi.fn(),
        approve: vi.fn(),
        cancel: vi.fn(),
        regeneratePlan: vi.fn(),
      },
    },
  };
});

describe("TaskDetailPage Plan Approval Resolution & ExecutionReceiptCard Rendering", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  it("renders integrity warning on task detail page and inside ExecutionReceiptCard when older rejected approval disagrees with newer approved plan hash", async () => {
    const user = userEvent.setup();

    const olderRejectedApprovalHash = "1111111111111111111111111111111111111111111111111111111111111111";
    const newerApprovedPlanHash = "2222222222222222222222222222222222222222222222222222222222222222";

    const mockTaskDetailWithOlderRejection: TaskDetail = {
      task: {
        id: "task-mismatch-42",
        title: "Regenerated Binary Integrity Verification",
        description: "Task with regenerated plan after earlier rejection",
        status: "succeeded",
        created_at: "2026-03-24T10:00:00Z",
        updated_at: "2026-03-24T12:00:00Z",
      },
      plan: {
        id: "plan-new-42",
        task_id: "task-mismatch-42",
        model: "glm-5.3",
        plan_json: {
          title: "Regenerated Binary Integrity Verification",
          summary: "New execution plan following rejection",
          reasoning_summary: "Updated to remove forbidden egress calls",
          steps: [
            {
              step_id: "step-1",
              description: "Compute local cryptographic digests",
              execution_type: "subprocess",
              code: "sha256sum /guest/input.txt",
            },
          ],
          required_capabilities: [],
          network_required: false,
          success_criteria: ["Hashes verified"],
          expected_artifacts: ["report.json"],
        },
        plan_hash: newerApprovedPlanHash,
        policy_result: {
          allowed: true,
          policy_name: "default-sandbox-v1",
          policy_version: "1.0",
          network_mode: "none",
          cpu_limit: 1,
          memory_limit_mb: 512,
          timeout_seconds: 30,
        },
        policy_version: "1.0",
        approval_status: "approved",
        created_at: "2026-03-24T11:30:00Z",
      },
      // Backend TaskDetail builder returns task.approvals[-1] which retains older rejected approval
      latest_approval: {
        id: "appr-old-rejected",
        task_id: "task-mismatch-42",
        approved_by: "auditor@partproof.io",
        approved_plan_hash: olderRejectedApprovalHash,
        decision: "rejected",
        reason: "Detected unauthorized network egress socket binding in original plan",
        created_at: "2026-03-24T10:15:00Z",
      },
      latest_execution: {
        id: "exec-42",
        task_id: "task-mismatch-42",
        worker_id: "worker-node-alpha",
        sandbox_id: "guest-microsandbox-prod-42",
        status: "succeeded",
        runtime_image: "python:3.12-slim",
        cpu_limit: 1,
        memory_limit_mb: 512,
        network_mode: "none",
        cleanup_status: "verified_destroyed",
        started_at: "2026-03-24T12:00:00Z",
        completed_at: "2026-03-24T12:00:05Z",
        duration_seconds: 5.2,
        exit_code: 0,
        receipt_json: null, // Worker does not yet generate receipt_json
        steps: [
          {
            id: "step-exec-1",
            task_id: "task-mismatch-42",
            execution_id: "exec-42",
            step_number: 1,
            description: "Compute local cryptographic digests",
            execution_type: "subprocess",
            code: "sha256sum /guest/input.txt",
            status: "succeeded",
            exit_code: 0,
            stdout: "2222222222222222 /guest/input.txt",
            stderr: "",
          },
        ],
        artifacts: [],
      },
      artifacts: [],
      events: [],
    };

    vi.mocked(api.tasks.get).mockResolvedValueOnce(mockTaskDetailWithOlderRejection);

    const paramsPromise = Promise.resolve({ taskId: "task-mismatch-42" });

    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <Suspense fallback={<div>Loading task...</div>}>
            <TaskDetailPage params={paramsPromise} />
          </Suspense>
        </QueryClientProvider>
      );
    });

    // 1. Verify Task Header & Plan are loaded
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Regenerated Binary Integrity Verification" })
      ).toBeInTheDocument();
    });

    // 2. Verify Plan Approval Integrity Warning is rendered prominently on the task detail page
    expect(
      screen.getByText("Plan Approval Integrity Warning")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/The current approved plan hash \(2222222222222222\.\.\.\) disagrees with the latest recorded approval digest \(1111111111111111\.\.\.\)/i)
    ).toBeInTheDocument();

    // 3. Verify ExecutionReceiptCard is actually rendered on the task detail page
    // Switch to Receipt & Artifacts tab
    const receiptTabTrigger = screen.getByRole("tab", { name: /Receipt & Artifacts/i });
    expect(receiptTabTrigger).toBeInTheDocument();
    await user.click(receiptTabTrigger);

    await waitFor(() => {
      // Proves ExecutionReceiptCard is imported and active on the task detail page
      expect(screen.getByText("Cryptographic Execution Receipt")).toBeInTheDocument();
    });

    // 4. Verify ExecutionReceiptCard reflects the hash discrepancy rather than silently selecting either hash
    expect(
      screen.getByText("Integrity Warning: Approval Record Hash Discrepancy")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Discrepancy (Hash Mismatch)")
    ).toBeInTheDocument();

    // 5. Verify the backend receipt gap notice is also present
    expect(
      screen.getByText(/Receipt not generated by backend \(Execution receipt unavailable\)/i)
    ).toBeInTheDocument();

    // 6. Verify operational metadata is displayed
    expect(screen.getByText("exec-42")).toBeInTheDocument();
    expect(screen.getAllByText("guest-microsandbox-prod-42").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Verified Destruction")).toBeInTheDocument();
  });
});
