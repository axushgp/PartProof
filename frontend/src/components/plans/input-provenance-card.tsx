"use client";

import React from "react";
import { Database, FileCode, FileSpreadsheet, Terminal, Info, CheckCircle2, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { TaskInputProvenance } from "@/types/backend";

interface InputProvenanceCardProps {
  provenance?: TaskInputProvenance | null;
}

export function InputProvenanceCard({ provenance }: InputProvenanceCardProps) {
  const mode = provenance?.mode || "prompt_only";
  const files = provenance?.files || [];

  return (
    <Card className="bg-[#111820] border-white/8 shadow-sm">
      <CardHeader className="pb-3 border-b border-white/[0.06]">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
              <Database className="h-4 w-4 text-[#55D6C2]" />
              Input Provenance &amp; Staging
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400">
              Input data mounted into <code className="font-mono text-teal-400">/workspace/input/</code> inside the isolated guest microVM.
            </CardDescription>
          </div>
          <div>
            {mode === "synthetic_sample" ? (
              <span className="rounded-full border border-teal-500/30 bg-teal-950/40 px-3 py-1 text-xs font-mono font-semibold text-teal-300 flex items-center gap-1.5">
                <FileSpreadsheet className="h-3.5 w-3.5" />
                Synthetic Sample Dataset
              </span>
            ) : mode === "user_upload" ? (
              <span className="rounded-full border border-indigo-500/30 bg-indigo-950/40 px-3 py-1 text-xs font-mono font-semibold text-indigo-300 flex items-center gap-1.5">
                <FileCode className="h-3.5 w-3.5" />
                User Uploaded ({files.length} file{files.length === 1 ? "" : "s"})
              </span>
            ) : (
              <span className="rounded-full border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs font-mono font-semibold text-zinc-300 flex items-center gap-1.5">
                <Terminal className="h-3.5 w-3.5" />
                Prompt-Only Task
              </span>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {mode === "synthetic_sample" && (
          <div className="space-y-3">
            <div className="flex items-start gap-2.5 rounded-lg border border-teal-500/20 bg-teal-950/20 p-3 text-xs text-zinc-300">
              <Info className="h-4 w-4 text-teal-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="font-semibold text-teal-300">
                  Autonomous Benchmark Sample Staged
                </p>
                <p className="text-[11px] text-zinc-300 leading-relaxed">
                  {provenance?.disclaimer ||
                    "Pre-configured 15-record EV powertrain telemetry with intentional edge cases: REC-004 (missing voltage reading), REC-007 (non-ISO timestamp string), and REC-012 (temperature outlier of 145.2°C)."}
                </p>
              </div>
            </div>

            {files.map((file, idx) => (
              <div
                key={idx}
                className="rounded-lg border border-white/8 bg-[#0B0E12] p-3 text-xs font-mono space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    <span className="font-semibold text-white">{file.filename}</span>
                    <span className="text-[11px] text-zinc-400">({file.size_bytes} bytes)</span>
                  </div>
                  <span className="rounded bg-teal-500/10 px-2 py-0.5 text-[10px] text-teal-300 uppercase">
                    {file.detected_format || "csv"}
                  </span>
                </div>
                <div className="text-[11px] text-zinc-400 break-all">
                  SHA-256: <span className="text-zinc-300">{file.sha256}</span>
                </div>
                <div className="text-[10px] text-zinc-500">
                  Guest Mount: <code className="text-teal-400">/workspace/input/{file.filename}</code>
                </div>
              </div>
            ))}
          </div>
        )}

        {mode === "user_upload" && (
          <div className="space-y-2">
            {files.length > 0 ? (
              files.map((file, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-white/8 bg-[#0B0E12] p-3 text-xs font-mono space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      <span className="font-semibold text-white">{file.filename}</span>
                      <span className="text-[11px] text-zinc-400">
                        ({(file.size_bytes / 1024).toFixed(1)} KB)
                      </span>
                    </div>
                    <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] text-indigo-300 uppercase">
                      {file.detected_format || "file"}
                    </span>
                  </div>
                  <div className="text-[11px] text-zinc-400 break-all">
                    SHA-256: <span className="text-zinc-300">{file.sha256}</span>
                  </div>
                  <div className="text-[10px] text-zinc-500">
                    Guest Mount: <code className="text-teal-400">/workspace/input/{file.filename}</code>
                  </div>
                </div>
              ))
            ) : (
              <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-950/20 p-3 text-xs text-amber-300">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Mode marked as user_upload, but no files were attached to the plan manifest.</span>
              </div>
            )}
          </div>
        )}

        {mode === "prompt_only" && (
          <div className="flex items-start gap-2.5 rounded-lg border border-white/8 bg-[#0B0E12] p-3 text-xs text-zinc-400">
            <Info className="h-4 w-4 text-zinc-500 shrink-0 mt-0.5" />
            <div>
              <strong className="text-zinc-200">No external input files staged:</strong> This task operates in prompt-only mode. All calculations, code generation, and assertions run without mounted input files under <code className="font-mono text-zinc-300">/workspace/input/</code>, verified by SEC-007.
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
