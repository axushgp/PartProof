"use client";

import React, { useState } from "react";
import { Scale, AlertCircle } from "lucide-react";
import Link from "next/link";
import {
  BOMItem,
  DocumentProvenance,
  ExtractedDocument,
  ProcurementAuditPayload,
  QuoteItem,
  SupplierComparisonResult,
} from "@/types/procurement";
import {
  extractDocuments,
  fetchProcurementDemo,
  reconcileProcurement,
} from "@/lib/api/procurementClient";
import { ProcurementUploader } from "@/components/procurement/procurement-uploader";
import { ExtractionPreview } from "@/components/procurement/extraction-preview";
import { DiscrepancyRegister } from "@/components/procurement/discrepancy-register";
import { SupplierComparisonMatrix } from "@/components/procurement/supplier-comparison-matrix";
import { DecisionReplayPanel } from "@/components/procurement/decision-replay-panel";
import { VoiceBriefingCard } from "@/components/procurement/voice-briefing-card";
import { ProcurementExecutionPanel } from "@/components/procurement/procurement-execution-panel";

export default function ProcurementPage() {
  const [auditPayload, setAuditPayload] = useState<ProcurementAuditPayload | null>(null);
  const [comparisonResult, setComparisonResult] = useState<SupplierComparisonResult | null>(null);
  const [extractedDocs, setExtractedDocs] = useState<ExtractedDocument[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Load Synthetic Demo Case
  const handleLoadDemo = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    setAuditPayload(null);
    setComparisonResult(null);
    setExtractedDocs([]);
    try {
      const demo = await fetchProcurementDemo();
      setAuditPayload(demo);

      const comparison = await reconcileProcurement(demo);
      setComparisonResult(comparison);
    } catch (err: unknown) {
      console.error("Failed to load demonstration case:", err);
      setErrorMsg(err instanceof Error ? err.message : "Failed to load demonstration case.");
    } finally {
      setIsLoading(false);
    }
  };

  // Analyze Custom Files
  const handleAnalyzeFiles = async (
    bomFile: File | null,
    quoteFiles: File[],
    supplierNames: string[]
  ) => {
    setIsLoading(true);
    setErrorMsg(null);
    setAuditPayload(null);
    setComparisonResult(null);
    setExtractedDocs([]);
    try {
      const docs = await extractDocuments(bomFile, quoteFiles, supplierNames);
      setExtractedDocs(docs);

      // Convert extracted docs into ProcurementAuditPayload
      const bomDoc = docs.find((d) => d.doc_type === "bom");
      const quoteDocs = docs.filter((d) => d.doc_type === "quote");

      const bomItems: BOMItem[] = (bomDoc?.items || []).map((it, idx) => ({
        item_id: `bom-${idx + 1}`,
        part_number: String(it.part_number || `PART-${idx + 1}`),
        description: String(it.description || ""),
        category: String(it.category || "General"),
        required_qty: Number(it.qty) || 1,
        uom: String(it.uom || "pcs"),
        target_unit_price: it.unit_price ? Number(it.unit_price) : null,
        currency: "USD",
        provenance: it.provenance as DocumentProvenance | undefined,
      }));

      const supplierQuotes: Record<string, QuoteItem[]> = {};
      for (const qDoc of quoteDocs) {
        const sId = qDoc.supplier_id || `sup-${Object.keys(supplierQuotes).length + 1}`;
        const sName = qDoc.supplier_name || `Supplier ${sId}`;

        supplierQuotes[sId] = (qDoc.items || []).map((it, idx) => ({
          quote_item_id: `q-${sId}-${idx + 1}`,
          supplier_id: sId,
          supplier_name: sName,
          part_number: String(it.part_number || `QPART-${idx + 1}`),
          description: String(it.description || ""),
          quoted_qty: Number(it.qty) || 1,
          pack_size: Number(it.pack_size) || 1,
          moq: Number(it.moq) || 1,
          unit_price: Number(it.unit_price) || 0,
          currency: "USD",
          tax_pct: Number(it.tax_pct) || 0.18,
          tax_inclusive: Boolean(it.tax_inclusive),
          freight_terms: (it.freight_terms as "included" | "excluded" | "at_actuals") || "included",
          freight_amount: Number(it.freight) || 0,
          lead_time_days: Number(it.lead_time_days) || 14,
          warranty_months: Number(it.warranty_months) || 12,
          payment_terms: String(it.payment_terms || "Net 30"),
          provenance: it.provenance as DocumentProvenance | undefined,
        }));
      }

      const totalQuoteItems = Object.values(supplierQuotes).reduce((sum, q) => sum + q.length, 0);
      if (bomItems.length === 0 && totalQuoteItems === 0) {
        setErrorMsg("No valid procurement line items could be extracted. Please check file formatting or upload standard CSV/XLSX spreadsheets.");
        return;
      }

      const payload: ProcurementAuditPayload = {
        title: bomFile ? bomFile.name.replace(/\.[^/.]+$/, "") : "Custom Engineering Procurement Audit",
        budget_limit: 42000,
        delivery_deadline_days: 30,
        bom_items: bomItems,
        supplier_quotes: supplierQuotes,
        currency: "USD",
      };

      setAuditPayload(payload);
      const comparison = await reconcileProcurement(payload);
      setComparisonResult(comparison);
    } catch (err: unknown) {
      console.error("Custom file analysis error:", err);
      setErrorMsg(err instanceof Error ? err.message : "Failed to analyze uploaded procurement documents.");
    } finally {
      setIsLoading(false);
    }
  };

  const hasOcrWarning = extractedDocs.some((d) => d.ocr_required);
  const docWarnings = extractedDocs.flatMap((d) => d.warnings);

  return (
    <div className="space-y-8 pb-16">
      {/* Top Breadcrumb & Title */}
      <div>
        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <Link href="/app" className="hover:text-slate-200">
            Console
          </Link>
          <span>/</span>
          <span className="text-teal-400">Procurement Forensics</span>
        </div>

        <div className="mt-3 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100 sm:text-3xl flex items-center gap-3">
              <Scale className="h-8 w-8 text-teal-400" />
              Procurement Intelligence & Forensics
            </h1>
            <p className="mt-1 text-sm text-slate-400 max-w-3xl">
              Rules-based procurement analysis of engineering BOMs and supplier quotations. Detects hidden procurement costs, pack-size traps, unquoted freight, and evaluates consistent landed-cost calculations under isolated MicroVM governance.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-teal-500/30 bg-teal-950/40 px-3 py-1 text-xs font-mono text-teal-300">
              Repeatable audit rules
            </span>
            <span className="rounded-full border border-emerald-500/30 bg-emerald-950/40 px-3 py-1 text-xs font-mono text-emerald-300">
              MicroSandbox Isolated
            </span>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="flex items-center gap-3 rounded-lg border border-red-500/30 bg-red-950/30 p-4 text-xs text-red-300">
          <AlertCircle className="h-5 w-5 shrink-0 text-red-400" />
          <p>{errorMsg}</p>
        </div>
      )}

      {/* 1. Uploader & Synthetic Demo Launcher */}
      <section>
        <ProcurementUploader
          onLoadDemo={handleLoadDemo}
          onAnalyzeFiles={handleAnalyzeFiles}
          isLoading={isLoading}
        />
      </section>

      {/* When data is present, show the full forensic investigation suite */}
      {auditPayload && comparisonResult && (
        <>
          {/* 2. Extraction & Normalization Preview */}
          <section>
            <ExtractionPreview
              bomItems={auditPayload.bom_items}
              supplierQuotes={auditPayload.supplier_quotes}
              warnings={docWarnings}
              ocrRequired={hasOcrWarning}
            />
          </section>

          {/* 3. Side-by-Side Supplier Intelligence & Award Recommendation */}
          <section>
            <SupplierComparisonMatrix comparison={comparisonResult} />
          </section>

          {/* 4. Forensic Discrepancy Findings Register */}
          <section>
            <DiscrepancyRegister discrepancies={comparisonResult.discrepancies} />
          </section>

          {/* 5. What-If Decision Replay Showpiece */}
          <section>
            <DecisionReplayPanel auditPayload={auditPayload} />
          </section>

          {/* 6. Local Voice Briefing */}
          <section>
            <VoiceBriefingCard
              narrationText={comparisonResult.recommendation_rationale}
              recommendedSupplierName={
                comparisonResult.suppliers.find(
                  (s) => s.supplier_id === comparisonResult.recommended_supplier_id
                )?.supplier_name || "Recommended Supplier"
              }
            />
          </section>

          {/* 7. Isolated Execution & Cryptographic Proof */}
          <section>
            <ProcurementExecutionPanel auditPayload={auditPayload} />
          </section>
        </>
      )}
    </div>
  );
}
