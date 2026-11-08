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
  Database,
  Download,
  FileCode,
  FileSpreadsheet,
  FolderUp,
  Info,
  Lightbulb,
  ShieldAlert,
  Sparkles,
  Terminal,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { taskCreateSchema, TaskCreateFormData } from "@/lib/validation";
import { api, ApiError } from "@/lib/api/client";
import { TaskInputUpload } from "@/types/backend";

type InputMode = "user_upload" | "synthetic_sample" | "prompt_only";

interface UploadedFileInfo extends TaskInputUpload {
  lastModified?: number;
}

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
    title: "Algorithm Performance Profiling",
    prompt:
      "Synthesize random prime generation and benchmark Miller-Rabin vs naive factoring with 10,000 iterations, outputting performance metrics to benchmark.json.",
  },
];

const SAMPLE_CSV_PREVIEW = [
  { record_id: "REC-001", timestamp: "2026-11-08T08:00:00Z", pack_voltage: "398.4", current_amps: "42.1", cell_temp_c: "28.5", status: "NORMAL" },
  { record_id: "REC-002", timestamp: "2026-11-08T08:00:01Z", pack_voltage: "398.2", current_amps: "44.3", cell_temp_c: "28.6", status: "NORMAL" },
  { record_id: "REC-003", timestamp: "2026-11-08T08:00:02Z", pack_voltage: "397.9", current_amps: "46.0", cell_temp_c: "28.8", status: "NORMAL" },
  { record_id: "REC-004", timestamp: "2026-11-08T08:00:03Z", pack_voltage: "", current_amps: "45.8", cell_temp_c: "28.9", status: "DEFECT (Missing Voltage)" },
  { record_id: "REC-005", timestamp: "2026-11-08T08:00:04Z", pack_voltage: "397.4", current_amps: "47.2", cell_temp_c: "29.1", status: "NORMAL" },
  { record_id: "REC-006", timestamp: "2026-11-08T08:00:05Z", pack_voltage: "397.1", current_amps: "48.0", cell_temp_c: "29.2", status: "NORMAL" },
  { record_id: "REC-007", timestamp: "2026/11/08 08:00:06", pack_voltage: "396.8", current_amps: "48.5", cell_temp_c: "29.4", status: "DEFECT (Non-ISO Timestamp)" },
  { record_id: "REC-008", timestamp: "2026-11-08T08:00:07Z", pack_voltage: "396.5", current_amps: "49.1", cell_temp_c: "29.5", status: "NORMAL" },
  { record_id: "REC-009", timestamp: "2026-11-08T08:00:08Z", pack_voltage: "396.2", current_amps: "49.6", cell_temp_c: "29.7", status: "NORMAL" },
  { record_id: "REC-010", timestamp: "2026-11-08T08:00:09Z", pack_voltage: "396.0", current_amps: "50.0", cell_temp_c: "29.8", status: "NORMAL" },
  { record_id: "REC-011", timestamp: "2026-11-08T08:00:10Z", pack_voltage: "395.7", current_amps: "50.4", cell_temp_c: "30.0", status: "NORMAL" },
  { record_id: "REC-012", timestamp: "2026-11-08T08:00:11Z", pack_voltage: "395.5", current_amps: "51.0", cell_temp_c: "145.2", status: "DEFECT (Thermal Outlier)" },
  { record_id: "REC-013", timestamp: "2026-11-08T08:00:12Z", pack_voltage: "395.2", current_amps: "50.8", cell_temp_c: "30.3", status: "NORMAL" },
  { record_id: "REC-014", timestamp: "2026-11-08T08:00:13Z", pack_voltage: "395.0", current_amps: "50.5", cell_temp_c: "30.4", status: "NORMAL" },
  { record_id: "REC-015", timestamp: "2026-11-08T08:00:14Z", pack_voltage: "394.8", current_amps: "50.1", cell_temp_c: "30.6", status: "NORMAL" },
];

async function bufferToSha256(buffer: ArrayBuffer): Promise<string> {
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

function bufferToBase64(buffer: ArrayBuffer): string {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export default function CreateTaskPage() {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [inputMode, setInputMode] = useState<InputMode>("prompt_only");
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFileInfo[]>([]);
  const [showSamplePreview, setShowSamplePreview] = useState<boolean>(false);
  const [isProcessingFiles, setIsProcessingFiles] = useState<boolean>(false);

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
      input_mode: "prompt_only",
    },
  });

  const descriptionValue = useWatch({ control, name: "description" }) || "";

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setIsProcessingFiles(true);
    setSubmitError(null);

    const newFiles: UploadedFileInfo[] = [];
    try {
      for (let i = 0; i < e.target.files.length; i++) {
        const file = e.target.files[i];
        const buffer = await file.arrayBuffer();
        const sha256 = await bufferToSha256(buffer);
        const b64 = bufferToBase64(buffer);
        const ext = file.name.split(".").pop()?.toLowerCase() || "data";

        newFiles.push({
          filename: file.name,
          size_bytes: file.size,
          detected_format: ext,
          sha256,
          file_content_b64: b64,
          lastModified: file.lastModified,
        });
      }

      setUploadedFiles((prev) => [...prev, ...newFiles]);
    } catch (err: unknown) {
      console.error("Error reading file:", err);
      setSubmitError("Failed to read and hash input files. Please try again.");
    } finally {
      setIsProcessingFiles(false);
      e.target.value = "";
    }
  };

  const handleRemoveFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSelectMode = (mode: InputMode) => {
    setInputMode(mode);
    setSubmitError(null);

    if (mode === "synthetic_sample") {
      setValue("title", "EV Telemetry Cleaning & Anomaly Audit", { shouldValidate: true });
      setValue(
        "description",
        "Inspect and clean /workspace/input/sample_telemetry_raw.csv. Detect telemetry anomalies: REC-004 (missing voltage), REC-007 (non-ISO timestamp), and REC-012 (temperature outlier of 145.2°C). Output cleaned records to /workspace/output/telemetry_clean.csv and anomaly findings to /workspace/output/anomalies.json.",
        { shouldValidate: true }
      );
    }
  };

  const onSubmit = async (data: TaskCreateFormData) => {
    setSubmitError(null);

    if (inputMode === "user_upload" && uploadedFiles.length === 0) {
      setSubmitError("Please select at least one file to upload for user-upload mode, or switch to prompt-only.");
      return;
    }

    try {
      const taskDetail = await api.tasks.create({
        title: data.title?.trim() || null,
        description: data.description.trim(),
        input_mode: inputMode,
        input_files:
          inputMode === "user_upload"
            ? uploadedFiles.map((f) => ({
                filename: f.filename,
                size_bytes: f.size_bytes,
                detected_format: f.detected_format,
                sha256: f.sha256,
                file_content_b64: f.file_content_b64,
              }))
            : undefined,
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
          Describe the engineering audit, calculation, or script to plan. Vultr AI will formulate a step-by-step execution plan for your review.
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

      {/* Task Input Mode Selector */}
      <Card className="bg-[#111820] border-white/8 shadow-sm">
        <CardHeader className="pb-3 border-b border-white/[0.06]">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
                <Database className="h-4 w-4 text-[#55D6C2]" />
                Task Input Provenance
              </CardTitle>
              <CardDescription className="text-xs text-zinc-400">
                Choose how input data is provided to the isolated MicroVM environment (/workspace/input/).
              </CardDescription>
            </div>
            <div className="flex rounded-lg border border-white/10 bg-[#0B0E12] p-1 text-xs font-mono">
              <button
                type="button"
                onClick={() => handleSelectMode("prompt_only")}
                className={`flex items-center gap-1.5 rounded px-3 py-1.5 transition ${
                  inputMode === "prompt_only"
                    ? "bg-[#55D6C2] font-semibold text-slate-950"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <Terminal className="h-3.5 w-3.5" />
                <span>Prompt-Only</span>
              </button>
              <button
                type="button"
                onClick={() => handleSelectMode("synthetic_sample")}
                className={`flex items-center gap-1.5 rounded px-3 py-1.5 transition ${
                  inputMode === "synthetic_sample"
                    ? "bg-[#55D6C2] font-semibold text-slate-950"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <FileSpreadsheet className="h-3.5 w-3.5" />
                <span>Synthetic Sample</span>
              </button>
              <button
                type="button"
                onClick={() => handleSelectMode("user_upload")}
                className={`flex items-center gap-1.5 rounded px-3 py-1.5 transition ${
                  inputMode === "user_upload"
                    ? "bg-[#55D6C2] font-semibold text-slate-950"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <FolderUp className="h-3.5 w-3.5" />
                <span>User Files</span>
              </button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="pt-4">
          {/* Mode A: User Upload */}
          {inputMode === "user_upload" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-xs text-zinc-300">
                  Upload CSV, JSON, TXT, or script files to stage into <code className="font-mono text-teal-400">/workspace/input/</code> inside the microVM.
                </div>
                <label className="cursor-pointer inline-flex items-center gap-1.5 rounded-md bg-[#55D6C2] px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-[#42BCA9] transition">
                  <FolderUp className="h-3.5 w-3.5" />
                  <span>Choose Files</span>
                  <input
                    type="file"
                    multiple
                    className="hidden"
                    onChange={handleFileUpload}
                    disabled={isProcessingFiles}
                  />
                </label>
              </div>

              {isProcessingFiles && (
                <div className="text-xs text-teal-400 font-mono animate-pulse">
                  Computing client-side SHA-256 hashes and preparing manifests...
                </div>
              )}

              {uploadedFiles.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-mono text-zinc-400 font-medium">
                    Staged Input Files ({uploadedFiles.length}):
                  </div>
                  <div className="space-y-1.5">
                    {uploadedFiles.map((file, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between rounded-lg border border-white/8 bg-[#0B0E12] p-2.5 text-xs font-mono"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <FileCode className="h-4 w-4 text-teal-400 shrink-0" />
                          <div className="truncate">
                            <span className="font-semibold text-white">{file.filename}</span>
                            <span className="ml-2 text-[10px] text-zinc-400">
                              ({(file.size_bytes / 1024).toFixed(1)} KB)
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <span className="text-[10px] text-zinc-400 hidden sm:inline" title={file.sha256 || ""}>
                            SHA-256: {file.sha256?.substring(0, 12)}...
                          </span>
                          <button
                            type="button"
                            onClick={() => handleRemoveFile(idx)}
                            className="text-zinc-500 hover:text-rose-400 transition"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-white/10 p-6 text-center text-xs text-zinc-400">
                  No files selected. Click &quot;Choose Files&quot; to add test datasets or configuration files.
                </div>
              )}
            </div>
          )}

          {/* Mode B: Synthetic Sample Dataset */}
          {inputMode === "synthetic_sample" && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg border border-teal-500/30 bg-teal-950/20 p-3.5">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-teal-500/20 px-2 py-0.5 text-[10px] font-mono font-semibold text-teal-300">
                      Synthetic Sample Dataset
                    </span>
                    <span className="font-mono text-xs text-white">sample_telemetry_raw.csv</span>
                    <span className="text-xs text-zinc-400">(15 records, 978 B)</span>
                  </div>
                  <p className="text-xs text-zinc-300">
                    Pre-configured EV powertrain telemetry dataset with intentional defects:
                    <strong className="text-teal-300"> REC-004</strong> (missing voltage),{" "}
                    <strong className="text-teal-300">REC-007</strong> (non-ISO timestamp), and{" "}
                    <strong className="text-teal-300">REC-012</strong> (thermal outlier 145.2°C).
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="text-xs gap-1.5 h-8 font-mono border-teal-500/30 text-teal-300 hover:bg-teal-950/40"
                    asChild
                  >
                    <a href="/api/tasks/sample-dataset/download" download="sample_telemetry_raw.csv">
                      <Download className="h-3.5 w-3.5" />
                      <span>Download CSV</span>
                    </a>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-xs h-8 text-zinc-300 hover:text-white"
                    onClick={() => setShowSamplePreview(!showSamplePreview)}
                  >
                    {showSamplePreview ? "Hide Preview" : "Preview 15 Rows"}
                  </Button>
                </div>
              </div>

              {/* Sample Table Preview */}
              {showSamplePreview && (
                <div className="overflow-x-auto rounded-lg border border-white/8 bg-[#0B0E12] max-h-60 overflow-y-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="border-b border-white/10 bg-white/[0.02] text-zinc-400 sticky top-0">
                      <tr>
                        <th className="px-3 py-2">record_id</th>
                        <th className="px-3 py-2">timestamp</th>
                        <th className="px-3 py-2 text-right">pack_voltage</th>
                        <th className="px-3 py-2 text-right">current_amps</th>
                        <th className="px-3 py-2 text-right">cell_temp_c</th>
                        <th className="px-3 py-2">status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {SAMPLE_CSV_PREVIEW.map((row) => (
                        <tr
                          key={row.record_id}
                          className={row.status !== "NORMAL" ? "bg-amber-950/20 text-amber-300" : "text-zinc-300"}
                        >
                          <td className="px-3 py-1.5 font-semibold">{row.record_id}</td>
                          <td className="px-3 py-1.5">{row.timestamp}</td>
                          <td className="px-3 py-1.5 text-right">{row.pack_voltage || "<missing>"}</td>
                          <td className="px-3 py-1.5 text-right">{row.current_amps}</td>
                          <td className="px-3 py-1.5 text-right">{row.cell_temp_c}</td>
                          <td className="px-3 py-1.5 text-[10px]">
                            {row.status !== "NORMAL" ? (
                              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-amber-300 font-semibold">
                                {row.status}
                              </span>
                            ) : (
                              <span className="text-zinc-500">Normal</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Mode C: Prompt Only */}
          {inputMode === "prompt_only" && (
            <div className="flex items-start gap-2.5 rounded-lg border border-white/8 bg-[#0B0E12] p-3 text-xs text-zinc-400">
              <Info className="h-4 w-4 text-zinc-400 shrink-0 mt-0.5" />
              <div>
                <strong className="text-zinc-200">Prompt-Only Task:</strong> No external input files will be staged into <code className="font-mono text-teal-400">/workspace/input/</code>. The plan must perform calculations, benchmarks, or code synthesis directly in Python.
              </div>
            </div>
          )}
        </CardContent>
      </Card>

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
