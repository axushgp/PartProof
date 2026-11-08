"use client";

import { useState } from "react";
import { AlertTriangle, StopCircle } from "lucide-react";
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

interface CancelModalProps {
  onCancel: (reason?: string) => Promise<void>;
  disabled?: boolean;
}

export function CancelModal({ onCancel, disabled = false }: CancelModalProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setError(null);
    setIsSubmitting(true);
    try {
      await onCancel(reason.trim() || undefined);
      setOpen(false);
    } catch (err: unknown) {
      setError(
        err && typeof err === "object" && "message" in err
          ? (err as { message: string }).message
          : "Cancellation request failed."
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
          className="gap-1.5 text-xs font-semibold h-8"
        >
          <StopCircle className="h-3.5 w-3.5" />
          <span>Cancel Task</span>
        </Button>
      </AlertDialogTrigger>

      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-white">
            <AlertTriangle className="h-5 w-5 text-rose-400" />
            <span>Abort Active Task Execution</span>
          </AlertDialogTitle>
          <AlertDialogDescription className="text-zinc-300 text-xs leading-relaxed">
            Aborting this task terminates the guest microVM process and initiates safe cleanup. If the sandbox is currently running code, the task will transition to <strong>cancel_requested</strong> while the worker terminates and reaps the sandbox process.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {error && (
          <div className="p-3 rounded bg-rose-950/60 border border-rose-800 text-xs text-rose-200">
            {error}
          </div>
        )}

        <div className="space-y-1.5 py-2 text-xs">
          <label htmlFor="cancel-reason" className="block text-zinc-300 font-medium">
            Reason for Cancellation (Optional)
          </label>
          <Textarea
            id="cancel-reason"
            rows={2}
            placeholder="e.g. Discontinued manual audit; aborting sandbox..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="text-xs"
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isSubmitting} className="text-xs">
            Dismiss
          </AlertDialogCancel>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            isLoading={isSubmitting}
            className="text-xs font-semibold"
          >
            Confirm Cancellation
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
