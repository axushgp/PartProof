"use client";

import React, { useState } from "react";
import { AlertOctagon, CheckCircle2, DollarSign, Filter } from "lucide-react";
import { DiscrepancyFinding } from "@/types/procurement";

interface DiscrepancyRegisterProps {
  discrepancies: DiscrepancyFinding[];
}

export function DiscrepancyRegister({ discrepancies }: DiscrepancyRegisterProps) {
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [supplierFilter, setSupplierFilter] = useState<string>("all");

  const suppliers = Array.from(new Set(discrepancies.map((d) => d.supplier_name)));

  const filtered = discrepancies.filter((d) => {
    if (severityFilter !== "all" && d.severity !== severityFilter) return false;
    if (supplierFilter !== "all" && d.supplier_name !== supplierFilter) return false;
    return true;
  });

  const criticalCount = discrepancies.filter((d) => d.severity === "critical").length;
  const warningCount = discrepancies.filter((d) => d.severity === "warning").length;
  const totalFinancialImpact = discrepancies.reduce(
    (acc, d) => acc + (d.financial_impact ? Number(d.financial_impact) : 0),
    0
  );

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <AlertOctagon className="h-5 w-5 text-red-400" />
            <h3 className="text-base font-semibold text-slate-100">Procurement Forensics & Discrepancy Register</h3>
            <span className="rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-mono font-medium text-red-400 border border-red-500/20">
              {discrepancies.length} Findings
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Automated detection across 14 repeatable audit rules: MOQ inventory traps, unbundled freight, spec substitutions, and pack-size ambiguities.
          </p>
        </div>

        {/* Financial Exposure KPI Pill */}
        {totalFinancialImpact > 0 && (
          <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-950/40 px-3.5 py-2 font-mono">
            <DollarSign className="h-4 w-4 text-amber-400" />
            <span className="text-xs text-amber-300 font-semibold">
              +${totalFinancialImpact.toFixed(2)} Hidden Exposure Flagged
            </span>
          </div>
        )}
      </div>

      {/* Filter Bar */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-1.5 font-mono">
          <Filter className="h-3.5 w-3.5 text-slate-400 mr-1" />
          <button
            onClick={() => setSeverityFilter("all")}
            className={`rounded px-2.5 py-1 transition ${
              severityFilter === "all" ? "bg-slate-700 text-slate-100 font-bold" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            All ({discrepancies.length})
          </button>
          <button
            onClick={() => setSeverityFilter("critical")}
            className={`rounded px-2.5 py-1 transition ${
              severityFilter === "critical"
                ? "bg-red-500/20 text-red-300 font-bold border border-red-500/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Critical ({criticalCount})
          </button>
          <button
            onClick={() => setSeverityFilter("warning")}
            className={`rounded px-2.5 py-1 transition ${
              severityFilter === "warning"
                ? "bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Warnings ({warningCount})
          </button>
        </div>

        {/* Supplier Selector */}
        {suppliers.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="text-slate-400 font-mono text-[11px]">Filter Supplier:</span>
            <select
              value={supplierFilter}
              onChange={(e) => setSupplierFilter(e.target.value)}
              className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200 font-mono focus:border-teal-500 focus:outline-none"
            >
              <option value="all">All Suppliers</option>
              {suppliers.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Discrepancy Cards Grid */}
      <div className="mt-4 space-y-3">
        {filtered.length === 0 ? (
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-6 text-center text-xs text-slate-400">
            <CheckCircle2 className="mx-auto h-8 w-8 text-teal-400 mb-2" />
            No discrepancies match the selected criteria.
          </div>
        ) : (
          filtered.map((d) => (
            <div
              key={d.id}
              className={`rounded-lg border p-4 transition ${
                d.severity === "critical"
                  ? "border-red-500/30 bg-red-950/10 hover:border-red-500/50"
                  : d.severity === "warning"
                  ? "border-amber-500/30 bg-amber-950/10 hover:border-amber-500/50"
                  : "border-slate-800 bg-slate-950/50"
              }`}
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider ${
                      d.severity === "critical"
                        ? "bg-red-500/20 text-red-300 border border-red-500/30"
                        : d.severity === "warning"
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                        : "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                    }`}
                  >
                    {d.severity}
                  </span>
                  <span className="font-semibold text-xs text-slate-200">{d.category}</span>
                  <span className="text-xs text-slate-400">•</span>
                  <span className="font-mono text-xs text-teal-300">{d.supplier_name}</span>
                </div>

                {d.financial_impact && Number(d.financial_impact) > 0 && (
                  <span className="font-mono text-xs font-semibold text-red-400 bg-red-950/40 px-2 py-0.5 rounded border border-red-500/30">
                    +${Number(d.financial_impact).toFixed(2)} Cost Penalty
                  </span>
                )}
              </div>

              <p className="mt-2 text-xs text-slate-300 leading-relaxed">{d.explanation}</p>

              {/* Expected vs Quoted Bar */}
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] font-mono bg-slate-950/70 p-2.5 rounded border border-slate-800/80">
                <div>
                  <span className="text-slate-400">Expected (BOM):</span>{" "}
                  <span className="text-slate-200 font-medium">{d.expected_value}</span>
                </div>
                <div>
                  <span className="text-slate-400">Quoted:</span>{" "}
                  <span className={d.severity === "critical" ? "text-red-300 font-medium" : "text-amber-300 font-medium"}>
                    {d.quoted_value}
                  </span>
                </div>
              </div>

              {/* Provenance Pill */}
              {d.provenance && (
                <div className="mt-2 text-[10px] font-mono text-slate-400 flex items-center gap-1.5">
                  <span className="text-slate-400">Source:</span>
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
                    {d.provenance.filename}{" "}
                    {d.provenance.page_number
                      ? `(p. ${d.provenance.page_number})`
                      : d.provenance.row_number
                      ? `(Row ${d.provenance.row_number})`
                      : ""}
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
