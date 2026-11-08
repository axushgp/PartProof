"use client";

import { useState } from "react";
import { XCircle } from "lucide-react";
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

interface RejectModalProps {
  onReject: (reason?: string) => Promise<void>;
  disabled?: boolean;
}

export function RejectModal({ onReject, disabled = false }: RejectModalProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setError(null);
    setIsSubmitting(true);
    try {
      await onReject(reason.trim() || undefined);
      setOpen(false);
    } catch (err: unknown) {
      setError(
        err && typeof err === "object" && "message" in err
          ? (err as { message: string }).message
          : "Rejection request failed."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button
          variant="destructive"
          size="sm"
          disabled={disabled}
          className="gap-1.5 text-xs font-semibold h-9 px-4"
        >
          <XCircle className="h-4 w-4" />
          <span>Reject Plan</span>
        </Button>
      </AlertDialogTrigger>

      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-white">
            <XCircle className="h-5 w-5 text-rose-400" />
            <span>Reject Execution Plan</span>
          </AlertDialogTitle>
          <AlertDialogDescription className="text-zinc-300">
            Rejecting this plan prevents any code from being queued or executed in the sandbox. You can subsequently regenerate a new plan if desired.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {error && (
          <div className="p-3 rounded bg-rose-950/60 border border-rose-800 text-xs text-rose-200">
            {error}
          </div>
        )}

        <div className="space-y-1.5 py-2">
          <label htmlFor="rejection-reason" className="text-xs text-zinc-300 font-medium">
            Reason for Rejection (Optional)
          </label>
          <Textarea
            id="rejection-reason"
            rows={3}
            placeholder="e.g. Plan steps require external network capability which violates airgap policy..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="text-xs"
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isSubmitting} className="text-xs">
            Cancel
          </AlertDialogCancel>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            isLoading={isSubmitting}
            className="text-xs font-semibold"
          >
            Confirm Rejection
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
