import { Terminal, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/ui/code-block";
import { PlanStepSchema } from "@/types/backend";

interface PlanStepsProps {
  steps: PlanStepSchema[];
}

export function PlanSteps({ steps }: PlanStepsProps) {
  return (
    <Card className="bg-[#111820] border-white/8 shadow-sm">
      <CardHeader className="pb-3 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
              <Terminal className="h-4 w-4 text-[#55D6C2]" />
              Execution Steps ({steps.length})
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400">
              Ordered guest Python scripts generated for isolated execution
            </CardDescription>
          </div>
          <Badge variant="outline" className="font-mono text-xs">
            Airgapped Python 3.12
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-6">
        {steps.map((step, idx) => (
          <div
            key={step.step_id || idx}
            className="rounded-lg border border-white/8 bg-[#0B0E12] p-4 space-y-3"
          >
            {/* Step Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-2 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#55D6C2]/20 border border-[#55D6C2]/40 text-[#55D6C2] font-mono text-xs font-bold shrink-0">
                  {idx + 1}
                </span>
                <span className="font-mono text-xs font-semibold text-zinc-200">
                  {step.step_id}
                </span>
                <span className="text-xs text-zinc-400 font-medium">
                  — {step.description}
                </span>
              </div>

              <div className="flex items-center gap-2 self-start sm:self-center">
                <Badge variant="secondary" className="font-mono text-[10px] uppercase">
                  Runtime: {step.execution_type}
                </Badge>
              </div>
            </div>

            {/* Step Code Block */}
            <div className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold block">
                Source Script
              </span>
              <CodeBlock
                code={step.code}
                language={step.execution_type}
                title={`${step.step_id}.py`}
              />
            </div>

            {/* Expected Output */}
            {step.expected_output && (
              <div className="flex items-start gap-2 pt-1 text-xs text-zinc-400">
                <Target className="h-3.5 w-3.5 text-zinc-500 shrink-0 mt-0.5" />
                <span>
                  <strong className="text-zinc-300 font-medium">Expected Result:</strong>{" "}
                  {step.expected_output}
                </span>
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
