import {
  AlertTriangle,
  Cpu,
  Globe,
  HardDrive,
  Lock,
  Radio,
  ShieldCheck,
  ShieldX,
  Timer,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PolicyEvaluationResult } from "@/types/backend";

interface PolicyInspectorProps {
  policy: PolicyEvaluationResult;
}

export function PolicyInspector({ policy }: PolicyInspectorProps) {
  return (
    <Card className="bg-[#111820] border-white/8 shadow-sm">
      <CardHeader className="pb-3 border-b border-white/[0.06]">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-[#55D6C2]" />
              Deterministic Policy Engine Inspector
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400">
              Deterministic verification against platform blast-radius constraints
            </CardDescription>
          </div>

          <div className="flex items-center gap-2">
            <Badge
              variant={policy.allowed ? "success" : "destructive"}
              className="text-xs font-mono font-semibold"
            >
              {policy.allowed ? "ALLOWED" : "DISALLOWED"}
            </Badge>
            <Badge variant="outline" className="font-mono text-xs text-zinc-400">
              {policy.policy_name} v{policy.policy_version}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-5 text-xs">
        {/* Violations Alert if disallowed */}
        {policy.violations && policy.violations.length > 0 && (
          <div
            role="alert"
            className="rounded-lg border border-rose-800/80 bg-rose-950/40 p-3.5 text-xs text-rose-200 space-y-2"
          >
            <div className="flex items-center gap-2 font-semibold text-rose-100">
              <ShieldX className="h-4 w-4 text-rose-400 shrink-0" />
              <span>Policy Violations Detected ({policy.violations.length})</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-rose-300 pl-1 font-mono text-[11px]">
              {policy.violations.map((violation, idx) => (
                <li key={idx}>{violation}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Warnings Alert (if any) */}
        {policy.warnings && policy.warnings.length > 0 && (
          <div
            role="alert"
            className="rounded-lg border border-amber-800/80 bg-amber-950/40 p-3.5 text-xs text-amber-200 space-y-2"
          >
            <div className="flex items-center gap-2 font-semibold text-amber-100">
              <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
              <span>Policy Warnings ({policy.warnings.length})</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-amber-300 pl-1 text-[11px]">
              {policy.warnings.map((warn, idx) => (
                <li key={idx}>{warn}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Enforced Hardware Limits Grid */}
        <div className="space-y-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold block">
            Approved Sandbox Isolation Limits
          </span>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
            <div className="rounded-md border border-white/6 bg-[#0B0E12] p-2.5 space-y-1">
              <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
                <Globe className="h-3 w-3 text-[#55D6C2]" />
                <span>Network Mode</span>
              </div>
              <p className="font-mono text-xs font-semibold text-white uppercase">
                {policy.network_mode || "none"}
              </p>
            </div>

            <div className="rounded-md border border-white/6 bg-[#0B0E12] p-2.5 space-y-1">
              <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
                <Cpu className="h-3 w-3 text-[#55D6C2]" />
                <span>CPU Limit</span>
              </div>
              <p className="font-mono text-xs font-semibold text-white">
                {policy.cpu_limit} vCPU
              </p>
            </div>

            <div className="rounded-md border border-white/6 bg-[#0B0E12] p-2.5 space-y-1">
              <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
                <HardDrive className="h-3 w-3 text-[#55D6C2]" />
                <span>Memory Bound</span>
              </div>
              <p className="font-mono text-xs font-semibold text-white">
                {policy.memory_limit_mb} MB
              </p>
            </div>

            <div className="rounded-md border border-white/6 bg-[#0B0E12] p-2.5 space-y-1">
              <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
                <Timer className="h-3 w-3 text-[#55D6C2]" />
                <span>Timeout</span>
              </div>
              <p className="font-mono text-xs font-semibold text-white">
                {policy.timeout_seconds}s
              </p>
            </div>

            <div className="rounded-md border border-white/6 bg-[#0B0E12] p-2.5 space-y-1">
              <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
                <Lock className="h-3 w-3 text-[#55D6C2]" />
                <span>Approval Gate</span>
              </div>
              <p className="font-mono text-xs font-semibold text-white">
                {policy.approval_required ? "Required" : "Bypassed"}
              </p>
            </div>

            <div className="rounded-md border border-white/6 bg-[#0B0E12] p-2.5 space-y-1">
              <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
                <Radio className="h-3 w-3 text-[#55D6C2]" />
                <span>Runtime Image</span>
              </div>
              <p className="font-mono text-[11px] font-semibold text-white truncate">
                {policy.image}
              </p>
            </div>
          </div>
        </div>

        {/* Rule Evaluation Results */}
        {policy.rule_results && policy.rule_results.length > 0 && (
          <div className="space-y-2 pt-1">
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold block">
              Automated Rule Evaluations ({policy.rule_results.length})
            </span>

            <div className="space-y-1.5">
              {policy.rule_results.map((rule, idx) => {
                const passed = rule.passed !== false && !rule.violation;
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 rounded bg-[#0B0E12] border border-white/6 text-xs font-mono"
                  >
                    <span className="text-zinc-300">
                      {String(rule.rule || rule.name || `Rule #${idx + 1}`)}
                    </span>
                    <Badge
                      variant={passed ? "success" : "destructive"}
                      className="text-[10px]"
                    >
                      {passed ? "PASSED" : "VIOLATED"}
                    </Badge>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
