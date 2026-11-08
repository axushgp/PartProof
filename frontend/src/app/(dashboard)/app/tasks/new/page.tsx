"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  AlertCircle,
  ArrowLeft,
  ChevronRight,
  Lightbulb,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { taskCreateSchema, TaskCreateFormData } from "@/lib/validation";
import { api, ApiError } from "@/lib/api/client";

const EXAMPLE_PROMPTS = [
  {
    title: "Binary Integrity Audit",
    prompt:
      "Inspect /bin utilities, compute SHA-256 digests for key tools (ls, sh, python3), and write an audit receipt to audit_hashes.csv.",
  },
  {
    title: "Cryptographic Key Benchmark",
    prompt:
      "Generate 50 Ed25519 key pairs using standard cryptography library, compute average generation latency, and output benchmark summary to keygen_benchmark.json.",
  },
  {
    title: "Airgapped Data Transformation",
    prompt:
      "Parse and normalize input dataset with custom sanitization rules, filter out invalid rows, and write clean CSV output without any network dependency.",
  },
];

export default function CreateTaskPage() {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    control,
    formState: { errors, isSubmitting },
  } = useForm<TaskCreateFormData>({
    resolver: zodResolver(taskCreateSchema),
    defaultValues: {
      title: "",
      description: "",
    },
  });

  const descriptionValue = useWatch({ control, name: "description" }) || "";

  const onSubmit = async (data: TaskCreateFormData) => {
    setSubmitError(null);
    try {
      const taskDetail = await api.tasks.create({
        title: data.title?.trim() || null,
        description: data.description.trim(),
      });
      // Navigate to task detail page where the generated plan and policy can be reviewed
      router.push(`/app/tasks/${taskDetail.task.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(err.message || "Failed to create task and generate plan.");
      } else {
        setSubmitError("Network error. Unable to communicate with backend task planner.");
      }
    }
  };

  const handleUsePrompt = (prompt: string, title: string) => {
    setValue("title", title, { shouldValidate: true });
    setValue("description", prompt, { shouldValidate: true });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Breadcrumb / Back Link */}
      <div className="flex items-center gap-2 text-xs text-zinc-400">
        <Link
          href="/app/tasks"
          className="hover:text-white transition-colors flex items-center gap-1"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Tasks</span>
        </Link>
        <ChevronRight className="h-3 w-3 text-zinc-600" />
        <span className="text-zinc-200">New Task Objective</span>
      </div>

      <div className="space-y-1 pb-2 border-b border-white/[0.06]">
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          Create Engineering Task
        </h1>
        <p className="text-xs text-zinc-400">
          Describe the engineering audit, calculation, or script to plan. Vultr AI will formulate a deterministic step-by-step execution plan for your review.
        </p>
      </div>

      {/* Mandatory Blast-Radius-Zero Security Notice */}
      <div
        role="note"
        className="rounded-lg border border-[#55D6C2]/30 bg-[#55D6C2]/10 p-4 text-xs text-zinc-200 flex items-start gap-3 shadow-sm"
      >
        <ShieldAlert className="h-5 w-5 shrink-0 text-[#55D6C2] mt-0.5" />
        <div className="space-y-1">
          <h4 className="font-semibold text-white text-xs">
            Explicit Approval Required Before Execution
          </h4>
          <p className="text-zinc-300 leading-relaxed">
            Submitting this task initiates AI planning and policy evaluation only.{" "}
            <strong className="text-white font-semibold">
              No code will execute until you inspect the generated steps, verify the SHA-256 plan hash, and explicitly confirm approval.
            </strong>
          </p>
        </div>
      </div>

      {submitError && (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-md border border-rose-800/60 bg-rose-950/40 p-4 text-xs text-rose-200"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
          <div className="flex-1 leading-relaxed">{submitError}</div>
        </div>
      )}

      {/* Composer Form */}
      <Card className="bg-[#111820] border-white/8 shadow-sm">
        <CardHeader>
          <CardTitle className="text-base font-semibold text-white">Task Specification</CardTitle>
          <CardDescription className="text-xs text-zinc-400">
            Provide the natural language instructions. Python code will be generated inside the plan for sandbox execution.
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
            {/* Optional Title */}
            <div className="space-y-1.5">
              <label
                htmlFor="task-title"
                className="block text-xs font-medium text-zinc-300"
              >
                Task Title{" "}
                <span className="text-zinc-400 font-normal">(Optional — AI will infer one if omitted)</span>
              </label>
              <Input
                id="task-title"
                placeholder="e.g. SHA-256 Binary Integrity Verification"
                error={Boolean(errors.title)}
                {...register("title")}
              />
              {errors.title && (
                <p className="text-[11px] text-rose-400 font-medium">
                  {errors.title.message}
                </p>
              )}
            </div>

            {/* Required Description */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="task-description"
                  className="block text-xs font-medium text-zinc-300"
                >
                  Objective &amp; Requirements <span className="text-rose-400">*</span>
                </label>
                <span className="text-[11px] font-mono text-zinc-400">
                  {descriptionValue?.length || 0} characters
                </span>
              </div>
              <Textarea
                id="task-description"
                rows={6}
                placeholder="Describe what you want the isolated sandbox to execute, verify, or calculate in natural language or pseudo-code..."
                error={Boolean(errors.description)}
                className="font-sans leading-relaxed"
                {...register("description")}
              />
              {errors.description && (
                <p className="text-[11px] text-rose-400 font-medium">
                  {errors.description.message}
                </p>
              )}
            </div>

            {/* Submit & Cancel */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-white/[0.06]">
              <Button asChild variant="outline" size="sm" className="text-xs">
                <Link href="/app/tasks">Cancel</Link>
              </Button>
              <Button
                type="submit"
                variant="default"
                size="sm"
                className="text-xs font-semibold gap-1.5 min-w-[130px]"
                isLoading={isSubmitting}
              >
                <Sparkles className="h-3.5 w-3.5" />
                <span>{isSubmitting ? "Generating Plan..." : "Generate Plan"}</span>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Example Prompts Library */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
          <Lightbulb className="h-3.5 w-3.5 text-amber-400" />
          <span>Preset Objective Examples</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {EXAMPLE_PROMPTS.map((ex, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleUsePrompt(ex.prompt, ex.title)}
              className="text-left p-3.5 rounded-lg border border-white/8 bg-[#111820] hover:bg-[#151E27] hover:border-white/20 transition-all text-xs space-y-1.5 group select-none"
            >
              <div className="font-semibold text-zinc-200 group-hover:text-[#55D6C2] transition-colors">
                {ex.title}
              </div>
              <p className="text-[11px] text-zinc-400 line-clamp-3 leading-relaxed">
                {ex.prompt}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
