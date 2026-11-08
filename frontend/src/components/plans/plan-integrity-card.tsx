"use client";

import { useState } from "react";
import { Check, Copy, Fingerprint } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface PlanIntegrityCardProps {
  planHash: string;
}

export function PlanIntegrityCard({ planHash }: PlanIntegrityCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(planHash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <Card className="bg-[#111820] border-[#55D6C2]/30 shadow-md">
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Fingerprint className="h-4 w-4 text-[#55D6C2]" />
            <span className="text-xs font-semibold text-white">
              Cryptographic Plan Digest (SHA-256)
            </span>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleCopy}
            className="h-7 px-2.5 text-xs text-[#55D6C2] hover:text-white hover:bg-[#55D6C2]/10 gap-1.5"
            title="Copy SHA-256 hash"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span>Copy Hash</span>
              </>
            )}
          </Button>
        </div>

        <div className="p-2.5 rounded bg-[#0B0E12] border border-white/8">
          <p className="font-mono text-xs text-[#55D6C2] break-all tracking-wider select-all">
            {planHash}
          </p>
        </div>

        <p className="text-[11px] text-zinc-400 leading-relaxed">
          This 64-character SHA-256 digest deterministically hashes the plan title, steps, code, and policy constraints. When you approve, this exact hash is cryptographically bound to the execution record and re-verified before guest microVM launch.
        </p>
      </CardContent>
    </Card>
  );
}
