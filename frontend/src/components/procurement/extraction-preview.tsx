"use client";

import React, { useState } from "react";
import { AlertCircle } from "lucide-react";
import { BOMItem, QuoteItem } from "@/types/procurement";

interface ExtractionPreviewProps {
  bomItems: BOMItem[];
  supplierQuotes: Record<string, QuoteItem[]>;
  warnings?: string[];
  ocrRequired?: boolean;
}

export function ExtractionPreview({
  bomItems,
  supplierQuotes,
  warnings = [],
  ocrRequired = false,
}: ExtractionPreviewProps) {
  const [activeTab, setActiveTab] = useState<string>("bom");

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl backdrop-blur-md">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-slate-800 pb-4">
        <div>
          <h3 className="text-base font-semibold text-slate-100">Document Extraction & Line-Item Normalization</h3>
          <p className="mt-0.5 text-xs text-slate-400">
            Verified line-level extraction with provenance tracking to original source files and page/row coordinates.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex rounded-lg border border-slate-700 bg-slate-950 p-1 text-xs font-mono">
          <button
            onClick={() => setActiveTab("bom")}
            className={`rounded px-3 py-1 transition ${
              activeTab === "bom" ? "bg-teal-500 font-bold text-slate-950" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            BOM Items ({bomItems.length})
          </button>
          {Object.entries(supplierQuotes).map(([supId, quotes]) => (
            <button
              key={supId}
              onClick={() => setActiveTab(supId)}
              className={`rounded px-3 py-1 transition ${
                activeTab === supId ? "bg-teal-500 font-bold text-slate-950" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {quotes[0]?.supplier_name || supId} ({quotes.length})
            </button>
          ))}
        </div>
      </div>

      {/* OCR Warning Alert */}
      {ocrRequired && (
        <div className="mt-4 flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-950/30 p-3 text-xs text-amber-300">
          <AlertCircle className="h-5 w-5 shrink-0 text-amber-400 mt-0.5" />
          <div>
            <p className="font-semibold">OCR Required Warning:</p>
            <p className="mt-0.5 text-amber-200/90">
              One or more uploaded documents appear to be image-based or scanned PDFs without extractable text. Please upload digital text PDFs, CSV, or XLSX spreadsheets for deterministic audit validation.
            </p>
          </div>
        </div>
      )}

      {/* Warnings List */}
      {warnings.length > 0 && !ocrRequired && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-400">
          <p className="font-semibold text-slate-300">Extraction Notices:</p>
          <ul className="mt-1 list-disc pl-4 space-y-0.5">
            {warnings.map((w, idx) => (
              <li key={idx}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Items Table */}
      <div className="mt-4 overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-800 bg-slate-950/90 font-mono text-slate-400">
            <tr>
              <th className="px-3 py-2.5">Part Number</th>
              <th className="px-3 py-2.5">Description</th>
              <th className="px-3 py-2.5 text-right">{activeTab === "bom" ? "Required Qty" : "Quoted Qty"}</th>
              <th className="px-3 py-2.5">UOM / Pack</th>
              <th className="px-3 py-2.5 text-right">Unit Price</th>
              {activeTab !== "bom" && <th className="px-3 py-2.5 text-right">MOQ</th>}
              {activeTab !== "bom" && <th className="px-3 py-2.5 text-right">Lead Time</th>}
              <th className="px-3 py-2.5">Provenance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-900/40">
            {activeTab === "bom" ? (
              bomItems.map((item) => (
                <tr key={item.item_id} className="hover:bg-slate-800/40 transition">
                  <td className="px-3 py-2 font-mono font-semibold text-teal-300">{item.part_number}</td>
                  <td className="px-3 py-2 text-slate-200">{item.description}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{item.required_qty}</td>
                  <td className="px-3 py-2 font-mono text-slate-400">{item.uom}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">
                    {item.target_unit_price ? `$${Number(item.target_unit_price).toFixed(2)}` : "-"}
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-400">
                    <span className="rounded bg-slate-800 px-1.5 py-0.5">
                      {item.provenance?.filename || "manual"} : {item.provenance?.row_number ? `Row ${item.provenance.row_number}` : "p.1"}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              (supplierQuotes[activeTab] || []).map((item) => (
                <tr key={item.quote_item_id} className="hover:bg-slate-800/40 transition">
                  <td className="px-3 py-2 font-mono font-semibold text-slate-200">{item.part_number}</td>
                  <td className="px-3 py-2 text-slate-300">{item.description}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{item.quoted_qty}</td>
                  <td className="px-3 py-2 font-mono text-slate-400">
                    {item.pack_size > 1 ? `Box of ${item.pack_size}` : "Piece"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-semibold text-slate-200">
                    ${Number(item.unit_price).toFixed(2)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{item.moq}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{item.lead_time_days}d</td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-400">
                    <span className="rounded bg-slate-800 px-1.5 py-0.5">
                      {item.provenance?.filename || "doc"} :{" "}
                      {item.provenance?.page_number
                        ? `p.${item.provenance.page_number}`
                        : item.provenance?.row_number
                        ? `Row ${item.provenance.row_number}`
                        : "ref"}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
