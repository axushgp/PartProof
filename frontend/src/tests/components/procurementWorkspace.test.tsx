import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ProcurementUploader } from "@/components/procurement/procurement-uploader";
import { ExtractionPreview } from "@/components/procurement/extraction-preview";
import { DiscrepancyRegister } from "@/components/procurement/discrepancy-register";
import { SupplierComparisonMatrix } from "@/components/procurement/supplier-comparison-matrix";
import { VoiceBriefingCard } from "@/components/procurement/voice-briefing-card";
import {
  BOMItem,
  DiscrepancyFinding,
  QuoteItem,
  SupplierComparisonResult,
} from "@/types/procurement";

// Mock fetch for Decision Replay client calls
global.fetch = vi.fn();

const mockBomItems: BOMItem[] = [
  {
    item_id: "bom-001",
    part_number: "BRG-6204-2RS",
    description: "Deep Groove Ball Bearing 20x47x14mm",
    category: "Bearings",
    required_qty: 200,
    uom: "pcs",
    target_unit_price: 12.0,
    currency: "USD",
    provenance: {
      filename: "bom.csv",
      doc_type: "bom",
      row_number: 2,
    },
  },
];

const mockSupplierQuotes: Record<string, QuoteItem[]> = {
  "sup-a": [
    {
      quote_item_id: "qa-001",
      supplier_id: "sup-a",
      supplier_name: "Apex Industrial Components",
      part_number: "BRG-6204-2RS",
      description: "Deep Groove Ball Bearing",
      quoted_qty: 200,
      pack_size: 1,
      moq: 500,
      unit_price: 9.5,
      currency: "USD",
      tax_pct: 0.18,
      tax_inclusive: false,
      freight_terms: "excluded",
      freight_amount: 1850,
      lead_time_days: 25,
      warranty_months: 12,
      payment_terms: "Net 30",
    },
  ],
  "sup-b": [
    {
      quote_item_id: "qb-001",
      supplier_id: "sup-b",
      supplier_name: "Beacon Precision Dynamics",
      part_number: "BRG-6204-2RS",
      description: "Deep Groove Ball Bearing C3",
      quoted_qty: 200,
      pack_size: 1,
      moq: 200,
      unit_price: 11.8,
      currency: "USD",
      tax_pct: 0.18,
      tax_inclusive: false,
      freight_terms: "included",
      freight_amount: 0,
      lead_time_days: 21,
      warranty_months: 24,
      payment_terms: "Net 30",
    },
  ],
};

const mockDiscrepancies: DiscrepancyFinding[] = [
  {
    id: "disc-001",
    supplier_id: "sup-a",
    supplier_name: "Apex Industrial Components",
    category: "MOQ-induced excess purchases",
    severity: "critical",
    item_id: "bom-001",
    part_number: "BRG-6204-2RS",
    expected_value: "200 units",
    quoted_value: "500 units MOQ",
    financial_impact: 2850.0,
    explanation: "Forces purchase of 300 excess units.",
  },
];

const mockComparison: SupplierComparisonResult = {
  lowest_headline_supplier_id: "sup-a",
  lowest_landed_cost_supplier_id: "sup-b",
  best_compliant_supplier_id: "sup-b",
  recommended_supplier_id: "sup-b",
  recommendation_rationale: "Beacon Precision Dynamics is recommended due to lower true landed cost.",
  split_award_recommended: false,
  suppliers: [
    {
      supplier_id: "sup-a",
      supplier_name: "Apex Industrial Components",
      currency: "USD",
      headline_price: 25680.0,
      effective_purchased_qty_total: 700,
      moq_excess_cost: 2920.0,
      subtotal_with_excess: 28600.0,
      freight_cost: 1850.0,
      tooling_cost: 0,
      tax_amount: 5481.0,
      true_landed_cost: 35931.0,
      landed_cost_variance: 10251.0,
      lead_time_days: 25,
      warranty_months: 12,
      payment_terms: "Net 30",
      is_compliant: false,
      compliance_issues: ["MOQ penalty", "Excluded freight"],
      line_item_details: [],
    },
    {
      supplier_id: "sup-b",
      supplier_name: "Beacon Precision Dynamics",
      currency: "USD",
      headline_price: 27948.0,
      effective_purchased_qty_total: 200,
      moq_excess_cost: 0,
      subtotal_with_excess: 27948.0,
      freight_cost: 0,
      tooling_cost: 0,
      tax_amount: 5030.64,
      true_landed_cost: 32978.64,
      landed_cost_variance: 5030.64,
      lead_time_days: 21,
      warranty_months: 24,
      payment_terms: "Net 30",
      is_compliant: true,
      compliance_issues: [],
      line_item_details: [],
    },
  ],
  discrepancies: mockDiscrepancies,
};

describe("Procurement Workspace Components", () => {
  it("renders ProcurementUploader with synthetic demo launcher", () => {
    const onLoadDemo = vi.fn();
    const onAnalyze = vi.fn();

    render(
      <ProcurementUploader
        onLoadDemo={onLoadDemo}
        onAnalyzeFiles={onAnalyze}
        isLoading={false}
      />
    );

    expect(screen.getByText("Live Demonstration Case")).toBeDefined();
    const demoBtn = screen.getByText("Load Synthetic Demo Case");
    fireEvent.click(demoBtn);
    expect(onLoadDemo).toHaveBeenCalled();
  });

  it("renders ExtractionPreview with line items and source provenance", () => {
    render(
      <ExtractionPreview
        bomItems={mockBomItems}
        supplierQuotes={mockSupplierQuotes}
      />
    );

    expect(screen.getByText("BRG-6204-2RS")).toBeDefined();
    expect(screen.getByText("bom.csv : Row 2")).toBeDefined();
  });

  it("renders DiscrepancyRegister with severity pills and financial exposure", () => {
    render(<DiscrepancyRegister discrepancies={mockDiscrepancies} />);

    expect(screen.getByText("Procurement Forensics & Discrepancy Register")).toBeDefined();
    expect(screen.getByText("+$2850.00 Hidden Exposure Flagged")).toBeDefined();
    expect(screen.getByText("MOQ-induced excess purchases")).toBeDefined();
  });

  it("renders SupplierComparisonMatrix with official winner and true landed costs", () => {
    render(<SupplierComparisonMatrix comparison={mockComparison} />);

    expect(screen.getByText("Official Award Recommendation")).toBeDefined();
    expect(screen.getAllByText("Beacon Precision Dynamics").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$32978.64").length).toBeGreaterThan(0);
    expect(screen.getByText("$35931.00")).toBeDefined();
  });

  it("renders VoiceBriefingCard with controls and Underdog Woof standby attribution", () => {
    render(
      <VoiceBriefingCard
        narrationText="Beacon Precision Dynamics is the recommended winner."
        recommendedSupplierName="Beacon Precision Dynamics"
      />
    );

    expect(screen.getByText("Browser-native voice briefing")).toBeDefined();
    expect(screen.getByText("Listen to Briefing")).toBeDefined();
    expect(screen.getByText("Underdog Woof: Standby")).toBeDefined();

    // Toggle transcript
    const transcriptToggle = screen.getByText("View Transcript");
    fireEvent.click(transcriptToggle);
    expect(screen.getByText("Hide Transcript")).toBeDefined();
    expect(screen.getByText("Beacon Precision Dynamics is the recommended winner.")).toBeDefined();
  });
});
