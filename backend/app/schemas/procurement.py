from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class DocumentProvenance(BaseModel):
    """Tracks origin of an extracted item to source file, page, sheet, or row."""
    filename: str
    doc_type: Literal["bom", "quote"]
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    raw_text: Optional[str] = None


class BOMItem(BaseModel):
    """Engineering Bill of Materials line item."""
    item_id: str
    part_number: str
    description: str
    category: str = "general"
    required_qty: Decimal
    uom: str = "pcs"
    target_unit_price: Optional[Decimal] = None
    currency: str = "USD"
    spec_notes: Optional[str] = None
    provenance: Optional[DocumentProvenance] = None


class QuoteItem(BaseModel):
    """Supplier quotation line item."""
    quote_item_id: str
    supplier_id: str
    supplier_name: str
    part_number: str
    description: str
    quoted_qty: Decimal
    pack_size: Decimal = Field(default=Decimal("1"))
    moq: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal
    currency: str = "USD"
    tax_pct: Decimal = Field(default=Decimal("0.18"))
    tax_inclusive: bool = False
    freight_terms: Literal["included", "excluded", "at_actuals"] = "included"
    freight_amount: Decimal = Field(default=Decimal("0.0"))
    tooling_charge: Decimal = Field(default=Decimal("0.0"))
    lead_time_days: int = 14
    warranty_months: int = 12
    payment_terms: str = "Net 30"
    validity_days: int = 30
    provenance: Optional[DocumentProvenance] = None


class ExtractedDocument(BaseModel):
    """Result of parsing an uploaded document (BOM or Quote)."""
    filename: str
    doc_type: Literal["bom", "quote"]
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    ocr_required: bool = False
    page_count: int = 1
    has_extractable_text: bool = True


class DiscrepancyFinding(BaseModel):
    """Detected discrepancy across quotes vs BOM."""
    id: str
    supplier_id: str
    supplier_name: str
    category: str
    severity: Literal["critical", "warning", "info"]
    item_id: Optional[str] = None
    part_number: Optional[str] = None
    expected_value: str
    quoted_value: str
    financial_impact: Optional[Decimal] = None
    explanation: str
    provenance: Optional[DocumentProvenance] = None


class SupplierCostBreakdown(BaseModel):
    """Deterministic landed-cost calculations for a supplier."""
    supplier_id: str
    supplier_name: str
    currency: str = "USD"
    headline_price: Decimal
    effective_purchased_qty_total: Decimal
    moq_excess_cost: Decimal
    subtotal_with_excess: Decimal
    freight_cost: Decimal
    tooling_cost: Decimal
    tax_amount: Decimal
    true_landed_cost: Decimal
    landed_cost_variance: Decimal
    lead_time_days: int
    warranty_months: int
    payment_terms: str
    is_compliant: bool
    compliance_status: Literal["compliant", "disqualified"] = "compliant"
    commercial_status: Literal["recommended", "expensive", "disqualified"] = "expensive"
    compliance_issues: List[str] = Field(default_factory=list)
    line_item_details: List[Dict[str, Any]] = Field(default_factory=list)


class SupplierComparisonResult(BaseModel):
    """Side-by-side analysis and award recommendation."""
    budget_limit: Optional[Decimal] = None
    delivery_deadline_days: Optional[int] = None
    lowest_headline_supplier_id: str
    lowest_landed_cost_supplier_id: str
    best_compliant_supplier_id: str
    recommended_supplier_id: str
    recommendation_rationale: str
    suppliers: List[SupplierCostBreakdown]
    discrepancies: List[DiscrepancyFinding]
    split_award_recommended: bool = False
    split_award_details: Optional[Dict[str, Any]] = None


class DecisionReplayRequest(BaseModel):
    """Parameters for what-if recalculation."""
    supplier_discounts_pct: Dict[str, float] = Field(default_factory=dict)
    item_discounts_pct: Dict[str, float] = Field(default_factory=dict)
    freight_waivers: Dict[str, bool] = Field(default_factory=dict)
    moq_overrides: Dict[str, float] = Field(default_factory=dict)
    deadline_days_override: Optional[int] = None
    budget_override: Optional[float] = None


class DecisionReplayResult(BaseModel):
    """Outcome of a what-if scenario recalculation."""
    scenario_description: str
    baseline_recommended_supplier_id: str
    new_recommended_supplier_id: str
    winner_changed: bool
    baseline_landed_cost: Decimal
    new_landed_cost: Decimal
    projected_savings: Decimal
    explanation: str
    supplier_ranking_before: List[str]
    supplier_ranking_after: List[str]
    suppliers: List[SupplierCostBreakdown]


class ProcurementAuditPayload(BaseModel):
    """Complete payload for procurement analysis or execution."""
    title: str = "Procurement Audit"
    budget_limit: Optional[Decimal] = None
    delivery_deadline_days: Optional[int] = None
    bom_items: List[BOMItem]
    supplier_quotes: Dict[str, List[QuoteItem]]
    currency: str = "USD"
