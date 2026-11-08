"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ChevronRight,
  Cpu,
  FileCode2,
  HardDrive,
  Globe,
  Lock,
  Radio,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Receipt,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Card } from "@/components/ui/card";
import { PlanOverview } from "@/components/plans/plan-overview";
import { PlanSteps } from "@/components/plans/plan-steps";
import { PolicyInspector } from "@/components/plans/policy-inspector";
import { PlanIntegrityCard } from "@/components/plans/plan-integrity-card";
import { InputProvenanceCard } from "@/components/plans/input-provenance-card";
import { ExecutionProgressTracker } from "@/components/executions/execution-progress-tracker";
import { ApprovalModal } from "@/components/plans/approval-modal";
import { RejectModal } from "@/components/plans/reject-modal";
import { ExecutionTimeline } from "@/components/executions/execution-timeline";
import { StepLogsViewer } from "@/components/executions/step-logs-viewer";
import { ReconciliationAlert } from "@/components/executions/reconciliation-alert";
import { CancelModal } from "@/components/executions/cancel-modal";
import {
  ExecutionReceiptCard,
  resolveApprovedPlanHash,
} from "@/components/artifacts/execution-receipt";
import { ArtifactsTable } from "@/components/artifacts/artifacts-table";
import { api, ApiError } from "@/lib/api/client";
import {
  getTaskStatusMeta,
  isTaskActiveExecution,
} from "@/lib/status/statusConfig";
import { formatDate, formatRelativeTime } from "@/lib/formatters";
import { TaskDetail, ExecutionRead } from "@/types/backend";

interface TaskDetailPageProps {
  params: Promise<{ taskId: string }>;
}

export default function TaskDetailPage({ params }: TaskDetailPageProps) {
  const { taskId } = use(params);
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);

  // TanStack Query with controlled dynamic polling
  const {
    data: taskDetail,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
    dataUpdatedAt,
  } = useQuery<TaskDetail, ApiError>({
    queryKey: ["task", taskId],
    queryFn: () => api.tasks.get(taskId),
    // Poll every 3 seconds while task is active; 15 seconds if in needs_reconciliation; stop once terminal
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const task = data.task;
      const execution = data.latest_execution || (data as unknown as { execution?: ExecutionRead }).execution;
      if (!task) return false;

      const isNeedsReconciliation =
        task.status === "needs_reconciliation" ||
        execution?.status === "needs_reconciliation" ||
        execution?.cleanup_status === "leak_detected";

      if (isNeedsReconciliation) {
        return 15000; // Cautious periodic check at 15s until host-side reconciliation resolution
      }

      if (isTaskActiveExecution(task.status)) {
        return 3000; // 3-second polling for active execution phases
      }
      return false;
    },
    refetchIntervalInBackground: false, // Pause when tab is hidden
  });

  // Approval Mutation
  const approveMutation = useMutation({
    mutationFn: (reason?: string) =>
      api.tasks.approve(taskId, { decision: "approved", reason }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["task", taskId], updated);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setActionError(null);
    },
    onError: (err: ApiError) => {
      setActionError(err.message || "Failed to approve plan.");
    },
  });

  // Rejection Mutation
  const rejectMutation = useMutation({
    mutationFn: (reason?: string) =>
      api.tasks.approve(taskId, { decision: "rejected", reason }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["task", taskId], updated);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setActionError(null);
    },
    onError: (err: ApiError) => {
      setActionError(err.message || "Failed to reject plan.");
    },
  });

  // Plan Regeneration Mutation (POST /api/v1/tasks/{task_id}/plan returns TaskPlanRead)
  const regenerateMutation = useMutation({
    mutationFn: () => api.tasks.regeneratePlan(taskId),
    onSuccess: (newPlan) => {
      queryClient.setQueryData<TaskDetail>(["task", taskId], (prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          task: {
            ...prev.task,
            status: newPlan.approval_status === "pending" ? "awaiting_approval" : "failed",
          },
          plan: newPlan,
          latest_approval: null, // Previous approval state is never reused
        };
      });
      queryClient.invalidateQueries({ queryKey: ["task", taskId] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setActionError(null);
    },
    onError: (err: ApiError) => {
      setActionError(err.message || "Failed to regenerate plan.");
    },
  });

  // Cancellation Mutation
  const cancelMutation = useMutation({
    mutationFn: (reason?: string) =>
      api.tasks.cancel(taskId, { reason }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["task", taskId], updated);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setActionError(null);
    },
    onError: (err: ApiError) => {
      setActionError(err.message || "Failed to cancel task.");
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton className="h-10 w-3/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !taskDetail) {
    return (
      <div className="p-12 text-center space-y-4">
        <ShieldAlert className="mx-auto h-10 w-10 text-rose-400" />
        <h2 className="text-lg font-bold text-white">Task Not Found or Inaccessible</h2>
        <p className="text-xs text-zinc-400 max-w-sm mx-auto">
          {error?.message || "Unable to retrieve task details. Verify task ID and your access credentials."}
        </p>
        <Button asChild variant="outline" size="sm" className="text-xs">
          <Link href="/app/tasks">Back to Tasks</Link>
        </Button>
      </div>
    );
  }

  const { task, plan, artifacts, events } = taskDetail;
  const execution =
    taskDetail.latest_execution ||
    (taskDetail as unknown as { execution?: ExecutionRead }).execution ||
    null;
  const taskStatusMeta = getTaskStatusMeta(task.status);
  const isNeedsReconciliation =
    task.status === "needs_reconciliation" ||
    execution?.status === "needs_reconciliation" ||
    execution?.cleanup_status === "leak_detected";
  const isAwaitingApproval =
    task.status === "awaiting_approval" &&
    plan?.approval_status === "pending" &&
    !isNeedsReconciliation;
  const isActive = isTaskActiveExecution(task.status) && !isNeedsReconciliation;
  const canRegenerate =
    ["awaiting_approval", "rejected", "failed"].includes(task.status) &&
    !execution &&
    !isNeedsReconciliation;

  // Resolve authoritative plan hash and check for retained/mismatched historical approvals
  const hashResolution = resolveApprovedPlanHash({
    plan,
    latestApproval: taskDetail.latest_approval,
  });

  return (
    <div className="space-y-6">
      {/* Breadcrumb Navigation */}
      <div className="flex items-center gap-2 text-xs text-zinc-400">
        <Link href="/app/tasks" className="hover:text-white transition-colors flex items-center gap-1">
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Tasks</span>
        </Link>
        <ChevronRight className="h-3 w-3 text-zinc-600" />
        <span className="text-zinc-200 font-mono font-medium truncate max-w-xs">
          {task.title || task.id}
        </span>
      </div>

      {/* Task Header & Status Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-3 border-b border-white/[0.06]">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-white">
              {task.title}
            </h1>
            <Badge
              variant="default"
              className={taskStatusMeta.badgeClass}
              dotClass={taskStatusMeta.dotClass}
            >
              {taskStatusMeta.label}
            </Badge>
          </div>
          <p className="text-xs text-zinc-400 font-mono">
            ID: <span className="text-zinc-300 select-all">{task.id}</span> • Created {formatDate(task.created_at)}
          </p>
        </div>

        {/* Global Task Actions */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Manual Refresh Indicator */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs text-zinc-400 hover:text-white h-8 px-2 gap-1.5"
            title="Refresh state"
          >
            <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin text-[#55D6C2]" : ""}`} />
            <span className="text-[11px] font-mono">
              {dataUpdatedAt ? formatRelativeTime(new Date(dataUpdatedAt).toISOString()) : "refresh"}
            </span>
          </Button>

          {/* Regenerate Plan Action */}
          {canRegenerate && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => regenerateMutation.mutate()}
              isLoading={regenerateMutation.isPending}
              className="text-xs h-8 gap-1.5"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Regenerate Plan</span>
            </Button>
          )}

          {/* Cancel Task Action */}
          {isActive && (
            <CancelModal
              onCancel={async (reason) => {
                await cancelMutation.mutateAsync(reason);
              }}
              disabled={cancelMutation.isPending}
            />
          )}

          {/* Approval Action Group (if awaiting approval) */}
          {isAwaitingApproval && plan && (
            <div className="flex items-center gap-2">
              <RejectModal
                onReject={async (reason) => {
                  await rejectMutation.mutateAsync(reason);
                }}
                disabled={rejectMutation.isPending}
              />
              <ApprovalModal
                planHash={plan.plan_hash}
                policy={plan.policy_result}
                onApprove={async (reason) => {
                  await approveMutation.mutateAsync(reason);
                }}
                disabled={approveMutation.isPending}
              />
            </div>
          )}
        </div>
      </div>

      {actionError && (
        <div
          role="alert"
          className="rounded-lg border border-rose-800/80 bg-rose-950/40 p-3.5 text-xs text-rose-200"
        >
          {actionError}
        </div>
      )}

      {/* Plan Approval Integrity / Association Warning */}
      {hashResolution.hasMismatch && (
        <div
          role="alert"
          className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5 text-xs text-amber-200 flex items-start gap-3"
        >
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h4 className="font-semibold text-amber-300 flex items-center gap-1.5">
              Plan Approval Integrity Warning
            </h4>
            <p className="text-zinc-300 text-[11px] leading-relaxed">
              {hashResolution.warningMessage}
            </p>
          </div>
        </div>
      )}

      {/* Special Security State: Needs Reconciliation */}
      {isNeedsReconciliation && (
        <ReconciliationAlert
          sandboxId={execution?.sandbox_id}
          cleanupStatus={execution?.cleanup_status}
        />
      )}

      {/* Hardware Sandbox & Worker Isolation Badge (when claimed or executed) */}
      {execution && (
        <div className="rounded-lg border border-white/8 bg-[#111820] p-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-3 font-mono text-[11px]">
            <div className="flex items-center gap-2 text-zinc-300">
              <Radio className="h-3.5 w-3.5 text-[#55D6C2]" />
              <span>Runtime: <strong className="text-white">{execution.runtime_image}</strong></span>
            </div>

            <div className="flex items-center gap-2 text-zinc-300">
              <Globe className="h-3.5 w-3.5 text-[#55D6C2]" />
              <span>Network: <strong className="text-emerald-400 uppercase">{execution.network_mode}</strong></span>
            </div>

            <div className="flex items-center gap-2 text-zinc-300">
              <Cpu className="h-3.5 w-3.5 text-[#55D6C2]" />
              <span>Limits: <strong className="text-white">{execution.cpu_limit} vCPU / {execution.memory_limit_mb}MB</strong></span>
            </div>

            <div className="flex items-center gap-2 text-zinc-300">
              <HardDrive className="h-3.5 w-3.5 text-[#55D6C2]" />
              <span>Sandbox: <strong className="text-[#55D6C2] truncate max-w-[140px] select-all">{execution.sandbox_id || "ephemeral"}</strong></span>
            </div>
          </div>
        </div>
      )}

      {/* 8-Phase Execution Progress Tracker & MicroVM Visualization */}
      <ExecutionProgressTracker
        task={task}
        plan={plan}
        execution={execution}
        artifacts={artifacts}
      />

      {/* Tabbed View */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="w-full justify-start border-b border-white/8 bg-[#111820]">
          <TabsTrigger value="overview" className="gap-1.5 text-xs">
            <FileCode2 className="h-3.5 w-3.5" />
            <span>Task &amp; Plan</span>
          </TabsTrigger>

          {plan && (
            <TabsTrigger value="steps" className="gap-1.5 text-xs">
              <Terminal className="h-3.5 w-3.5" />
              <span>Code Steps ({plan.plan_json.steps?.length || 0})</span>
            </TabsTrigger>
          )}

          {plan && (
            <TabsTrigger value="policy" className="gap-1.5 text-xs">
              <ShieldCheck className="h-3.5 w-3.5" />
              <span>Policy Engine</span>
            </TabsTrigger>
          )}

          {execution && (
            <TabsTrigger value="logs" className="gap-1.5 text-xs">
              <Activity className="h-3.5 w-3.5" />
              <span>Execution Logs ({execution.steps?.length || 0})</span>
            </TabsTrigger>
          )}

          {(execution || artifacts.length > 0) && (
            <TabsTrigger value="receipt" className="gap-1.5 text-xs">
              <Receipt className="h-3.5 w-3.5" />
              <span>Receipt &amp; Artifacts ({artifacts.length})</span>
            </TabsTrigger>
          )}

          <TabsTrigger value="timeline" className="gap-1.5 text-xs">
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>Audit Trail ({events.length})</span>
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Overview & Cryptographic Plan Hash */}
        <TabsContent value="overview" className="space-y-6 pt-2">
          {plan ? (
            <div className="space-y-6">
              {/* Prominent Plan Integrity Card */}
              <PlanIntegrityCard planHash={plan.plan_hash} />

              {/* Task Input Provenance Card */}
              <InputProvenanceCard provenance={plan.plan_json.input_provenance} />

              <PlanOverview plan={plan} />

              {/* Action reminder if awaiting approval */}
              {isAwaitingApproval && (
                <Card className="bg-[#111820] border-[#55D6C2]/40 shadow-lg p-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                        <Lock className="h-4 w-4 text-[#55D6C2]" />
                        Ready for Approval Decision
                      </h4>
                      <p className="text-xs text-zinc-300">
                        Review the code steps and policy evaluation before granting execution authorization.
                      </p>
                    </div>

                    <div className="flex items-center gap-2.5 shrink-0">
                      <RejectModal
                        onReject={async (reason) => {
                          await rejectMutation.mutateAsync(reason);
                        }}
                        disabled={rejectMutation.isPending}
                      />
                      <ApprovalModal
                        planHash={plan.plan_hash}
                        policy={plan.policy_result}
                        onApprove={async (reason) => {
                          await approveMutation.mutateAsync(reason);
                        }}
                        disabled={approveMutation.isPending}
                      />
                    </div>
                  </div>
                </Card>
              )}
            </div>
          ) : (
            <Card className="bg-[#111820] border-white/8 p-8 text-center">
              <p className="text-sm text-zinc-300">
                {task.status === "planning"
                  ? "AI Task Planner is currently formulating your isolated execution plan..."
                  : "No plan is currently associated with this task."}
              </p>
            </Card>
          )}
        </TabsContent>

        {/* Tab 2: Execution Steps */}
        {plan && (
          <TabsContent value="steps" className="space-y-6 pt-2">
            <PlanSteps steps={plan.plan_json.steps || []} />
          </TabsContent>
        )}

        {/* Tab 3: Policy Inspector */}
        {plan && (
          <TabsContent value="policy" className="space-y-6 pt-2">
            <PolicyInspector policy={plan.policy_result} />
          </TabsContent>
        )}

        {/* Tab 4: Execution Logs */}
        {execution && (
          <TabsContent value="logs" className="space-y-6 pt-2">
            <StepLogsViewer
              steps={execution.steps || []}
              taskStatus={task.status}
              executionStatus={execution.status}
              events={events}
            />
          </TabsContent>
        )}

        {/* Tab 5: Receipt & Artifacts */}
        {(execution || artifacts.length > 0) && (
          <TabsContent value="receipt" className="space-y-6 pt-2">
            <ExecutionReceiptCard
              execution={execution}
              receipt={execution?.receipt_json}
              approvedPlanHash={hashResolution.authoritativePlanHash}
              planHashMismatch={hashResolution.hasMismatch}
              planHashWarning={hashResolution.warningMessage}
            />
            <ArtifactsTable artifacts={artifacts} />
          </TabsContent>
        )}

        {/* Tab 6: Audit Timeline */}
        <TabsContent value="timeline" className="space-y-6 pt-2">
          <ExecutionTimeline taskStatus={task.status} events={events} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
