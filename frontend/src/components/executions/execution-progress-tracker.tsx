"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Clock,
  Code2,
  Cpu,
  FolderTree,
  HardDrive,
  Lock,
  Pause,
  Play,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ExecutionRead, ExecutionStepRead, TaskDetail } from "@/types/backend";

interface ExecutionProgressTrackerProps {
  task: TaskDetail["task"];
  plan?: TaskDetail["plan"];
  execution?: ExecutionRead | null;
  artifacts?: TaskDetail["artifacts"];
}

interface PhaseDef {
  id: string;
  label: string;
  shortDesc: string;
  icon: React.ComponentType<{ className?: string }>;
}

const PHASES: PhaseDef[] = [
  { id: "planning", label: "Plan Formulation", shortDesc: "Vultr AI plan generation", icon: Code2 },
  { id: "policy", label: "Policy Evaluation", shortDesc: "Blast-radius validation", icon: ShieldCheck },
  { id: "approval", label: "Authorization Gate", shortDesc: "Cryptographic human sign-off", icon: Lock },
  { id: "provisioning", label: "MicroVM Setup", shortDesc: "Hardware jail initialization", icon: Cpu },
  { id: "execution", label: "Guest Code Run", shortDesc: "Multi-step sandboxed execution", icon: Terminal },
  { id: "artifacts", label: "Artifact Harvest", shortDesc: "Integrity verification", icon: HardDrive },
  { id: "cleanup", label: "Sandbox Teardown", shortDesc: "Verified jail destruction", icon: Zap },
  { id: "receipt", label: "Receipt Signed", shortDesc: "Ed25519 cryptographic proof", icon: ShieldAlert },
];

export function ExecutionProgressTracker({
  task,
  plan,
  execution,
  artifacts = [],
}: ExecutionProgressTrackerProps) {
  const [followExecution, setFollowExecution] = useState<boolean>(true);
  const [liveSeconds, setLiveSeconds] = useState<number>(0);
  const [activeStepTab, setActiveStepTab] = useState<number>(0);
  const userScrolledRef = useRef<boolean>(false);
  const terminalLogRef = useRef<HTMLDivElement>(null);

  // Determine current active phase index (0 to 7)
  const determinePhaseIndex = (): { current: number; isTerminal: boolean; isFailed: boolean } => {
    if (task.status === "planning") return { current: 0, isTerminal: false, isFailed: false };
    if (task.status === "awaiting_approval") return { current: 2, isTerminal: false, isFailed: false };
    if (task.status === "rejected") return { current: 2, isTerminal: true, isFailed: true };
    if (task.status === "cancelled") return { current: 3, isTerminal: true, isFailed: true };
    if (task.status === "needs_reconciliation") return { current: 6, isTerminal: true, isFailed: true };

    if (execution) {
      if (execution.status === "queued" || execution.status === "preparing") {
        return { current: 3, isTerminal: false, isFailed: false };
      }
      if (execution.status === "running") {
        return { current: 4, isTerminal: false, isFailed: false };
      }
      if (execution.status === "verifying") {
        return { current: 5, isTerminal: false, isFailed: false };
      }
      if (execution.status === "succeeded") {
        return { current: 7, isTerminal: true, isFailed: false };
      }
      if (execution.status === "failed") {
        return { current: 6, isTerminal: true, isFailed: true };
      }
    }

    if (task.status === "approved" || task.status === "queued") {
      return { current: 3, isTerminal: false, isFailed: false };
    }
    if (task.status === "running") {
      return { current: 4, isTerminal: false, isFailed: false };
    }
    if (task.status === "succeeded") {
      return { current: 7, isTerminal: true, isFailed: false };
    }
    if (task.status === "failed") {
      return { current: 6, isTerminal: true, isFailed: true };
    }

    return { current: 1, isTerminal: false, isFailed: false };
  };

  const { current: activePhaseIndex, isTerminal, isFailed } = determinePhaseIndex();

  // Derived static duration or live interval timer
  const staticDuration =
    typeof execution?.duration_seconds === "number"
      ? execution.duration_seconds
      : execution?.started_at && execution?.completed_at
      ? Math.max(
          0,
          (new Date(execution.completed_at).getTime() - new Date(execution.started_at).getTime()) / 1000
        )
      : null;

  useEffect(() => {
    if (staticDuration != null || !execution?.started_at || execution?.completed_at) {
      return;
    }

    const start = new Date(execution.started_at).getTime();
    const interval = setInterval(() => {
      setLiveSeconds(Math.max(0, (Date.now() - start) / 1000));
    }, 500);

    return () => clearInterval(interval);
  }, [execution?.started_at, execution?.completed_at, staticDuration]);

  const displayedSeconds = staticDuration ?? liveSeconds;

  // Auto-scroll when followExecution is true
  useEffect(() => {
    if (followExecution && terminalLogRef.current) {
      terminalLogRef.current.scrollTop = terminalLogRef.current.scrollHeight;
    }
  }, [followExecution, execution?.steps]);

  // Detect manual scroll to detach follow mode
  const handleScroll = () => {
    if (!userScrolledRef.current && followExecution) {
      // User touched or scrolled container manually
      setFollowExecution(false);
    }
  };

  const steps: ExecutionStepRead[] = execution?.steps || [];
  const selectedStep = steps[activeStepTab] || steps[steps.length - 1] || null;
  const inputManifest = plan?.plan_json?.input_provenance?.files || [];

  return (
    <Card className="bg-[#111820] border-white/8 shadow-sm">
      <CardHeader className="pb-3 border-b border-white/[0.06]">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
              <Activity className="h-4 w-4 text-[#55D6C2]" />
              Isolated Execution Progress
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400">
              Real-time hardware isolation telemetry and execution step visualization.
            </CardDescription>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Live Elapsed Time Pill */}
            <div className="flex items-center gap-1.5 rounded-full border border-white/10 bg-[#0B0E12] px-3 py-1 font-mono text-xs text-zinc-300">
              <Clock className="h-3.5 w-3.5 text-[#55D6C2]" />
              <span>
                Elapsed:{" "}
                <strong className="text-white">
                  {displayedSeconds.toFixed(1)}s
                </strong>
              </span>
            </div>

            {/* Follow Execution Auto-Scroll Toggle */}
            <button
              type="button"
              onClick={() => {
                setFollowExecution(!followExecution);
                userScrolledRef.current = false;
              }}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-mono transition ${
                followExecution
                  ? "border-teal-500/40 bg-teal-950/40 text-teal-300"
                  : "border-white/10 bg-[#0B0E12] text-zinc-400 hover:text-white"
              }`}
              title={
                followExecution
                  ? "Auto-scroll enabled (click to pause)"
                  : "Auto-scroll paused (click to follow)"
              }
            >
              {followExecution ? (
                <>
                  <Play className="h-3 w-3 text-teal-400 fill-teal-400" />
                  <span>Following Logs</span>
                </>
              ) : (
                <>
                  <Pause className="h-3 w-3 text-zinc-500" />
                  <span>Follow Execution</span>
                </>
              )}
            </button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-6">
        {/* 8-Phase Execution Timeline Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {PHASES.map((p, idx) => {
            const IconComponent = p.icon;
            const isPassed = idx < activePhaseIndex || (idx === activePhaseIndex && isTerminal && !isFailed);
            const isCurrent = idx === activePhaseIndex && !isTerminal;
            const isFailStep = idx === activePhaseIndex && isFailed;

            return (
              <div
                key={p.id}
                className={`relative flex flex-col justify-between rounded-lg border p-2.5 transition-all text-xs ${
                  isCurrent
                    ? "border-teal-500/80 bg-teal-950/30 ring-1 ring-teal-500/50 shadow-sm"
                    : isFailStep
                    ? "border-rose-500/60 bg-rose-950/30 text-rose-300"
                    : isPassed
                    ? "border-emerald-500/30 bg-emerald-950/15 text-emerald-400"
                    : "border-white/5 bg-[#0B0E12] text-zinc-500"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] text-zinc-400">0{idx + 1}</span>
                  {isPassed ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  ) : (
                    <IconComponent
                      className={`h-3.5 w-3.5 ${
                        isCurrent ? "text-teal-400 animate-pulse" : isFailStep ? "text-rose-400" : "text-zinc-600"
                      }`}
                    />
                  )}
                </div>
                <div className="mt-2">
                  <div
                    className={`font-semibold text-[11px] leading-tight truncate ${
                      isCurrent ? "text-white" : isPassed ? "text-zinc-200" : "text-zinc-500"
                    }`}
                  >
                    {p.label}
                  </div>
                  <div className="text-[10px] text-zinc-500 leading-tight mt-0.5 truncate">
                    {p.shortDesc}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Guest MicroVM Visualization: Workspace Mounts */}
        <div className="rounded-lg border border-white/8 bg-[#0B0E12] p-3 font-mono text-xs">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/5">
            <div className="flex items-center gap-2 text-zinc-300">
              <FolderTree className="h-4 w-4 text-[#55D6C2]" />
              <span className="font-semibold text-white">MicroVM Guest Filesystem Mounts</span>
            </div>
            <div className="text-[10px] text-zinc-400">
              Sandbox ID: <span className="text-[#55D6C2]">{execution?.sandbox_id || "ephemeral-kvm"}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[11px]">
            {/* Input Mount */}
            <div className="rounded border border-white/5 bg-white/[0.01] p-2.5">
              <div className="flex items-center gap-2 text-teal-400 font-semibold mb-1">
                <span>/workspace/input/</span>
                <span className="text-[10px] text-zinc-500 font-normal">
                  ({inputManifest.length} mounted file{inputManifest.length === 1 ? "" : "s"})
                </span>
              </div>
              {inputManifest.length > 0 ? (
                <ul className="space-y-1 text-zinc-300">
                  {inputManifest.map((f, i) => (
                    <li key={i} className="flex items-center justify-between text-[10px]">
                      <span className="truncate">{f.filename}</span>
                      <span className="text-zinc-500 shrink-0">
                        ({f.size_bytes} B | SHA: {f.sha256?.substring(0, 8)}...)
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-[10px] text-zinc-500 italic">No staged files (prompt_only mode)</div>
              )}
            </div>

            {/* Output Mount */}
            <div className="rounded border border-white/5 bg-white/[0.01] p-2.5">
              <div className="flex items-center gap-2 text-emerald-400 font-semibold mb-1">
                <span>/workspace/output/</span>
                <span className="text-[10px] text-zinc-500 font-normal">
                  ({artifacts.length} produced artifact{artifacts.length === 1 ? "" : "s"})
                </span>
              </div>
              {artifacts.length > 0 ? (
                <ul className="space-y-1 text-zinc-300">
                  {artifacts.map((a, i) => (
                    <li key={i} className="flex items-center justify-between text-[10px]">
                      <span className="truncate">{a.filename}</span>
                      <span className="text-zinc-500 shrink-0">
                        ({(a.size_bytes / 1024).toFixed(1)} KB | SHA: {a.sha256?.substring(0, 8)}...)
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-[10px] text-zinc-500 italic">Awaiting step output generation...</div>
              )}
            </div>
          </div>
        </div>

        {/* Multi-Step Code & Execution Log Visualizer */}
        {steps.length > 0 && (
          <div className="space-y-3">
            {/* Step Selection Tabs */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs font-mono">
              {steps.map((st, idx) => (
                <button
                  key={st.id || idx}
                  type="button"
                  onClick={() => setActiveStepTab(idx)}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
                    activeStepTab === idx
                      ? "bg-[#55D6C2] font-semibold text-slate-950"
                      : "border border-white/10 bg-[#0B0E12] text-zinc-300 hover:text-white"
                  }`}
                >
                  <span>Step {st.step_number || idx + 1}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[9px] ${
                      st.status === "succeeded"
                        ? "bg-emerald-900/60 text-emerald-300"
                        : st.status === "failed"
                        ? "bg-rose-900/60 text-rose-300"
                        : "bg-teal-900/60 text-teal-300"
                    }`}
                  >
                    {st.status}
                  </span>
                </button>
              ))}
            </div>

            {selectedStep && (
              <div
                ref={terminalLogRef}
                onScroll={handleScroll}
                className="space-y-3 rounded-lg border border-white/8 bg-[#0B0E12] p-4 text-xs font-mono"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2 text-[11px]">
                  <div className="text-zinc-300">
                    <strong className="text-white">
                      Step {selectedStep.step_number}: {selectedStep.description}
                    </strong>
                  </div>
                  <div className="flex items-center gap-3 text-zinc-400">
                    <span>Exit Code: <strong className={selectedStep.exit_code === 0 ? "text-emerald-400" : "text-rose-400"}>{selectedStep.exit_code ?? "-"}</strong></span>
                    <span>Attempt: <strong className="text-zinc-200">{selectedStep.attempt_number ?? 1}</strong></span>
                  </div>
                </div>

                {/* Read-Only Code Viewer */}
                {selectedStep.code && (
                  <div className="space-y-1">
                    <div className="text-[10px] text-zinc-500 uppercase tracking-wider">
                      Sandboxed Guest Code ({selectedStep.execution_type})
                    </div>
                    <pre className="rounded bg-[#111820] p-3 text-[11px] text-zinc-200 overflow-x-auto max-h-48 border border-white/5 select-all">
                      <code>{selectedStep.code}</code>
                    </pre>
                  </div>
                )}

                {/* Real Stdout */}
                {selectedStep.stdout && (
                  <div className="space-y-1">
                    <div className="text-[10px] text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                      <Terminal className="h-3 w-3" />
                      <span>Guest MicroVM stdout</span>
                    </div>
                    <pre className="rounded bg-black/60 p-3 text-[11px] text-emerald-300/90 overflow-x-auto max-h-48 border border-emerald-950/40 select-all">
                      <code>{selectedStep.stdout}</code>
                    </pre>
                  </div>
                )}

                {/* Real Stderr */}
                {selectedStep.stderr && (
                  <div className="space-y-1">
                    <div className="text-[10px] text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
                      <Terminal className="h-3 w-3" />
                      <span>Guest MicroVM stderr</span>
                    </div>
                    <pre className="rounded bg-black/60 p-3 text-[11px] text-rose-300/90 overflow-x-auto max-h-48 border border-rose-950/40 select-all">
                      <code>{selectedStep.stderr}</code>
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
