"use client";

import React from "react";
import { Award, XCircle, Clock, Shield } from "lucide-react";
import { SupplierComparisonResult } from "@/types/procurement";

interface SupplierComparisonMatrixProps {
  comparison: SupplierComparisonResult;
}

export function SupplierComparisonMatrix({ comparison }: SupplierComparisonMatrixProps) {
  const recommendedSupplier = comparison.suppliers.find(
    (s) => s.supplier_id === comparison.recommended_supplier_id
  );

  return (
    <div className="space-y-6">
      {/* Recommended Award Banner */}
      {recommendedSupplier && (
        <div className="rounded-xl border border-teal-500/40 bg-gradient-to-r from-teal-950/40 via-slate-900 to-slate-900 p-6 shadow-2xl backdrop-blur-md">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500 text-slate-950 font-bold">
                  <Award className="h-5 w-5" />
                </div>
                <div>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-teal-400 font-bold">
                    Official Award Recommendation
                  </span>
                  <h3 className="text-xl font-bold text-slate-100">{recommendedSupplier.supplier_name}</h3>
                </div>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-slate-300 max-w-3xl">
                {comparison.recommendation_rationale}
              </p>
            </div>

            {/* Metric highlight */}
            <div className="flex flex-col rounded-lg border border-teal-500/30 bg-teal-950/40 p-4 font-mono text-right shrink-0">
              <span className="text-[11px] text-teal-400">True Landed Cost</span>
              <span className="text-2xl font-bold text-slate-100">
                ${Number(recommendedSupplier.true_landed_cost).toFixed(2)}
              </span>
              <span className="text-[11px] text-teal-300/80">
                {recommendedSupplier.is_compliant ? "100% Specification Compliant" : "Conditional"}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Side-by-Side Comparison Cards */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {comparison.suppliers.map((supplier) => {
          const isWinner = supplier.supplier_id === comparison.recommended_supplier_id;
          const isLowestHeadline = supplier.supplier_id === comparison.lowest_headline_supplier_id;

          return (
            <div
              key={supplier.supplier_id}
              className={`flex flex-col justify-between rounded-xl border p-5 shadow-xl transition backdrop-blur-md ${
                isWinner
                  ? "border-teal-500/60 bg-slate-900/95 ring-1 ring-teal-500/30"
                  : "border-slate-800 bg-slate-900/80"
              }`}
            >
              <div>
                {/* Header Pills */}
                <div className="flex flex-wrap items-center justify-between gap-1.5">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider ${
                        supplier.is_compliant
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-red-500/20 text-red-300 border border-red-500/30"
                      }`}
                    >
                      {supplier.is_compliant ? "Compliant" : "Disqualified"}
                    </span>
                    {supplier.is_compliant && !isWinner && (
                      <span className="rounded-full px-2 py-0.5 text-[10px] font-mono font-semibold text-amber-300 bg-amber-500/15 border border-amber-500/30">
                        Commercially Expensive
                      </span>
                    )}
                  </div>

                  {isWinner && (
                    <span className="flex items-center gap-1 text-[10px] font-mono font-bold text-teal-300 bg-teal-500/10 px-2 py-0.5 rounded border border-teal-500/30">
                      <Award className="h-3 w-3" /> Winner
                    </span>
                  )}
                  {isLowestHeadline && !isWinner && (
                    <span className="text-[10px] font-mono text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/30">
                      Lowest Headline
                    </span>
                  )}
                </div>

                <h4 className="mt-3 text-base font-bold text-slate-100">{supplier.supplier_name}</h4>

                {/* Landed Cost Breakdown */}
                <div className="mt-4 space-y-2 rounded-lg border border-slate-800 bg-slate-950/80 p-3 font-mono text-xs">
                  <div className="flex items-center justify-between text-slate-400">
                    <span>Headline Quote:</span>
                    <span className="text-slate-200">${Number(supplier.headline_price).toFixed(2)}</span>
                  </div>

                  {Number(supplier.moq_excess_cost) > 0 && (
                    <div className="flex items-center justify-between text-red-400">
                      <span>+ MOQ Dead Inventory:</span>
                      <span>+${Number(supplier.moq_excess_cost).toFixed(2)}</span>
                    </div>
                  )}

                  {Number(supplier.freight_cost) > 0 && (
                    <div className="flex items-center justify-between text-amber-400">
                      <span>+ Unbundled Freight:</span>
                      <span>+${Number(supplier.freight_cost).toFixed(2)}</span>
                    </div>
                  )}

                  <div className="flex items-center justify-between text-slate-400">
                    <span>+ Taxes (GST):</span>
                    <span>+${Number(supplier.tax_amount).toFixed(2)}</span>
                  </div>

                  <div className="border-t border-slate-800 pt-2 flex items-center justify-between font-bold">
                    <span className="text-slate-300">True Landed Cost:</span>
                    <span className={isWinner ? "text-teal-300 text-sm" : "text-slate-100 text-sm"}>
                      ${Number(supplier.true_landed_cost).toFixed(2)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>Variance vs Headline:</span>
                    <span className="text-amber-400/90 font-medium">
                      +${Number(supplier.landed_cost_variance).toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Operations & Terms */}
                <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] font-mono text-slate-400">
                  <div className="rounded bg-slate-950/40 p-2 border border-slate-800/60">
                    <span className="flex items-center gap-1 text-slate-400">
                      <Clock className="h-3 w-3" /> Lead Time
                    </span>
                    <span className="mt-0.5 block font-semibold text-slate-200">{supplier.lead_time_days} days</span>
                  </div>
                  <div className="rounded bg-slate-950/40 p-2 border border-slate-800/60">
                    <span className="flex items-center gap-1 text-slate-400">
                      <Shield className="h-3 w-3" /> Warranty
                    </span>
                    <span className="mt-0.5 block font-semibold text-slate-200">{supplier.warranty_months} months</span>
                  </div>
                </div>

                {/* Compliance Violations List */}
                {!supplier.is_compliant && supplier.compliance_issues.length > 0 && (
                  <div className="mt-3 rounded-lg border border-red-500/20 bg-red-950/20 p-2.5 text-xs text-red-300">
                    <p className="font-semibold flex items-center gap-1 text-[11px]">
                      <XCircle className="h-3.5 w-3.5 text-red-400" /> Disqualification Drivers:
                    </p>
                    <ul className="mt-1 list-disc pl-4 text-[11px] text-red-200/80 space-y-0.5">
                      {supplier.compliance_issues.map((issue, idx) => (
                        <li key={idx}>{issue}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
