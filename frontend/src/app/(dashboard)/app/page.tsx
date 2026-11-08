"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Cpu,
  FileCode2,
  HardDrive,
  Plus,
  RefreshCw,
  Server,
  Shield,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { getTaskStatusMeta, isTaskActiveExecution } from "@/lib/status/statusConfig";
import { formatRelativeTime } from "@/lib/formatters";
import { TaskRead } from "@/types/backend";

export default function OverviewPage() {
  const {
    data: tasks,
    isLoading: tasksLoading,
    isError: tasksError,
    refetch: refetchTasks,
    isFetching: tasksFetching,
  } = useQuery({
    queryKey: ["tasks"],
    queryFn: api.tasks.list,
  });

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["health"],
    queryFn: api.system.health,
  });

  const { data: systemStatus, isLoading: systemStatusLoading } = useQuery({
    queryKey: ["system-status"],
    queryFn: api.system.status,
  });

  const { data: inference, isLoading: inferenceLoading } = useQuery({
    queryKey: ["system-inference"],
    queryFn: api.system.inference,
  });

  // Derive metrics strictly from real task records
  const taskList: TaskRead[] = tasks || [];
  const totalTasks = taskList.length;
  const awaitingApproval = taskList.filter((t) => t.status === "awaiting_approval").length;
  const activeExecutions = taskList.filter((t) => isTaskActiveExecution(t.status)).length;
  const completedTasks = taskList.filter((t) => t.status === "succeeded").length;
  const failedTasks = taskList.filter((t) => ["failed", "timed_out", "rejected"].includes(t.status)).length;
  const needsReconciliationCount = taskList.filter((t) => t.status === "needs_reconciliation").length;

  // Recent tasks sorted by created_at descending
  const recentTasks = [...taskList]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Top Banner & Primary Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            Execution Overview
            {tasksFetching && (
              <RefreshCw className="h-4 w-4 animate-spin text-zinc-400" />
            )}
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Real-time telemetry and isolation metrics for engineering tasks and hardware sandboxes.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetchTasks()}
            disabled={tasksFetching}
            className="text-xs gap-1.5 h-8"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${tasksFetching ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </Button>

          <Button asChild variant="default" size="sm" className="text-xs gap-1.5 h-8">
            <Link href="/app/tasks/new">
              <Plus className="h-3.5 w-3.5" />
              <span>Create Task</span>
            </Link>
          </Button>
        </div>
      </div>

      {/* Critical Needs Reconciliation Banner (if any) */}
      {needsReconciliationCount > 0 && (
        <div
          role="alert"
          className="rounded-lg border border-orange-600/80 bg-orange-950/40 p-4 text-xs text-orange-200 flex items-start gap-3 shadow-lg"
        >
          <AlertTriangle className="h-5 w-5 shrink-0 text-orange-400 mt-0.5" />
          <div className="space-y-1">
            <h4 className="font-semibold text-orange-100 text-sm">
              Critical Security Alert: {needsReconciliationCount} MicroVM Sandbox(es) Require Operator Reconciliation
            </h4>
            <p className="text-orange-200/90 leading-relaxed">
              Sandbox cleanup verification could not be confirmed absent following task execution. To preserve isolation, execution has not been requeued. Operator inspection of host microVM instances is required.
            </p>
            <Link
              href="/app/tasks"
              className="inline-flex items-center gap-1 font-semibold text-orange-300 hover:text-white underline underline-offset-4 mt-1"
            >
              Inspect Affected Tasks &rarr;
            </Link>
          </div>
        </div>
      )}

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3.5">
        <Card className="bg-[#111820] border-white/8 p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-zinc-400">
            <span className="text-xs font-medium">Total Tasks</span>
            <FileCode2 className="h-4 w-4 text-zinc-400" />
          </div>
          <div className="mt-3">
            {tasksLoading ? (
              <Skeleton className="h-7 w-14" />
            ) : (
              <div className="text-2xl font-bold font-mono text-white">{totalTasks}</div>
            )}
            <p className="text-[10px] text-zinc-400 mt-0.5">Recorded task lifecycle entries</p>
          </div>
        </Card>

        <Card className="bg-[#111820] border-white/8 p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-zinc-400">
            <span className="text-xs font-medium">Awaiting Approval</span>
            <Clock className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-3">
            {tasksLoading ? (
              <Skeleton className="h-7 w-14" />
            ) : (
              <div className="text-2xl font-bold font-mono text-amber-300">{awaitingApproval}</div>
            )}
            <p className="text-[10px] text-zinc-400 mt-0.5">Cryptographic review required</p>
          </div>
        </Card>

        <Card className="bg-[#111820] border-white/8 p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-zinc-400">
            <span className="text-xs font-medium">Active Executions</span>
            <Activity className="h-4 w-4 text-[#55D6C2]" />
          </div>
          <div className="mt-3">
            {tasksLoading ? (
              <Skeleton className="h-7 w-14" />
            ) : (
              <div className="text-2xl font-bold font-mono text-[#55D6C2]">{activeExecutions}</div>
            )}
            <p className="text-[10px] text-zinc-400 mt-0.5">Isolated microVM processes</p>
          </div>
        </Card>

        <Card className="bg-[#111820] border-white/8 p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-zinc-400">
            <span className="text-xs font-medium">Verified Completed</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-3">
            {tasksLoading ? (
              <Skeleton className="h-7 w-14" />
            ) : (
              <div className="text-2xl font-bold font-mono text-emerald-400">{completedTasks}</div>
            )}
            <p className="text-[10px] text-zinc-400 mt-0.5">Sandbox destroyed &amp; audited</p>
          </div>
        </Card>

        <Card className="bg-[#111820] border-white/8 p-4 flex flex-col justify-between col-span-2 md:col-span-1">
          <div className="flex items-center justify-between text-zinc-400">
            <span className="text-xs font-medium">Failed / Rejected</span>
            <XCircle className="h-4 w-4 text-rose-400" />
          </div>
          <div className="mt-3">
            {tasksLoading ? (
              <Skeleton className="h-7 w-14" />
            ) : (
              <div className="text-2xl font-bold font-mono text-rose-300">{failedTasks}</div>
            )}
            <p className="text-[10px] text-zinc-400 mt-0.5">Policy violations or errors</p>
          </div>
        </Card>
      </div>

      {/* Two Column Layout: Recent Tasks & Infrastructure Security Health */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Tasks List (2 cols on lg) */}
        <div className="lg:col-span-2 space-y-4">
          <Card className="bg-[#111820] border-white/8 shadow-sm">
            <CardHeader className="flex flex-row items-center justify-between py-4 px-5">
              <div>
                <CardTitle className="text-sm font-semibold text-white">Recent Task Audits</CardTitle>
                <CardDescription className="text-xs text-zinc-400">
                  Latest execution attempts and cryptographic plans
                </CardDescription>
              </div>
              <Button asChild variant="ghost" size="sm" className="text-xs text-[#55D6C2] hover:text-white gap-1 h-7">
                <Link href="/app/tasks">
                  <span>View All</span>
                  <ArrowUpRight className="h-3 w-3" />
                </Link>
              </Button>
            </CardHeader>

            <CardContent className="p-0">
              {tasksLoading ? (
                <div className="p-5 space-y-3">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : tasksError ? (
                <div className="p-6 text-center text-xs text-rose-300">
                  Failed to load tasks. Verify backend connectivity.
                </div>
              ) : recentTasks.length === 0 ? (
                <div className="p-10 text-center">
                  <FileCode2 className="mx-auto h-8 w-8 text-zinc-600 mb-2" />
                  <p className="text-sm font-medium text-zinc-300">No tasks created yet</p>
                  <p className="text-xs text-zinc-400 mt-1 max-w-sm mx-auto">
                    Submit your first natural language task objective to generate an AI plan and isolated execution.
                  </p>
                  <Button asChild variant="default" size="sm" className="mt-4 text-xs">
                    <Link href="/app/tasks/new">Create Task</Link>
                  </Button>
                </div>
              ) : (
                <div className="divide-y divide-white/[0.06]">
                  {recentTasks.map((task) => {
                    const statusMeta = getTaskStatusMeta(task.status);
                    return (
                      <Link
                        key={task.id}
                        href={`/app/tasks/${task.id}`}
                        className="flex flex-col sm:flex-row sm:items-center justify-between p-4 hover:bg-white/[0.03] transition-colors gap-2 group"
                      >
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-xs text-zinc-200 group-hover:text-white truncate">
                              {task.title}
                            </span>
                            <span className="font-mono text-[10px] text-zinc-400 shrink-0">
                              #{task.id.slice(0, 8)}
                            </span>
                          </div>
                          <p className="text-xs text-zinc-400 line-clamp-1 pr-2">
                            {task.description}
                          </p>
                        </div>

                        <div className="flex items-center gap-3 shrink-0 self-start sm:self-center">
                          <span className="text-[11px] text-zinc-400 font-mono">
                            {formatRelativeTime(task.created_at)}
                          </span>
                          <Badge
                            variant="default"
                            className={statusMeta.badgeClass}
                            dotClass={statusMeta.dotClass}
                          >
                            {statusMeta.label}
                          </Badge>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Infrastructure & Security Invariants Panel (1 col on lg) */}
        <div className="space-y-4">
          <Card className="bg-[#111820] border-white/8 shadow-sm">
            <CardHeader className="py-4 px-5">
              <CardTitle className="text-sm font-semibold text-white flex items-center gap-2">
                <Shield className="h-4 w-4 text-[#55D6C2]" />
                Security Invariants
              </CardTitle>
              <CardDescription className="text-xs text-zinc-400">
                Verified platform blast-radius-zero parameters
              </CardDescription>
            </CardHeader>

            <CardContent className="px-5 pb-5 pt-0 space-y-3.5 text-xs">
              <div className="rounded-md border border-white/6 bg-[#0B0E12] p-3 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400 flex items-center gap-1.5 font-medium">
                    <Server className="h-3.5 w-3.5 text-zinc-400" />
                    Database Connectivity
                  </span>
                  <span
                    className={`font-mono font-medium ${
                      health?.database_connected ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {healthLoading ? "..." : health?.database_connected ? "Connected" : "Disconnected"}
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400 flex items-center gap-1.5 font-medium">
                    <Shield className="h-3.5 w-3.5 text-zinc-400" />
                    API Health Status
                  </span>
                  <span
                    className={`font-mono font-medium ${
                      health?.status === "healthy" ? "text-emerald-400" : "text-amber-400"
                    }`}
                  >
                    {healthLoading ? "..." : health?.status || "offline"}
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400 flex items-center gap-1.5 font-medium">
                    <Cpu className="h-3.5 w-3.5 text-zinc-400" />
                    Vultr Inference
                  </span>
                  <span
                    className={`font-mono font-medium ${
                      inference?.status === "reachable"
                        ? "text-emerald-400"
                        : "text-amber-400"
                    }`}
                  >
                    {inferenceLoading
                      ? "..."
                      : inference?.status
                      ? `${inference.status} (${systemStatus?.vultr_inference_model || inference?.model || "glm-5.3"})`
                      : "checking..."}
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400 flex items-center gap-1.5 font-medium">
                    <HardDrive className="h-3.5 w-3.5 text-zinc-400" />
                    Configured Sandbox Backend
                  </span>
                  <span className="font-mono text-zinc-200 uppercase font-semibold text-[11px]">
                    {systemStatus?.sandbox_backend || health?.sandbox_backend || "microsandbox"}
                  </span>
                </div>
              </div>

              {/* Configured Safety Limits & Invariant Policies */}
              <div className="space-y-2 pt-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block">
                  Configured Safety Limits (Platform Policy)
                </span>

                <div className="space-y-1.5 text-[11px]">
                  <div className="flex items-center justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-zinc-400">Max Guest CPUs</span>
                    <span className="font-mono text-zinc-200 font-medium">
                      {systemStatusLoading ? "..." : `${systemStatus?.security_invariants?.max_cpus ?? 1} vCPU`}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-zinc-400">Max Guest Memory</span>
                    <span className="font-mono text-zinc-200 font-medium">
                      {systemStatusLoading ? "..." : `${systemStatus?.security_invariants?.max_memory_mb ?? 1024} MB`}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-zinc-400">Max Execution Timeout</span>
                    <span className="font-mono text-zinc-200 font-medium">
                      {systemStatusLoading ? "..." : `${systemStatus?.security_invariants?.max_timeout_seconds ?? 120}s`}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-zinc-400">Default Network Policy</span>
                    <span className="font-mono text-emerald-400 font-medium">Default None (Airgapped)</span>
                  </div>
                  <div className="flex items-center justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-zinc-400">Host Credentials</span>
                    <span className="font-mono text-emerald-400 font-medium">Zero in Sandbox</span>
                  </div>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-zinc-400">Teardown Verification</span>
                    <span className="font-mono text-emerald-400 font-medium">Deterministic Strict</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
