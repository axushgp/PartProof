/**
 * Procurement Intelligence & Forensics Types
 * Strictly aligned with FastAPI schemas in backend/app/schemas/procurement.py
 */

export interface DocumentProvenance {
  filename: string;
  doc_type: "bom" | "quote";
  page_number?: number | null;
  sheet_name?: string | null;
  row_number?: number | null;
  raw_text?: string | null;
}

export interface BOMItem {
  item_id: string;
  part_number: string;
  description: string;
  category: string;
  required_qty: number;
  uom: string;
  target_unit_price?: number | null;
  currency: string;
  spec_notes?: string | null;
  provenance?: DocumentProvenance | null;
}

export interface QuoteItem {
  quote_item_id: string;
  supplier_id: string;
  supplier_name: string;
  part_number: string;
  description: string;
  quoted_qty: number;
  pack_size: number;
  moq: number;
  unit_price: number;
  currency: string;
  tax_pct: number;
  tax_inclusive: boolean;
  freight_terms: "included" | "excluded" | "at_actuals";
  freight_amount: number;
  tooling_charge?: number;
  lead_time_days: number;
  warranty_months: number;
  payment_terms: string;
  validity_days?: number;
  provenance?: DocumentProvenance | null;
}

export interface ExtractedDocument {
  filename: string;
  doc_type: "bom" | "quote";
  supplier_id?: string | null;
  supplier_name?: string | null;
  items: Record<string, unknown>[];
  warnings: string[];
  ocr_required: boolean;
  page_count: number;
  has_extractable_text: boolean;
}

export type DiscrepancySeverity = "critical" | "warning" | "info";

export interface DiscrepancyFinding {
  id: string;
  supplier_id: string;
  supplier_name: string;
  category: string;
  severity: DiscrepancySeverity;
  item_id?: string | null;
  part_number?: string | null;
  expected_value: string;
  quoted_value: string;
  financial_impact?: number | null;
  explanation: string;
  provenance?: DocumentProvenance | null;
}

export interface LineItemDetail {
  part_number: string;
  quoted_part_number?: string;
  description: string;
  status: "compliant" | "substituted" | "unquoted";
  required_qty: number;
  pack_size?: number;
  moq?: number;
  effective_purchased_qty?: number;
  excess_qty?: number;
  unit_price: number;
  headline_cost: number;
  line_cost: number;
  excess_cost: number;
  tax_amount: number;
}

export interface SupplierCostBreakdown {
  supplier_id: string;
  supplier_name: string;
  currency: string;
  headline_price: number;
  effective_purchased_qty_total: number;
  moq_excess_cost: number;
  subtotal_with_excess: number;
  freight_cost: number;
  tooling_cost: number;
  tax_amount: number;
  true_landed_cost: number;
  landed_cost_variance: number;
  lead_time_days: number;
  warranty_months: number;
  payment_terms: string;
  is_compliant: boolean;
  compliance_status?: "compliant" | "disqualified";
  commercial_status?: "recommended" | "expensive" | "disqualified";
  compliance_issues: string[];
  line_item_details: LineItemDetail[];
}

export interface SupplierComparisonResult {
  budget_limit?: number | null;
  delivery_deadline_days?: number | null;
  lowest_headline_supplier_id: string;
  lowest_landed_cost_supplier_id: string;
  best_compliant_supplier_id: string;
  recommended_supplier_id: string;
  recommendation_rationale: string;
  suppliers: SupplierCostBreakdown[];
  discrepancies: DiscrepancyFinding[];
  split_award_recommended: boolean;
  split_award_details?: {
    feasible: boolean;
    strategy: string;
    projected_cost: number;
    potential_savings: number;
    recommendation: string;
  } | null;
}

export interface DecisionReplayRequest {
  supplier_discounts_pct?: Record<string, number>;
  item_discounts_pct?: Record<string, number>;
  freight_waivers?: Record<string, boolean>;
  moq_overrides?: Record<string, number>;
  deadline_days_override?: number | null;
  budget_override?: number | null;
}

export interface DecisionReplayResult {
  scenario_description: string;
  baseline_recommended_supplier_id: string;
  new_recommended_supplier_id: string;
  winner_changed: boolean;
  baseline_landed_cost: number;
  new_landed_cost: number;
  projected_savings: number;
  explanation: string;
  supplier_ranking_before: string[];
  supplier_ranking_after: string[];
  suppliers: SupplierCostBreakdown[];
}

export interface ProcurementAuditPayload {
  title: string;
  budget_limit?: number | null;
  delivery_deadline_days?: number | null;
  bom_items: BOMItem[];
  supplier_quotes: Record<string, QuoteItem[]>;
  currency: string;
}
