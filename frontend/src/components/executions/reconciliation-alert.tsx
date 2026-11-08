import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface ReconciliationAlertProps {
  sandboxId?: string | null;
  cleanupStatus?: string | null;
}

export function ReconciliationAlert({
  sandboxId,
  cleanupStatus,
}: ReconciliationAlertProps) {
  return (
    <div
      role="alert"
      className="rounded-lg border-2 border-orange-600/90 bg-orange-950/50 p-5 text-orange-200 shadow-xl space-y-3"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-md bg-orange-500/20 text-orange-300 shrink-0">
          <AlertTriangle className="h-6 w-6" />
        </div>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-orange-100 tracking-tight">
              CRITICAL SECURITY STATE: Sandbox Cleanup Needs Reconciliation
            </h3>
            <Badge variant="destructive" className="bg-rose-600 text-white font-mono text-[10px]">
              LEAK DETECTED
            </Badge>
          </div>
          <p className="text-xs text-orange-200/90 leading-relaxed">
            The background reconciler or worker detected that microVM sandbox destruction could not be conclusively verified absent. Under PartProof Blast-Radius-Zero safety invariants, <strong>this task will NEVER be automatically requeued or finalized as succeeded</strong>.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 text-xs font-mono">
        <div className="rounded bg-[#0B0E12] p-3 border border-orange-700/50 space-y-1">
          <span className="text-[10px] uppercase text-zinc-400 block font-sans font-semibold">
            Preserved Sandbox Identity
          </span>
          <p className="text-orange-300 font-semibold truncate select-all">
            {sandboxId || "unknown-sandbox-id"}
          </p>
        </div>

        <div className="rounded bg-[#0B0E12] p-3 border border-orange-700/50 space-y-1">
          <span className="text-[10px] uppercase text-zinc-400 block font-sans font-semibold">
            Teardown Verification Result
          </span>
          <p className="text-orange-300 font-semibold uppercase">
            {cleanupStatus || "leak_detected"}
          </p>
        </div>
      </div>

      <div className="text-[11px] text-orange-300/80 pt-1 border-t border-orange-800/40 leading-relaxed">
        Operator action required: Inspect host microVM instances via <code>msb ls</code> on the infrastructure host. Sandbox teardown uncertainty requires host-side verification. Under Blast-Radius-Zero safety rules, no automated retry, re-queue, or manual bypass is permitted from this console.
      </div>
    </div>
  );
}
