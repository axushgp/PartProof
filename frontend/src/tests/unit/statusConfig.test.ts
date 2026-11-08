import { describe, it, expect } from "vitest";
import {
  TASK_STATUS_CONFIG,
  EXECUTION_STATUS_CONFIG,
  isTaskTerminal,
  isExecutionTerminal,
  isTaskActionable,
  isTaskActiveExecution,
  getTaskStatusMeta,
} from "@/lib/status/statusConfig";

describe("Status Configuration & Lifecycles", () => {
  const ALL_TASK_STATUSES = [
    "created",
    "planning",
    "awaiting_approval",
    "queued",
    "preparing",
    "running",
    "verifying",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
    "timed_out",
    "rejected",
    "needs_reconciliation",
  ] as const;

  it("defines metadata for all task statuses", () => {
    for (const status of ALL_TASK_STATUSES) {
      const meta = TASK_STATUS_CONFIG[status];
      expect(meta, `Metadata for ${status} should exist`).toBeDefined();
      expect(meta.label).toBeTruthy();
      expect(meta.badgeClass).toBeTruthy();
      expect(meta.dotClass).toBeTruthy();
      expect(meta.description).toBeTruthy();
    }
  });

  it("marks terminal states correctly", () => {
    expect(isTaskTerminal("succeeded")).toBe(true);
    expect(isTaskTerminal("failed")).toBe(true);
    expect(isTaskTerminal("cancelled")).toBe(true);
    expect(isTaskTerminal("timed_out")).toBe(true);
    expect(isTaskTerminal("rejected")).toBe(true);

    // Active states are not terminal
    expect(isTaskTerminal("created")).toBe(false);
    expect(isTaskTerminal("planning")).toBe(false);
    expect(isTaskTerminal("awaiting_approval")).toBe(false);
    expect(isTaskTerminal("queued")).toBe(false);
    expect(isTaskTerminal("preparing")).toBe(false);
    expect(isTaskTerminal("running")).toBe(false);
  });

  it("marks awaiting_approval and needs_reconciliation as actionable", () => {
    expect(isTaskActionable("awaiting_approval")).toBe(true);
    expect(isTaskActionable("needs_reconciliation")).toBe(true);
    expect(isTaskActionable("running")).toBe(false);
    expect(isTaskActionable("succeeded")).toBe(false);
  });

  it("correctly identifies active execution phases", () => {
    expect(isTaskActiveExecution("queued")).toBe(true);
    expect(isTaskActiveExecution("preparing")).toBe(true);
    expect(isTaskActiveExecution("running")).toBe(true);
    expect(isTaskActiveExecution("verifying")).toBe(true);
    expect(isTaskActiveExecution("cancel_requested")).toBe(true);
    expect(isTaskActiveExecution("succeeded")).toBe(false);
    expect(isTaskActiveExecution("awaiting_approval")).toBe(false);
  });

  it("provides fallback metadata for unknown statuses", () => {
    const fallback = getTaskStatusMeta("unknown_status_xyz");
    expect(fallback).toBeDefined();
    expect(fallback.label).toBe("unknown_status_xyz");
    expect(fallback.isTerminal).toBe(false);
  });

  it("defines execution statuses accurately", () => {
    expect(EXECUTION_STATUS_CONFIG.running.isTerminal).toBe(false);
    expect(EXECUTION_STATUS_CONFIG.succeeded.isTerminal).toBe(true);
    expect(EXECUTION_STATUS_CONFIG.failed.isTerminal).toBe(true);
    expect(EXECUTION_STATUS_CONFIG.timed_out.isTerminal).toBe(true);
    expect(EXECUTION_STATUS_CONFIG.cancelled.isTerminal).toBe(true);

    expect(isExecutionTerminal("succeeded")).toBe(true);
    expect(isExecutionTerminal("failed")).toBe(true);
    expect(isExecutionTerminal("timed_out")).toBe(true);
    expect(isExecutionTerminal("cancelled")).toBe(true);
    expect(isExecutionTerminal("running")).toBe(false);
  });
});
