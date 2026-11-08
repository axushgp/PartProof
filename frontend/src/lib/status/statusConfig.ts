import { TaskStatus, ExecutionStatus } from "@/types/backend";

export interface StatusMeta {
  label: string;
  badgeClass: string;
  dotClass: string;
  description: string;
  isTerminal: boolean;
  isActionable?: boolean;
}

export const TASK_STATUS_CONFIG: Record<string, StatusMeta> = {
  created: {
    label: "Created",
    badgeClass: "bg-zinc-800/80 text-zinc-300 border-zinc-700/60",
    dotClass: "bg-zinc-400",
    description: "Task record initialized",
    isTerminal: false,
  },
  planning: {
    label: "AI Planning",
    badgeClass: "bg-amber-950/40 text-amber-300 border-amber-800/50",
    dotClass: "bg-amber-400 animate-pulse",
    description: "Vultr AI generating isolated execution plan",
    isTerminal: false,
  },
  awaiting_approval: {
    label: "Awaiting Approval",
    badgeClass: "bg-amber-950/60 text-amber-200 border-amber-600/60",
    dotClass: "bg-amber-400",
    description: "Plan ready. Requires explicit cryptographic confirmation",
    isTerminal: false,
    isActionable: true,
  },
  queued: {
    label: "Queued",
    badgeClass: "bg-cyan-950/40 text-cyan-300 border-cyan-800/50",
    dotClass: "bg-cyan-400",
    description: "Plan approved. Awaiting worker claim via SKIP LOCKED",
    isTerminal: false,
  },
  preparing: {
    label: "Preparing MicroVM",
    badgeClass: "bg-cyan-950/50 text-cyan-200 border-cyan-700/60",
    dotClass: "bg-cyan-300 animate-pulse",
    description: "Claimed by worker. Provisioning guest hardware isolation",
    isTerminal: false,
  },
  running: {
    label: "Running",
    badgeClass: "bg-cyan-950/70 text-cyan-200 border-cyan-500/70",
    dotClass: "bg-cyan-400 animate-ping",
    description: "Executing code steps inside ephemeral sandbox",
    isTerminal: false,
  },
  verifying: {
    label: "Verifying",
    badgeClass: "bg-teal-950/60 text-teal-200 border-teal-700/60",
    dotClass: "bg-teal-300 animate-pulse",
    description: "Verifying guest teardown and artifact integrity",
    isTerminal: false,
  },
  succeeded: {
    label: "Succeeded",
    badgeClass: "bg-emerald-950/50 text-emerald-300 border-emerald-800/60",
    dotClass: "bg-emerald-400",
    description: "Execution completed and sandbox verified destroyed",
    isTerminal: true,
  },
  failed: {
    label: "Failed",
    badgeClass: "bg-rose-950/50 text-rose-300 border-rose-800/60",
    dotClass: "bg-rose-400",
    description: "Execution failed or policy verification violated",
    isTerminal: true,
  },
  cancel_requested: {
    label: "Cancel Requested",
    badgeClass: "bg-orange-950/50 text-orange-300 border-orange-800/60",
    dotClass: "bg-orange-400 animate-pulse",
    description: "Cancellation signal delivered. Reaping sandbox cleanly",
    isTerminal: false,
  },
  cancelled: {
    label: "Cancelled",
    badgeClass: "bg-zinc-800/70 text-zinc-400 border-zinc-700/50",
    dotClass: "bg-zinc-400",
    description: "Task cancelled and resources cleanly reclaimed",
    isTerminal: true,
  },
  timed_out: {
    label: "Timed Out",
    badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/60",
    dotClass: "bg-rose-400",
    description: "Exceeded sandbox maximum duration limit",
    isTerminal: true,
  },
  rejected: {
    label: "Rejected",
    badgeClass: "bg-zinc-800/80 text-rose-300/80 border-rose-900/40",
    dotClass: "bg-rose-400",
    description: "Execution plan rejected by user",
    isTerminal: true,
  },
  needs_reconciliation: {
    label: "Needs Reconciliation",
    badgeClass: "bg-orange-950/70 text-orange-200 border-orange-600 font-semibold shadow-sm",
    dotClass: "bg-orange-400 animate-ping",
    description: "CRITICAL: MicroVM destruction could not be verified. Operator audit required.",
    isTerminal: false,
    isActionable: true,
  },
};

export const EXECUTION_STATUS_CONFIG: Record<string, StatusMeta> = {
  queued: {
    label: "Queued",
    badgeClass: "bg-cyan-950/40 text-cyan-300 border-cyan-800/50",
    dotClass: "bg-cyan-400",
    description: "Awaiting worker lease claim",
    isTerminal: false,
  },
  preparing: {
    label: "Preparing",
    badgeClass: "bg-cyan-950/50 text-cyan-200 border-cyan-700/60",
    dotClass: "bg-cyan-300 animate-pulse",
    description: "Spawning hardware-isolated guest microVM",
    isTerminal: false,
  },
  running: {
    label: "Running",
    badgeClass: "bg-cyan-950/70 text-cyan-200 border-cyan-500/70",
    dotClass: "bg-cyan-400 animate-ping",
    description: "Executing plan steps in zero-network guest",
    isTerminal: false,
  },
  verifying: {
    label: "Verifying",
    badgeClass: "bg-teal-950/60 text-teal-200 border-teal-700/60",
    dotClass: "bg-teal-300 animate-pulse",
    description: "Validating guest exit and artifact checksums",
    isTerminal: false,
  },
  succeeded: {
    label: "Succeeded",
    badgeClass: "bg-emerald-950/50 text-emerald-300 border-emerald-800/60",
    dotClass: "bg-emerald-400",
    description: "Execution finished with blast-radius-zero guarantee",
    isTerminal: true,
  },
  failed: {
    label: "Failed",
    badgeClass: "bg-rose-950/50 text-rose-300 border-rose-800/60",
    dotClass: "bg-rose-400",
    description: "Guest step failure or abnormal process exit",
    isTerminal: true,
  },
  cancelled: {
    label: "Cancelled",
    badgeClass: "bg-zinc-800/70 text-zinc-400 border-zinc-700/50",
    dotClass: "bg-zinc-400",
    description: "Execution aborted",
    isTerminal: true,
  },
  timed_out: {
    label: "Timed Out",
    badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/60",
    dotClass: "bg-rose-400",
    description: "Hardware execution deadline exceeded",
    isTerminal: true,
  },
  needs_reconciliation: {
    label: "Needs Reconciliation",
    badgeClass: "bg-orange-950/70 text-orange-200 border-orange-600 font-semibold shadow-sm",
    dotClass: "bg-orange-400 animate-ping",
    description: "CRITICAL: MicroVM destruction could not be verified. Operator audit required.",
    isTerminal: true,
    isActionable: true,
  },
};

export const CLEANUP_STATUS_CONFIG: Record<string, { label: string; badgeClass: string }> = {
  verified_destroyed: {
    label: "Verified Destroyed",
    badgeClass: "bg-emerald-950/50 text-emerald-300 border-emerald-800/60",
  },
  leak_detected: {
    label: "Leak Detected",
    badgeClass: "bg-orange-950/70 text-orange-200 border-orange-600",
  },
  timeout: {
    label: "Cleanup Timeout",
    badgeClass: "bg-rose-950/50 text-rose-300 border-rose-800/60",
  },
  failed: {
    label: "Cleanup Failed",
    badgeClass: "bg-rose-950/50 text-rose-300 border-rose-800/60",
  },
  untracked: {
    label: "Untracked",
    badgeClass: "bg-zinc-800/70 text-zinc-400 border-zinc-700/50",
  },
};

export function getTaskStatusMeta(status: TaskStatus | string): StatusMeta {
  const normalized = (status || "").toLowerCase().trim();
  return (
    TASK_STATUS_CONFIG[normalized] || {
      label: status || "Unknown",
      badgeClass: "bg-zinc-800/80 text-zinc-300 border-zinc-700/60",
      dotClass: "bg-zinc-400",
      description: `State: ${status}`,
      isTerminal: false,
    }
  );
}

export function getExecutionStatusMeta(status: ExecutionStatus | string): StatusMeta {
  const normalized = (status || "").toLowerCase().trim();
  return (
    EXECUTION_STATUS_CONFIG[normalized] || {
      label: status || "Unknown",
      badgeClass: "bg-zinc-800/80 text-zinc-300 border-zinc-700/60",
      dotClass: "bg-zinc-400",
      description: `State: ${status}`,
      isTerminal: false,
    }
  );
}

export function isTaskTerminal(status: TaskStatus | string): boolean {
  return getTaskStatusMeta(status).isTerminal;
}

export function isTaskActionable(status: TaskStatus | string): boolean {
  return Boolean(getTaskStatusMeta(status).isActionable);
}

export function isExecutionTerminal(status: ExecutionStatus | string): boolean {
  return getExecutionStatusMeta(status).isTerminal;
}

export function isTaskActiveExecution(status: TaskStatus | string): boolean {
  const s = (status || "").toLowerCase().trim();
  return ["queued", "preparing", "running", "verifying", "cancel_requested"].includes(s);
}
