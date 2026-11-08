"use client";

import { useState } from "react";
import { CheckCircle2, Fingerprint, Lock, ShieldCheck } from "lucide-react";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PolicyEvaluationResult } from "@/types/backend";

interface ApprovalModalProps {
  planHash: string;
  policy: PolicyEvaluationResult;
  onApprove: (reason?: string) => Promise<void>;
  disabled?: boolean;
}

export function ApprovalModal({
  planHash,
  policy,
  onApprove,
  disabled = false,
}: ApprovalModalProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setError(null);
    setIsSubmitting(true);
    try {
      await onApprove(reason.trim() || undefined);
      setOpen(false);
    } catch (err: unknown) {
      setError(
        err && typeof err === "object" && "message" in err
          ? (err as { message: string }).message
          : "Approval request failed."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button
          variant="success"
          size="sm"
          disabled={disabled || !policy.allowed}
          className="gap-1.5 text-xs font-semibold h-9 px-4"
        >
          <CheckCircle2 className="h-4 w-4" />
          <span>Approve Plan</span>
        </Button>
      </AlertDialogTrigger>

      <AlertDialogContent className="max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-white">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <span>Confirm Plan Approval &amp; Authorize Execution</span>
          </AlertDialogTitle>
          <AlertDialogDescription className="text-zinc-300">
            You are authorizing isolated microVM execution of this verified plan. Review the cryptographic digest and policy bounds below before confirming.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {error && (
          <div className="p-3 rounded bg-rose-950/60 border border-rose-800 text-xs text-rose-200">
            {error}
          </div>
        )}

        {/* Cryptographic Hash Review */}
        <div className="space-y-3 py-2 text-xs">
          <div className="rounded-md border border-white/10 bg-[#0B0E12] p-3 space-y-1.5">
            <div className="flex items-center gap-1.5 text-zinc-400 font-semibold font-mono text-[10px] uppercase">
              <Fingerprint className="h-3.5 w-3.5 text-[#55D6C2]" />
              Canonical Plan SHA-256 Digest
            </div>
            <p className="font-mono text-[11px] text-[#55D6C2] break-all select-all">
              {planHash}
            </p>
          </div>

          {/* Policy Summary */}
          <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
            <div className="rounded bg-[#0B0E12] p-2 border border-white/6 text-zinc-400">
              <span>Policy:</span>{" "}
              <strong className="text-zinc-200">{policy.policy_name}</strong>
            </div>
            <div className="rounded bg-[#0B0E12] p-2 border border-white/6 text-zinc-400">
              <span>Network:</span>{" "}
              <strong className="text-emerald-400 uppercase">{policy.network_mode}</strong>
            </div>
            <div className="rounded bg-[#0B0E12] p-2 border border-white/6 text-zinc-400">
              <span>CPU / Memory:</span>{" "}
              <strong className="text-zinc-200">
                {policy.cpu_limit} vCPU / {policy.memory_limit_mb}MB
              </strong>
            </div>
            <div className="rounded bg-[#0B0E12] p-2 border border-white/6 text-zinc-400">
              <span>Timeout:</span>{" "}
              <strong className="text-zinc-200">{policy.timeout_seconds}s</strong>
            </div>
          </div>

          {/* Optional Approval Note */}
          <div className="space-y-1 pt-1">
            <label htmlFor="approval-reason" className="text-xs text-zinc-300 font-medium">
              Approval Justification / Audit Note (Optional)
            </label>
            <Textarea
              id="approval-reason"
              rows={2}
              placeholder="e.g. Plan verified compliant with safety protocol..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="text-xs"
            />
          </div>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isSubmitting} className="text-xs">
            Cancel
          </AlertDialogCancel>
          <Button
            variant="success"
            onClick={handleConfirm}
            isLoading={isSubmitting}
            className="text-xs font-semibold gap-1.5"
          >
            <Lock className="h-3.5 w-3.5" />
            <span>Confirm &amp; Queue Execution</span>
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
