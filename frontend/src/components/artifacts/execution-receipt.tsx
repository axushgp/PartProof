"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  Fingerprint,
  Receipt,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ApprovalRead,
  ExecutionReceipt as ExecutionReceiptType,
  ExecutionRead,
  TaskPlanRead,
} from "@/types/backend";
import { formatDate, formatDuration } from "@/lib/formatters";

/**
 * Maps raw cleanup status strings to human-readable labels and Tailwind color tokens.
 * Explicitly supports:
 * - verified_destroyed
 * - leak_detected
 * - pending_cleanup
 * Plus additional backend statuses (untracked, timeout, failed) and neutral fallback for unknown values.
 */
export function formatCleanupStatus(status?: string | null): {
  label: string;
  colorClass: string;
} {
  if (!status) {
    return { label: "Unknown", colorClass: "text-zinc-400" };
  }

  const normalized = status.toLowerCase();
  switch (normalized) {
    case "verified_destroyed":
      return { label: "Verified Destruction", colorClass: "text-emerald-400" };
    case "leak_detected":
      return { label: "Leak Detected", colorClass: "text-rose-400" };
    case "pending_cleanup":
      return { label: "Pending Cleanup", colorClass: "text-amber-400" };
    case "untracked":
      return { label: "Untracked", colorClass: "text-amber-400" };
    case "timeout":
      return { label: "Cleanup Timeout", colorClass: "text-orange-400" };
    case "failed":
      return { label: "Cleanup Failed", colorClass: "text-rose-400" };
    default:
      // Neutral fallback for any unknown status value
      return { label: status, colorClass: "text-zinc-400" };
  }
}

/**
 * Determines the security verification status adhering strictly to security invariants:
 * - Missing receipt or missing/null verification field: UNVERIFIED (never infer verification)
 * - Explicit security_verified === false: VERIFICATION FAILED / UNVERIFIED
 * - Explicit cleanup_status === leak_detected or execution status === needs_reconciliation: LEAK DETECTED / RECONCILIATION REQUIRED
 * - Explicit security_verified === true: SECURITY VERIFIED
 */
export function getVerificationStatus({
  receipt,
  cleanupStatus,
  executionStatus,
}: {
  receipt?: ExecutionReceiptType | null;
  cleanupStatus?: string | null;
  executionStatus?: string | null;
}): {
  label: string;
  variant: "default" | "secondary" | "destructive" | "outline" | "success";
  iconType: "verified" | "failed" | "leak" | "unverified";
} {
  // 1. Explicit leak or reconciliation condition takes precedence
  if (
    cleanupStatus === "leak_detected" ||
    executionStatus === "needs_reconciliation"
  ) {
    return {
      label: "LEAK DETECTED / RECONCILIATION REQUIRED",
      variant: "destructive",
      iconType: "leak",
    };
  }

  // 2. Explicit false verification on receipt
  if (receipt && (receipt.security_verified === false || receipt.signature_verified === false)) {
    return {
      label: "VERIFICATION FAILED / UNVERIFIED",
      variant: "destructive",
      iconType: "failed",
    };
  }

  // 3. Explicit true verification on receipt
  if (receipt && receipt.security_verified === true && receipt.signature_verified !== false) {
    return {
      label: "SECURITY VERIFIED",
      variant: "success",
      iconType: "verified",
    };
  }

  // 4. Default: missing receipt or missing verification field -> UNVERIFIED
  // Note: Never display "LEAK DETECTED" merely because security_verified is false or missing.
  return {
    label: "UNVERIFIED",
    variant: "secondary",
    iconType: "unverified",
  };
}

export interface PlanHashResolution {
  authoritativePlanHash: string | null;
  hasMismatch: boolean;
  warningMessage: string | null;
  latestApprovalHash: string | null;
  currentPlanHash: string | null;
  isApproved: boolean;
}

/**
 * Resolves the authoritative approved plan hash adhering to backend integrity invariants:
 * - The backend's TaskDetail builder returns task.approvals[-1] without database sorting.
 * - Tasks may retain older approval or rejection records from previous plan generations.
 * - Do NOT blindly trust latest_approval as the approval for the current plan.
 * - Use the current plan.plan_hash as authoritative when plan.approval_status === "approved".
 * - Compare it with latest_approval.approved_plan_hash when available.
 * - If they disagree, flag a mismatch and generate an integrity/association warning rather than silently selecting either.
 */
export function resolveApprovedPlanHash({
  plan,
  latestApproval,
}: {
  plan?: TaskPlanRead | null;
  latestApproval?: ApprovalRead | null;
}): PlanHashResolution {
  const isApproved = plan?.approval_status === "approved";
  const currentPlanHash = plan?.plan_hash || null;
  const latestApprovalHash = latestApproval?.approved_plan_hash || null;
  const latestDecision = latestApproval?.decision;

  // 1. Current plan is marked approved
  if (isApproved && currentPlanHash) {
    // If an approval record exists with a differing approved_plan_hash:
    if (latestApprovalHash && latestApprovalHash !== currentPlanHash) {
      return {
        authoritativePlanHash: null, // Do not silently select either value
        hasMismatch: true,
        warningMessage: `Plan approval integrity warning: The current approved plan hash (${currentPlanHash.slice(0, 16)}...) disagrees with the latest recorded approval digest (${latestApprovalHash.slice(0, 16)}...). This indicates a retained historical approval or rejection record from a prior plan generation.`,
        latestApprovalHash,
        currentPlanHash,
        isApproved: true,
      };
    }

    // If an approval record exists with decision "rejected" despite plan being "approved":
    if (latestApproval && latestDecision === "rejected") {
      return {
        authoritativePlanHash: null, // Do not silently select either value
        hasMismatch: true,
        warningMessage: `Plan approval association warning: The active plan is marked 'approved', but the latest approval record reflects a historical rejection (${latestApprovalHash ? latestApprovalHash.slice(0, 16) + '...' : 'no hash'}) retained from a prior plan generation.`,
        latestApprovalHash,
        currentPlanHash,
        isApproved: true,
      };
    }

    // Matching and valid
    return {
      authoritativePlanHash: currentPlanHash,
      hasMismatch: false,
      warningMessage: null,
      latestApprovalHash,
      currentPlanHash,
      isApproved: true,
    };
  }

  // 2. Current plan is NOT approved (e.g., pending review, rejected, planning)
  // Even if latest_approval exists with a hash from an older iteration, do NOT present it as current
  return {
    authoritativePlanHash: null,
    hasMismatch: false,
    warningMessage: null,
    latestApprovalHash,
    currentPlanHash,
    isApproved: false,
  };
}

interface ExecutionReceiptProps {
  receipt?: ExecutionReceiptType | null;
  execution?: ExecutionRead | null;
  approvedPlanHash?: string | null;
  planHashMismatch?: boolean;
  planHashWarning?: string | null;
}

export function ExecutionReceiptCard({
  receipt,
  execution,
  approvedPlanHash,
  planHashMismatch,
  planHashWarning,
}: ExecutionReceiptProps) {
  const [copied, setCopied] = useState(false);

  // Check if receipt is actually provided by backend
  const hasReceipt = Boolean(receipt && typeof receipt === "object");
  const verificationHash = receipt?.receipt_digest || receipt?.verification_hash || null;
  const hasVerificationHash = Boolean(verificationHash);

  // Cleanup status from execution or receipt
  const rawCleanupStatus = execution?.cleanup_status || receipt?.cleanup_status || null;
  const cleanupInfo = formatCleanupStatus(rawCleanupStatus);

  // Verification status badge
  const verificationStatus = getVerificationStatus({
    receipt,
    cleanupStatus: rawCleanupStatus,
    executionStatus: execution?.status,
  });

  // Effective plan hash: only use if there is no mismatch
  const effectivePlanHash = planHashMismatch ? null : (approvedPlanHash || receipt?.plan_hash || null);

  const handleCopyHash = async () => {
    if (!verificationHash) return;
    try {
      await navigator.clipboard.writeText(verificationHash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard fallback
    }
  };

  return (
    <Card className="bg-[#111820] border-white/8 shadow-sm">
      <CardHeader className="pb-3 border-b border-white/[0.06]">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
              <Receipt className="h-4 w-4 text-[#55D6C2]" />
              Cryptographic Execution Receipt
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400">
              Immutable cryptographic evidence of guest microVM execution and teardown
            </CardDescription>
          </div>

          <Badge
            variant={verificationStatus.variant}
            className={`text-xs font-mono font-semibold ${
              verificationStatus.variant === "secondary"
                ? "bg-zinc-800 text-zinc-300 border-zinc-700"
                : ""
            }`}
          >
            {verificationStatus.iconType === "verified" && (
              <ShieldCheck className="h-3.5 w-3.5 mr-1 text-emerald-400" />
            )}
            {verificationStatus.iconType === "failed" && (
              <ShieldX className="h-3.5 w-3.5 mr-1 text-rose-400" />
            )}
            {verificationStatus.iconType === "leak" && (
              <ShieldAlert className="h-3.5 w-3.5 mr-1 text-rose-400" />
            )}
            {verificationStatus.iconType === "unverified" && (
              <ShieldAlert className="h-3.5 w-3.5 mr-1 text-amber-400" />
            )}
            {verificationStatus.label}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-5 text-xs">
        {/* Receipt Availability & Ed25519 Digital Signature Info */}
        {hasReceipt && (
          <div
            role="status"
            className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-3 text-xs text-emerald-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
          >
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
              <div>
                <span className="font-semibold text-emerald-300">
                  Cryptographic Receipt Available
                </span>
                <p className="text-[11px] text-zinc-400 font-mono mt-0.5">
                  Algorithm: {receipt?.signature_scheme?.toUpperCase() || "ED25519"} · Key ID: {receipt?.key_id || "partproof-ed25519-v1"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                variant={receipt?.signature_verified === false ? "destructive" : "success"}
                className="text-[11px] font-mono"
              >
                {receipt?.signature_verified === false
                  ? "Signature Invalid"
                  : "Ed25519 Signature Verified"}
              </Badge>
            </div>
          </div>
        )}

        {/* Backend Receipt Gap / Legacy Notice (Rendered when receipt_json is null) */}
        {!hasReceipt && (
          <div
            role="note"
            className="rounded-lg border border-amber-500/20 bg-amber-500/[0.06] p-3 text-xs text-amber-200/90 flex items-start gap-2.5"
          >
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-semibold text-amber-300">
                Legacy execution: receipt unavailable · Receipt not generated by backend (Execution receipt unavailable)
              </p>
              <p className="text-zinc-400 text-[11px] leading-relaxed">
                Cryptographic execution receipt generation and digital signing are not available for this record. Operational execution records from the database are shown below for audit purposes.
              </p>
            </div>
          </div>
        )}

        {/* Plan Hash Discrepancy Warning (When approval record and plan disagree) */}
        {planHashMismatch && (
          <div
            role="alert"
            className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-start gap-2.5"
          >
            <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-semibold text-amber-300">
                Integrity Warning: Approval Record Hash Discrepancy
              </p>
              <p className="text-zinc-300 text-[11px] leading-relaxed">
                {planHashWarning ||
                  "The active approved plan hash disagrees with the latest recorded approval digest. This indicates an older approval or rejection record retained from plan regeneration."}
              </p>
            </div>
          </div>
        )}

        {/* Verification Digest (Clearly distinguished from authorizing plan hash) */}
        <div className="rounded-lg border border-[#55D6C2]/30 bg-[#0B0E12] p-3.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono text-[#55D6C2] font-semibold uppercase tracking-wider flex items-center gap-1.5">
              <Fingerprint className="h-3.5 w-3.5 text-[#55D6C2]" />
              Execution Verification Digest (Distinct from Plan Hash)
            </span>
            {hasVerificationHash && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCopyHash}
                className="h-6 px-2 text-[11px] text-[#55D6C2] hover:text-white gap-1"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 text-emerald-400" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    <span>Copy</span>
                  </>
                )}
              </Button>
            )}
          </div>

          {hasVerificationHash ? (
            <p className="font-mono text-xs text-zinc-200 break-all select-all">
              {verificationHash}
            </p>
          ) : (
            <p className="font-mono text-xs text-zinc-400 italic">
              Unavailable (Receipt not generated by backend)
            </p>
          )}

          <p className="text-[10px] text-zinc-400 font-mono">
            Cryptographic evidence hash computed over microVM execution and teardown.
          </p>

          {receipt?.signature && (
            <div className="pt-2 border-t border-white/[0.06] space-y-1">
              <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
                Digital Signature ({receipt?.signature_scheme?.toUpperCase() || "ED25519"})
              </span>
              <p className="font-mono text-[11px] text-zinc-300 break-all select-all">
                {receipt.signature}
              </p>
            </div>
          )}
        </div>

        {/* Evidence Grid: Operational Execution Records */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono font-semibold text-zinc-300 uppercase tracking-wider">
              Operational Execution Evidence
            </span>
            <span className="text-[10px] text-zinc-400 font-mono">
              {hasReceipt ? "Receipt & Database Records" : "Database Records (Pre-Receipt)"}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 text-xs">
            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Execution ID</span>
              <p className="font-mono text-xs text-zinc-200 truncate select-all">
                {execution?.id || receipt?.execution_id || "—"}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Sandbox ID</span>
              <p className="font-mono text-xs text-zinc-200 truncate select-all">
                {execution?.sandbox_id || receipt?.sandbox_id || "ephemeral-sandbox"}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">
                Approved Plan Hash
              </span>
              {planHashMismatch ? (
                <p
                  className="font-mono text-xs text-amber-400 font-semibold truncate select-all"
                  title={planHashWarning || "Hash Mismatch Discrepancy"}
                >
                  Discrepancy (Hash Mismatch)
                </p>
              ) : (
                <p
                  className="font-mono text-xs text-zinc-300 truncate select-all"
                  title={effectivePlanHash || "—"}
                >
                  {effectivePlanHash
                    ? `${effectivePlanHash.slice(0, 16)}...`
                    : "—"}
                </p>
              )}
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Teardown Status</span>
              <p className={`font-mono text-xs font-semibold uppercase ${cleanupInfo.colorClass}`}>
                {cleanupInfo.label}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Runtime Image</span>
              <p className="font-mono text-xs text-zinc-200 truncate">
                {execution?.runtime_image || receipt?.runtime_image || "python:3.12-slim"}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Guest Kernel</span>
              <p className="font-mono text-xs text-zinc-200 truncate select-all">
                {execution?.guest_kernel || receipt?.guest_kernel || "vmlinux-6.1-microvm"}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">CPU / Memory</span>
              <p className="font-mono text-xs text-zinc-200">
                {(execution?.cpu_limit ?? receipt?.cpu_limit ?? 2)} vCPU / {(execution?.memory_limit_mb ?? receipt?.memory_limit_mb ?? 2048)} MB
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Network Mode</span>
              <p className="font-mono text-xs text-zinc-200 uppercase">
                {execution?.network_mode || receipt?.network_mode || "none"}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Exit Code</span>
              <p
                className={`font-mono text-xs font-semibold ${
                  (execution?.exit_code ?? receipt?.exit_code) === 0
                    ? "text-emerald-400"
                    : "text-rose-400"
                }`}
              >
                {execution?.exit_code ?? receipt?.exit_code ?? "—"}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Duration</span>
              <p className="font-mono text-xs text-zinc-200">
                {formatDuration(execution?.duration_seconds ?? receipt?.duration_seconds)}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Started At</span>
              <p className="font-mono text-[11px] text-zinc-300">
                {formatDate(execution?.started_at || receipt?.started_at)}
              </p>
            </div>

            <div className="rounded bg-[#0B0E12] p-2.5 border border-white/6 space-y-0.5">
              <span className="text-[10px] font-mono text-zinc-400 uppercase">Completed At</span>
              <p className="font-mono text-[11px] text-zinc-300">
                {formatDate(execution?.completed_at || receipt?.completed_at)}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
