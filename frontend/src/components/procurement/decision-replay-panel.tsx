"use client";

import React, { useState } from "react";
import { Sliders, RefreshCw, Zap, Award, RotateCcw } from "lucide-react";
import { DecisionReplayRequest, DecisionReplayResult, ProcurementAuditPayload } from "@/types/procurement";
import { replayDecision } from "@/lib/api/procurementClient";

interface DecisionReplayPanelProps {
  auditPayload: ProcurementAuditPayload;
  onReplayUpdate?: (result: DecisionReplayResult) => void;
}

export function DecisionReplayPanel({ auditPayload, onReplayUpdate }: DecisionReplayPanelProps) {
  const [discountApex, setDiscountApex] = useState<number>(0);
  const [waiveFreightApex, setWaiveFreightApex] = useState<boolean>(false);
  const [bearingMoqApex, setBearingMoqApex] = useState<number>(500);
  const [deadlineDays, setDeadlineDays] = useState<number>(auditPayload.delivery_deadline_days || 30);
  const [isCalculating, setIsCalculating] = useState<boolean>(false);
  const [replayResult, setReplayResult] = useState<DecisionReplayResult | null>(null);

  const executeReplay = async (overrides?: {
    discount?: number;
    itemDiscounts?: Record<string, number>;
    waiveFreight?: boolean;
    moqOverrides?: Record<string, number>;
    deadline?: number;
  }) => {
    setIsCalculating(true);
    const disc = overrides?.discount !== undefined ? overrides.discount : discountApex;
    const waive = overrides?.waiveFreight !== undefined ? overrides.waiveFreight : waiveFreightApex;
    const moqs = overrides?.moqOverrides !== undefined ? overrides.moqOverrides : (bearingMoqApex !== 500 ? { "BRG-6204-2RS": bearingMoqApex } : {});
    const ddl = overrides?.deadline !== undefined ? overrides.deadline : deadlineDays;
    const itemDiscs = overrides?.itemDiscounts !== undefined ? overrides.itemDiscounts : {};

    const request: DecisionReplayRequest = {
      supplier_discounts_pct: disc > 0 ? { "sup-a": disc } : {},
      item_discounts_pct: Object.keys(itemDiscs).length > 0 ? itemDiscs : undefined,
      freight_waivers: waive ? { "sup-a": true } : {},
      moq_overrides: Object.keys(moqs).length > 0 ? moqs : {},
      deadline_days_override: ddl,
    };

    try {
      const res = await replayDecision(auditPayload, request);
      setReplayResult(res);
      if (onReplayUpdate) onReplayUpdate(res);
    } catch (err) {
      console.error("Decision replay error:", err);
    } finally {
      setIsCalculating(false);
    }
  };

  const applyPreset1 = async () => {
    // Scenario 1: Remove $2,920 MOQ excess (waive bearing & bolt MOQ) & waive $1,850 freight
    setBearingMoqApex(200);
    setWaiveFreightApex(true);
    setDiscountApex(0);
    await executeReplay({
      moqOverrides: { "BRG-6204-2RS": 200, "FST-M8-ST-88": 800 },
      waiveFreight: true,
      discount: 0,
      itemDiscounts: {},
    });
  };

  const applyPreset2 = async () => {
    // Scenario 2: Controller unit price changes from $165 to $151.80 (8% discount)
    setBearingMoqApex(500);
    setWaiveFreightApex(false);
    setDiscountApex(0);
    await executeReplay({
      moqOverrides: {},
      waiveFreight: false,
      discount: 0,
      itemDiscounts: { "CTR-BLDC-72V": 8.0 },
    });
  };

  const applyPreset3 = async () => {
    // What if project delivery deadline is extended to 45 days?
    setDeadlineDays(45);
    await executeReplay({ deadline: 45 });
  };

  const resetToBaseline = async () => {
    setBearingMoqApex(500);
    setWaiveFreightApex(false);
    setDiscountApex(0);
    setDeadlineDays(auditPayload.delivery_deadline_days || 30);
    await executeReplay({
      moqOverrides: {},
      waiveFreight: false,
      discount: 0,
      itemDiscounts: {},
      deadline: auditPayload.delivery_deadline_days || 30,
    });
  };

  return (
    <div className="rounded-xl border border-teal-500/30 bg-slate-900/90 p-6 shadow-2xl backdrop-blur-md">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Sliders className="h-5 w-5 text-teal-400" />
            <h3 className="text-base font-semibold text-slate-100">Procurement Decision Replay (What-If Simulation)</h3>
            <span className="rounded-full bg-teal-500/20 px-2.5 py-0.5 text-xs font-mono font-medium text-teal-300">
              Deterministic Recalculation
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Simulate supplier negotiation concessions, waived MOQ penalties, and logistics terms live. Recalculates full landed disbursements instantly.
          </p>
        </div>

        <button
          type="button"
          onClick={resetToBaseline}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-mono text-slate-300 transition hover:bg-slate-700"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset Baseline
        </button>
      </div>

      {/* Preset Scenario Buttons */}
      <div className="mt-4">
        <label className="text-xs font-mono text-slate-400">1-Click What-If Scenarios:</label>
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={applyPreset1}
            className="inline-flex items-center gap-1.5 rounded-lg border border-teal-500/30 bg-teal-950/40 px-3 py-1.5 text-xs font-medium text-teal-300 transition hover:bg-teal-500/20 active:scale-95"
          >
            <Zap className="h-3.5 w-3.5" />
            Apex: Waive $2,920 MOQ Excess & Waive $1,850 Freight
          </button>

          <button
            type="button"
            onClick={applyPreset2}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-700 active:scale-95"
          >
            <Zap className="h-3.5 w-3.5" />
            Apex: 8% Controller Discount ($165 &rarr; $151.80)
          </button>

          <button
            type="button"
            onClick={applyPreset3}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-700 active:scale-95"
          >
            <Zap className="h-3.5 w-3.5" />
            Project: Extend Deadline to 45 Days
          </button>
        </div>
      </div>

      {/* Interactive Controls */}
      <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-4 rounded-lg border border-slate-800 bg-slate-950/70 p-4">
        {/* Discount slider */}
        <div>
          <label className="flex items-center justify-between text-xs font-mono text-slate-300">
            <span>Apex Price Discount:</span>
            <span className="font-bold text-teal-400">{discountApex}%</span>
          </label>
          <input
            type="range"
            min={0}
            max={20}
            step={1}
            value={discountApex}
            onChange={(e) => setDiscountApex(Number(e.target.value))}
            className="mt-2 w-full accent-teal-500 cursor-pointer"
          />
        </div>

        {/* Waive Freight checkbox */}
        <div className="flex flex-col justify-center">
          <label className="flex items-center gap-2 text-xs font-mono text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={waiveFreightApex}
              onChange={(e) => setWaiveFreightApex(e.target.checked)}
              className="rounded border-slate-700 bg-slate-900 text-teal-500 focus:ring-teal-500"
            />
            <span>Waive Apex Freight ($1,850)</span>
          </label>
          <span className="text-[10px] text-slate-400 font-mono mt-0.5">Supplier absorbs dispatch shipping</span>
        </div>

        {/* Bearing MOQ Override */}
        <div>
          <label className="text-xs font-mono text-slate-300">Apex Bearing MOQ:</label>
          <input
            type="number"
            min={200}
            max={1000}
            step={50}
            value={bearingMoqApex}
            onChange={(e) => setBearingMoqApex(Number(e.target.value))}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 font-mono focus:border-teal-500 focus:outline-none"
          />
          <span className="text-[10px] text-slate-400 font-mono">BOM required: 200 pcs</span>
        </div>

        {/* Deadline Days Override */}
        <div>
          <label className="text-xs font-mono text-slate-300">Delivery Deadline:</label>
          <input
            type="number"
            min={15}
            max={60}
            step={1}
            value={deadlineDays}
            onChange={(e) => setDeadlineDays(Number(e.target.value))}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 font-mono focus:border-teal-500 focus:outline-none"
          />
          <span className="text-[10px] text-slate-400 font-mono">Project target: 30 days</span>
        </div>
      </div>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          disabled={isCalculating}
          onClick={() => executeReplay()}
          className="inline-flex items-center gap-2 rounded-lg bg-teal-500 px-5 py-2 text-xs font-semibold text-slate-950 transition hover:bg-teal-400 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isCalculating ? "animate-spin" : ""}`} />
          Recalculate Decision Replay
        </button>
      </div>

      {/* Replay Outcome Display */}
      {replayResult && (
        <div className="mt-6 rounded-xl border border-teal-500/40 bg-teal-950/20 p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-teal-500/20 pb-4">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-teal-400 font-bold">
                Simulation Outcome
              </span>
              <h4 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                {replayResult.winner_changed ? (
                  <span className="flex items-center gap-1.5 text-teal-300">
                    <Award className="h-5 w-5 text-teal-400" />
                    Award Recommendation Changed!
                  </span>
                ) : (
                  <span className="text-slate-300">Original Recommendation Unchanged</span>
                )}
              </h4>
            </div>

            {/* Savings Counter */}
            {Number(replayResult.projected_savings) > 0 && (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/40 px-3.5 py-2 font-mono text-right">
                <span className="text-[10px] text-emerald-400">Net Landed Savings</span>
                <p className="text-lg font-bold text-emerald-300">
                  +${Number(replayResult.projected_savings).toFixed(2)}
                </p>
              </div>
            )}
          </div>

          <p className="mt-3 text-xs leading-relaxed text-slate-200">
            {replayResult.explanation}
          </p>

          {/* Ranking Diff Bar */}
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
            <div className="rounded bg-slate-950/60 p-3 border border-slate-800">
              <span className="text-slate-400">Baseline True Landed Ranking:</span>
              <ol className="mt-1.5 list-decimal pl-4 space-y-0.5 text-slate-300">
                {replayResult.supplier_ranking_before.map((name, i) => (
                  <li key={i} className={i === 0 ? "font-bold text-teal-300" : ""}>
                    {name}
                  </li>
                ))}
              </ol>
            </div>

            <div className="rounded bg-slate-950/60 p-3 border border-teal-500/30">
              <span className="text-teal-400 font-bold">What-If True Landed Ranking:</span>
              <ol className="mt-1.5 list-decimal pl-4 space-y-0.5 text-slate-200">
                {replayResult.supplier_ranking_after.map((name, i) => (
                  <li key={i} className={i === 0 ? "font-bold text-teal-300" : ""}>
                    {name}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
