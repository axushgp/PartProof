"use client";

import React, { useState, useEffect } from "react";
import { ShieldCheck, Play, Loader2, FileDown, Lock, Check } from "lucide-react";
import { ProcurementAuditPayload } from "@/types/procurement";
import { TaskDetail } from "@/types/backend";
import { createProcurementTask } from "@/lib/api/procurementClient";
import { api } from "@/lib/api/client";
import { ExecutionReceiptCard, resolveApprovedPlanHash } from "@/components/artifacts/execution-receipt";
import { ArtifactsTable } from "@/components/artifacts/artifacts-table";

interface ProcurementExecutionPanelProps {
  auditPayload: ProcurementAuditPayload;
}

export function ProcurementExecutionPanel({ auditPayload }: ProcurementExecutionPanelProps) {
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null);
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Poll for execution completion once queued
  useEffect(() => {
    if (!taskDetail) return;
    const currentStatus = taskDetail.task.status;
    if (["queued", "preparing", "running", "verifying"].includes(currentStatus)) {
      const interval = setInterval(async () => {
        try {
          const updated = await api.tasks.get(taskDetail.task.id);
          setTaskDetail(updated);
          if (["succeeded", "failed", "cancelled", "timed_out"].includes(updated.task.status)) {
            clearInterval(interval);
          }
        } catch (e) {
          console.error("Polling error:", e);
        }
      }, 1500);

      return () => clearInterval(interval);
    }
  }, [taskDetail]);

  const handleCreateTask = async () => {
    setIsCreatingTask(true);
    setErrorMsg(null);
    try {
      const detail = await createProcurementTask(auditPayload);
      setTaskDetail(detail);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to initiate procurement task");
    } finally {
      setIsCreatingTask(false);
    }
  };

  const handleApprove = async () => {
    if (!taskDetail) return;
    setIsApproving(true);
    setErrorMsg(null);
    try {
      const updated = await api.tasks.approve(taskDetail.task.id, {
        decision: "approved",
        reason: "Procurement forensic audit approved by auditor.",
      });
      setTaskDetail(updated);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to approve task execution");
    } finally {
      setIsApproving(false);
    }
  };

  const latestExec = taskDetail?.latest_execution;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl backdrop-blur-md">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-slate-800 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <Lock className="h-5 w-5 text-teal-400" />
              <h3 className="text-base font-semibold text-slate-100">Isolated MicroSandbox Execution & Cryptographic Proof</h3>
              <span className="rounded-full bg-teal-500/10 px-2.5 py-0.5 text-xs font-mono font-medium text-teal-300 border border-teal-500/20">
                Phase 1 & Phase 2 Bound
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Transform this procurement audit into an immutable, cryptographically signed PartProof Execution Receipt with 5 authenticated decision artifacts.
            </p>
          </div>

          {!taskDetail && (
            <button
              onClick={handleCreateTask}
              disabled={isCreatingTask}
              className="inline-flex items-center gap-2 rounded-lg bg-teal-500 px-5 py-2.5 text-xs font-semibold text-slate-950 transition hover:bg-teal-400 active:scale-95 disabled:opacity-50"
            >
              {isCreatingTask ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating Plan...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 fill-current" />
                  Initialize Isolated Audit Task
                </>
              )}
            </button>
          )}
        </div>

        {errorMsg && (
          <div className="mt-4 rounded-lg border border-red-500/30 bg-red-950/30 p-3 text-xs text-red-300">
            {errorMsg}
          </div>
        )}

        {/* Task Plan & Policy State */}
        {taskDetail && (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/80 p-4 font-mono text-xs">
              <div>
                <span className="text-slate-400">Task ID:</span>{" "}
                <span className="text-teal-300 font-bold">{taskDetail.task.id}</span>
                <span className="mx-2 text-slate-700">|</span>
                <span className="text-slate-400">Status:</span>{" "}
                <span className="capitalize text-slate-200 font-semibold">{taskDetail.task.status}</span>
              </div>

              {taskDetail.plan && (
                <div className="flex items-center gap-2">
                  <span className="rounded bg-teal-500/10 border border-teal-500/30 px-2 py-0.5 text-[11px] text-teal-300">
                    Plan Hash: {taskDetail.plan.plan_hash.slice(0, 12)}...
                  </span>
                  <span className="rounded bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 text-[11px] text-emerald-300 flex items-center gap-1">
                    <ShieldCheck className="h-3 w-3" /> Policy: Blast Radius Zero
                  </span>
                </div>
              )}
            </div>

            {/* Approval Action */}
            {taskDetail.task.status === "awaiting_approval" && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold text-amber-300">Plan Generated & Policy Verified</p>
                  <p className="text-xs text-amber-200/80 mt-0.5">
                    Plan specifies isolated execution with zero networking to output the 5 procurement decision artifacts. Explicit approval is required.
                  </p>
                </div>
                <button
                  onClick={handleApprove}
                  disabled={isApproving}
                  className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-teal-500 px-5 py-2 text-xs font-semibold text-slate-950 transition hover:bg-teal-400 disabled:opacity-50"
                >
                  {isApproving ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Queueing...
                    </>
                  ) : (
                    <>
                      <Check className="h-3.5 w-3.5" />
                      Approve & Execute in MicroSandbox
                    </>
                  )}
                </button>
              </div>
            )}

            {/* In-Flight Monitoring */}
            {["queued", "preparing", "running", "verifying"].includes(taskDetail.task.status) && (
              <div className="rounded-lg border border-teal-500/30 bg-teal-950/20 p-4 flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-teal-400" />
                <div className="text-xs">
                  <p className="font-semibold text-teal-300">
                    Executing isolated procurement calculations in MicroSandbox...
                  </p>
                  <p className="text-slate-400 mt-0.5">
                    Status: <span className="font-mono text-slate-300 capitalize">{taskDetail.task.status}</span>. Writing decision pack and verifying microVM destruction.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Cryptographic Execution Receipt & Artifact Downloads */}
      {taskDetail && latestExec && (
        <div className="space-y-6">
          {(() => {
            const planHashRes = resolveApprovedPlanHash({
              plan: taskDetail.plan,
              latestApproval: taskDetail.latest_approval,
            });
            return (
              <ExecutionReceiptCard
                receipt={latestExec.receipt_json}
                execution={latestExec}
                approvedPlanHash={planHashRes.authoritativePlanHash}
                planHashMismatch={planHashRes.hasMismatch}
                planHashWarning={planHashRes.warningMessage}
              />
            );
          })()}

          {/* Decision Pack Artifacts Download */}
          {taskDetail.artifacts && taskDetail.artifacts.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <FileDown className="h-5 w-5 text-teal-400" />
                <h4 className="text-base font-semibold text-slate-100">Procurement Decision Pack (Authenticated Downloads)</h4>
              </div>
              <ArtifactsTable artifacts={taskDetail.artifacts} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
