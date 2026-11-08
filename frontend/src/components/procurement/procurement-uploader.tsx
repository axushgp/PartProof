"use client";

import React, { useState } from "react";
import { FileSpreadsheet, CheckCircle2, AlertTriangle, Sparkles, Plus, Trash2, ArrowRight } from "lucide-react";

interface ProcurementUploaderProps {
  onLoadDemo: () => Promise<void>;
  onAnalyzeFiles: (bomFile: File | null, quoteFiles: File[], supplierNames: string[]) => Promise<void>;
  isLoading: boolean;
}

export function ProcurementUploader({ onLoadDemo, onAnalyzeFiles, isLoading }: ProcurementUploaderProps) {
  const [bomFile, setBomFile] = useState<File | null>(null);
  const [quoteFiles, setQuoteFiles] = useState<File[]>([]);
  const [supplierNames, setSupplierNames] = useState<string[]>(["Supplier A", "Supplier B", "Supplier C"]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleBomChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (file.size > 15 * 1024 * 1024) {
        setErrorMsg("BOM file exceeds 15MB limit.");
        return;
      }
      setBomFile(file);
      setErrorMsg(null);
    }
  };

  const handleQuoteFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      if (files.some((f) => f.size > 15 * 1024 * 1024)) {
        setErrorMsg("One or more quotation files exceed 15MB limit.");
        return;
      }
      setQuoteFiles((prev) => [...prev, ...files].slice(0, 3));
      setErrorMsg(null);
    }
  };

  const removeQuoteFile = (index: number) => {
    setQuoteFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const updateSupplierName = (index: number, val: string) => {
    setSupplierNames((prev) => {
      const next = [...prev];
      next[index] = val;
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bomFile && quoteFiles.length === 0) {
      setErrorMsg("Please upload an engineering BOM and at least two supplier quotations, or load the preloaded demo case.");
      return;
    }
    if (quoteFiles.length < 2) {
      setErrorMsg("At least two supplier quotations are required for side-by-side reconciliation.");
      return;
    }
    setErrorMsg(null);
    await onAnalyzeFiles(bomFile, quoteFiles, supplierNames.slice(0, quoteFiles.length));
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl backdrop-blur-md">
      {/* Synthetic Demo Header Banner */}
      <div className="mb-6 flex flex-col gap-4 rounded-xl border border-teal-500/30 bg-gradient-to-r from-teal-950/40 via-slate-900 to-slate-900 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-teal-400" />
            <h3 className="text-base font-semibold text-slate-100">Live Demonstration Case</h3>
            <span className="rounded-full bg-teal-500/20 px-2.5 py-0.5 text-xs font-mono text-teal-300">
              1-Click EV Powertrain Showcase
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-300">
            Experience the complete investigation immediately without uploading files: EV Powertrain BOM (bearings, bolts, controller, brakes, wiring) across 3 realistic supplier quotes.
          </p>
        </div>
        <button
          type="button"
          disabled={isLoading}
          onClick={onLoadDemo}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-teal-500 px-5 py-2.5 text-sm font-semibold text-slate-950 shadow-lg shadow-teal-500/20 transition hover:bg-teal-400 active:scale-95 disabled:opacity-50"
        >
          <Sparkles className="h-4 w-4 fill-current" />
          Load Synthetic Demo Case
        </button>
      </div>

      <div className="relative mb-6">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-slate-800" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-slate-900 px-3 text-slate-400 font-mono">Or Upload Custom Documents</span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {/* BOM Upload Box */}
          <div className="rounded-lg border border-slate-700/80 bg-slate-950/60 p-4">
            <div className="flex items-center justify-between">
              <label className="text-sm font-semibold text-slate-200">1. Engineering BOM</label>
              <span className="text-xs text-slate-400 font-mono">CSV, XLSX, PDF</span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Approved bill of materials with part numbers, specifications, and required quantities.
            </p>

            <div className="mt-3">
              {!bomFile ? (
                <label className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-700 p-6 transition hover:border-teal-500/60 hover:bg-slate-900/50 cursor-pointer">
                  <FileSpreadsheet className="h-8 w-8 text-slate-400" />
                  <span className="mt-2 text-xs font-medium text-slate-300">Select or drop BOM document</span>
                  <span className="text-[10px] text-slate-400 mt-1">Up to 15MB</span>
                  <input
                    type="file"
                    accept=".csv,.xlsx,.pdf"
                    onChange={handleBomChange}
                    className="hidden"
                  />
                </label>
              ) : (
                <div className="flex items-center justify-between rounded-lg border border-teal-500/40 bg-teal-950/30 p-3">
                  <div className="flex items-center gap-2 overflow-hidden">
                    <CheckCircle2 className="h-5 w-5 shrink-0 text-teal-400" />
                    <div className="truncate">
                      <p className="truncate text-xs font-medium text-slate-200">{bomFile.name}</p>
                      <p className="text-[10px] text-slate-400 font-mono">{(bomFile.size / 1024).toFixed(1)} KB</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setBomFile(null)}
                    className="rounded p-1 text-slate-400 hover:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Quotations Upload Box */}
          <div className="rounded-lg border border-slate-700/80 bg-slate-950/60 p-4">
            <div className="flex items-center justify-between">
              <label className="text-sm font-semibold text-slate-200">2. Supplier Quotations (2-3)</label>
              <span className="text-xs text-slate-400 font-mono">{quoteFiles.length}/3 Uploaded</span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Quotes with unit rates, pack sizes, MOQs, freight terms, and delivery lead times.
            </p>

            <div className="mt-3 space-y-2">
              {quoteFiles.map((f, idx) => (
                <div key={idx} className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 p-2.5">
                  <input
                    type="text"
                    value={supplierNames[idx] || `Supplier ${chr(65 + idx)}`}
                    onChange={(e) => updateSupplierName(idx, e.target.value)}
                    placeholder="Supplier Name"
                    className="w-32 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200 font-medium focus:border-teal-500 focus:outline-none"
                  />
                  <div className="flex-1 truncate">
                    <p className="truncate text-xs text-slate-300">{f.name}</p>
                    <p className="text-[10px] text-slate-400 font-mono">{(f.size / 1024).toFixed(1)} KB</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeQuoteFile(idx)}
                    className="rounded p-1 text-slate-400 hover:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}

              {quoteFiles.length < 3 && (
                <label className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-slate-700 p-3 text-xs text-slate-400 transition hover:border-teal-500/60 hover:text-slate-200 cursor-pointer">
                  <Plus className="h-4 w-4" />
                  <span>Add Quotation File ({3 - quoteFiles.length} remaining)</span>
                  <input
                    type="file"
                    accept=".csv,.xlsx,.pdf"
                    onChange={handleQuoteFilesChange}
                    className="hidden"
                  />
                </label>
              )}
            </div>
          </div>
        </div>

        {/* Notice on Text vs Scanned PDFs */}
        <div className="flex items-start gap-2.5 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-400">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
          <p>
            <strong className="text-slate-300">Digital Document Standards:</strong> Uploads must be digital CSV, XLSX spreadsheets, or text-based PDFs. Scanned image PDFs will trigger an explicit OCR warning as required by audit policies.
          </p>
        </div>

        {errorMsg && (
          <div className="rounded-lg border border-red-500/30 bg-red-950/30 p-3 text-xs text-red-300">
            {errorMsg}
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isLoading || (!bomFile && quoteFiles.length === 0)}
            className="inline-flex items-center gap-2 rounded-lg bg-teal-500 px-6 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-teal-400 disabled:opacity-50"
          >
            {isLoading ? "Extracting & Reconciling..." : "Extract & Analyze Procurement"}
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}

function chr(code: number): string {
  return String.fromCharCode(code);
}
