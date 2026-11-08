import { useState } from "react";
import { ChevronDown, ChevronRight, Terminal } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/ui/code-block";
import { ExecutionStepRead } from "@/types/backend";
import { formatDate } from "@/lib/formatters";

interface StepLogsViewerProps {
  steps: ExecutionStepRead[];
}

export function StepLogsViewer({ steps }: StepLogsViewerProps) {
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>(() => {
    // Expand all steps by default for immediate visibility
    const initial: Record<string, boolean> = {};
    steps.forEach((s) => {
      initial[s.id] = true;
    });
    return initial;
  });

  const toggleStep = (id: string) => {
    setExpandedSteps((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <Card className="bg-[#111820] border-white/8 shadow-sm">
      <CardHeader className="pb-3 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
              <Terminal className="h-4 w-4 text-[#55D6C2]" />
              Guest MicroVM Execution Logs ({steps.length} Steps)
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400">
              Captured stdout, stderr, and process exit codes from isolated sandbox
            </CardDescription>
          </div>
          <Badge variant="outline" className="font-mono text-xs">
            Zero Network Guest
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {steps.length === 0 ? (
          <p className="text-xs text-zinc-400 py-4 text-center">
            No execution step outputs recorded yet.
          </p>
        ) : (
          steps.map((step) => {
            const isExpanded = expandedSteps[step.id] ?? true;
            const isSucceeded = step.status === "succeeded";
            const isFailed = step.status === "failed";

            return (
              <div
                key={step.id}
                className="rounded-lg border border-white/8 bg-[#0B0E12] overflow-hidden"
              >
                {/* Step header / toggle */}
                <button
                  type="button"
                  onClick={() => toggleStep(step.id)}
                  className="w-full flex items-center justify-between p-3.5 hover:bg-white/[0.03] transition-colors text-left"
                >
                  <div className="flex items-center gap-2.5">
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4 text-zinc-400 shrink-0" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-zinc-400 shrink-0" />
                    )}

                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-white">
                        Step #{step.step_number}
                      </span>
                      <span className="text-xs text-zinc-300 font-medium">
                        — {step.description}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5">
                    {step.exit_code !== null && step.exit_code !== undefined && (
                      <span
                        className={`font-mono text-[10px] px-2 py-0.5 rounded ${
                          step.exit_code === 0
                            ? "bg-emerald-950/60 text-emerald-300 border border-emerald-800/60"
                            : "bg-rose-950/60 text-rose-300 border border-rose-800/60"
                        }`}
                      >
                        exit: {step.exit_code}
                      </span>
                    )}

                    <Badge
                      variant={isSucceeded ? "success" : isFailed ? "destructive" : "secondary"}
                      className="font-mono text-[10px] uppercase"
                    >
                      {step.status}
                    </Badge>
                  </div>
                </button>

                {/* Collapsible Content */}
                {isExpanded && (
                  <div className="p-4 pt-1 border-t border-white/[0.06] space-y-3 text-xs">
                    {/* Timing */}
                    <div className="flex items-center gap-4 text-[11px] text-zinc-400 font-mono">
                      <span>Started: {formatDate(step.started_at)}</span>
                      {step.completed_at && <span>Completed: {formatDate(step.completed_at)}</span>}
                    </div>

                    {/* Code Executed (if stored) */}
                    {step.code && (
                      <div className="space-y-1">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block">
                          Executed Python Script
                        </span>
                        <CodeBlock
                          code={step.code}
                          language="python"
                          title={`step_${step.step_number}_exec.py`}
                          maxHeight="max-h-48"
                        />
                      </div>
                    )}

                    {/* Stdout */}
                    <div className="space-y-1">
                      <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block">
                        stdout
                      </span>
                      <div
                        data-lenis-prevent
                        className="rounded-md border border-white/6 bg-[#080A0D] p-3 font-mono text-[11px] text-zinc-200 overflow-auto max-h-56 leading-relaxed select-text"
                      >
                        {step.stdout ? (
                          <pre className="m-0 whitespace-pre-wrap">{step.stdout}</pre>
                        ) : (
                          <span className="text-zinc-600 italic">No console output recorded</span>
                        )}
                      </div>
                    </div>

                    {/* Stderr (if present) */}
                    {step.stderr && (
                      <div className="space-y-1">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-rose-400 font-semibold block">
                          stderr
                        </span>
                        <div
                          data-lenis-prevent
                          className="rounded-md border border-rose-900/60 bg-rose-950/20 p-3 font-mono text-[11px] text-rose-300 overflow-auto max-h-56 leading-relaxed select-text"
                        >
                          <pre className="m-0 whitespace-pre-wrap">{step.stderr}</pre>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
