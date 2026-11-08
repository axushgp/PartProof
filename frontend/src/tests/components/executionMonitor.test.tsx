import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReconciliationAlert } from "@/components/executions/reconciliation-alert";
import { StepLogsViewer } from "@/components/executions/step-logs-viewer";
import { ExecutionTimeline } from "@/components/executions/execution-timeline";
import { CancelModal } from "@/components/executions/cancel-modal";
import { ExecutionStepRead, ExecutionEventRead } from "@/types/backend";

describe("Execution Monitoring Components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("ReconciliationAlert", () => {
    it("renders prominent leak detected security alert with preserved sandbox ID", () => {
      render(
        <ReconciliationAlert
          sandboxId="unverified-leak-sandbox-id-8888"
          cleanupStatus="leak_detected"
        />
      );

      expect(
        screen.getByText(/CRITICAL SECURITY STATE: Sandbox Cleanup Needs Reconciliation/i)
      ).toBeInTheDocument();
      expect(screen.getByText("LEAK DETECTED")).toBeInTheDocument();
      expect(screen.getByText("unverified-leak-sandbox-id-8888")).toBeInTheDocument();
      expect(
        screen.getByText(/this task will NEVER be automatically requeued/i)
      ).toBeInTheDocument();
    });

    it("handles null sandbox ID gracefully", () => {
      render(<ReconciliationAlert sandboxId={null} cleanupStatus={null} />);

      expect(screen.getByText("unknown-sandbox-id")).toBeInTheDocument();
    });
  });

  describe("StepLogsViewer", () => {
    const mockSteps: ExecutionStepRead[] = [
      {
        id: "step-1",
        task_id: "task-1",
        execution_id: "exec-1",
        step_number: 1,
        description: "Compute File Hashes",
        execution_type: "subprocess",
        code: "sha256sum /guest/input.txt",
        status: "succeeded",
        exit_code: 0,
        stdout: "a3f5b9c1d2e4f6a8b0c2 /guest/input.txt\nDone",
        stderr: "",
        started_at: "2026-03-24T12:00:00Z",
        completed_at: "2026-03-24T12:00:01Z",
      },
      {
        id: "step-2",
        task_id: "task-1",
        execution_id: "exec-1",
        step_number: 2,
        description: "Security Integrity Check",
        execution_type: "subprocess",
        code: "verify_integrity",
        status: "failed",
        exit_code: 1,
        stdout: "",
        stderr: "Integrity mismatch detected on block 4",
        started_at: "2026-03-24T12:00:02Z",
        completed_at: "2026-03-24T12:00:03Z",
      },
    ];

    it("renders each step with its command, exit code badge, and stdout/stderr", () => {
      render(<StepLogsViewer steps={mockSteps} />);

      expect(screen.getByText(/Guest MicroVM Execution Logs \(2 Steps\)/i)).toBeInTheDocument();
      expect(screen.getByText(/Compute File Hashes/i)).toBeInTheDocument();
      expect(screen.getByText(/Security Integrity Check/i)).toBeInTheDocument();

      expect(screen.getByText("exit: 0")).toBeInTheDocument();
      expect(screen.getByText("exit: 1")).toBeInTheDocument();

      expect(screen.getByText(/a3f5b9c1d2e4f6a8b0c2/i)).toBeInTheDocument();
      expect(screen.getByText(/Integrity mismatch detected on block 4/i)).toBeInTheDocument();
    });

    it("renders empty state message when steps array is empty", () => {
      render(<StepLogsViewer steps={[]} />);

      expect(screen.getByText(/No execution step outputs recorded yet/i)).toBeInTheDocument();
    });
  });

  describe("ExecutionTimeline", () => {
    const mockEvents: ExecutionEventRead[] = [
      {
        id: "evt-1",
        execution_id: "exec-1",
        event_type: "claimed",
        message: "Worker worker-prod-01 claimed execution with SKIP LOCKED",
        data: {},
        timestamp: "2026-03-24T12:00:00Z",
      },
      {
        id: "evt-2",
        execution_id: "exec-1",
        event_type: "started",
        message: "MicroVM initialized in isolated cgroup",
        data: {},
        timestamp: "2026-03-24T12:00:05Z",
      },
      {
        id: "evt-3",
        execution_id: "exec-1",
        event_type: "completed",
        message: "Sandbox destroyed and cleanup verified",
        data: {},
        timestamp: "2026-03-24T12:00:10Z",
      },
    ];

    it("renders events in chronological order with recorded count and status", () => {
      render(<ExecutionTimeline taskStatus="succeeded" events={mockEvents} />);

      expect(screen.getByText("Execution Lifecycle Timeline")).toBeInTheDocument();
      expect(screen.getByText("3 Recorded Events")).toBeInTheDocument();
      expect(screen.getByText("Worker worker-prod-01 claimed execution with SKIP LOCKED")).toBeInTheDocument();
      expect(screen.getByText("MicroVM initialized in isolated cgroup")).toBeInTheDocument();
      expect(screen.getByText("Sandbox destroyed and cleanup verified")).toBeInTheDocument();
    });
  });

  describe("CancelModal", () => {
    it("opens confirmation dialog and submits cancellation reason", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn().mockResolvedValue(undefined);
      render(<CancelModal onCancel={onCancel} />);

      const triggerBtn = screen.getByRole("button", { name: /Cancel Task/i });
      await user.click(triggerBtn);

      await waitFor(() => {
        expect(screen.getByText(/Abort Active Task Execution/i)).toBeInTheDocument();
      });

      const reasonInput = screen.getByPlaceholderText(/e\.g\. Discontinued manual audit/i);
      await user.type(reasonInput, "Emergency operator termination");

      const confirmBtn = screen.getByRole("button", { name: /Confirm Cancellation/i });
      await user.click(confirmBtn);

      await waitFor(() => {
        expect(onCancel).toHaveBeenCalledWith("Emergency operator termination");
      });
    });
  });
});
