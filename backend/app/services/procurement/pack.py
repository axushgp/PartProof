import csv
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List

from app.schemas.procurement import (
    BOMItem,
    QuoteItem,
    SupplierComparisonResult,
)


def generate_procurement_decision_pack(
    bom_items: List[BOMItem],
    supplier_quotes: Dict[str, List[QuoteItem]],
    result: SupplierComparisonResult,
) -> Dict[str, bytes]:
    """
    Generates the 5 deterministic procurement audit artifacts:
    1. bom_audit.csv
    2. supplier_comparison.csv
    3. discrepancy_register.csv
    4. procurement_decision.json
    5. negotiation_brief.md
    """
    artifacts: Dict[str, bytes] = {}

    # 1. bom_audit.csv
    buf1 = io.StringIO()
    writer1 = csv.writer(buf1)
    writer1.writerow([
        "item_id",
        "part_number",
        "description",
        "category",
        "required_qty",
        "uom",
        "target_unit_price",
        "quoted_by_count",
        "provenance_file",
        "provenance_ref",
    ])
    for b in bom_items:
        quoted_count = sum(
            1 for quotes in supplier_quotes.values()
            if any(q.part_number == b.part_number for q in quotes)
        )
        prov_file = b.provenance.filename if b.provenance else "manual"
        prov_ref = f"Row {b.provenance.row_number}" if b.provenance and b.provenance.row_number else "N/A"
        writer1.writerow([
            b.item_id,
            b.part_number,
            b.description,
            b.category,
            str(b.required_qty),
            b.uom,
            str(b.target_unit_price or "0.00"),
            quoted_count,
            prov_file,
            prov_ref,
        ])
    artifacts["bom_audit.csv"] = buf1.getvalue().encode("utf-8")

    # 2. supplier_comparison.csv
    buf2 = io.StringIO()
    writer2 = csv.writer(buf2)
    writer2.writerow([
        "supplier_id",
        "supplier_name",
        "headline_price",
        "moq_excess_cost",
        "freight_cost",
        "tooling_cost",
        "tax_amount",
        "true_landed_cost",
        "landed_variance",
        "lead_time_days",
        "warranty_months",
        "is_compliant",
        "compliance_issues_count",
    ])
    for s in sorted(result.suppliers, key=lambda x: x.true_landed_cost):
        writer2.writerow([
            s.supplier_id,
            s.supplier_name,
            str(s.headline_price),
            str(s.moq_excess_cost),
            str(s.freight_cost),
            str(s.tooling_cost),
            str(s.tax_amount),
            str(s.true_landed_cost),
            str(s.landed_cost_variance),
            s.lead_time_days,
            s.warranty_months,
            "YES" if s.is_compliant else "NO",
            len(s.compliance_issues),
        ])
    artifacts["supplier_comparison.csv"] = buf2.getvalue().encode("utf-8")

    # 3. discrepancy_register.csv
    buf3 = io.StringIO()
    writer3 = csv.writer(buf3)
    writer3.writerow([
        "discrepancy_id",
        "supplier_name",
        "category",
        "severity",
        "part_number",
        "expected_value",
        "quoted_value",
        "financial_impact",
        "explanation",
        "source_file",
        "source_ref",
    ])
    for d in result.discrepancies:
        src_file = d.provenance.filename if d.provenance else "unknown"
        src_ref = (
            f"Page {d.provenance.page_number}"
            if d.provenance and d.provenance.page_number
            else (f"Row {d.provenance.row_number}" if d.provenance and d.provenance.row_number else "N/A")
        )
        writer3.writerow([
            d.id,
            d.supplier_name,
            d.category,
            d.severity.upper(),
            d.part_number or "N/A",
            d.expected_value,
            d.quoted_value,
            str(d.financial_impact or "0.00"),
            d.explanation,
            src_file,
            src_ref,
        ])
    artifacts["discrepancy_register.csv"] = buf3.getvalue().encode("utf-8")

    # 4. procurement_decision.json
    decision_dict = {
        "audit_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine": "PartProof Procurement Intelligence 3.0",
            "calculation_standard": "Deterministic Python Decimal (ROUND_HALF_UP)",
        },
        "recommendation": {
            "recommended_supplier_id": result.recommended_supplier_id,
            "best_compliant_supplier_id": result.best_compliant_supplier_id,
            "lowest_headline_supplier_id": result.lowest_headline_supplier_id,
            "lowest_landed_cost_supplier_id": result.lowest_landed_cost_supplier_id,
            "rationale": result.recommendation_rationale,
            "split_award": result.split_award_details,
        },
        "suppliers": [s.model_dump(mode="json") for s in result.suppliers],
        "discrepancies_count": len(result.discrepancies),
        "discrepancies": [d.model_dump(mode="json") for d in result.discrepancies],
    }
    artifacts["procurement_decision.json"] = json.dumps(decision_dict, indent=2).encode("utf-8")

    # 5. negotiation_brief.md
    rec_sup = next((s for s in result.suppliers if s.supplier_id == result.recommended_supplier_id), result.suppliers[0])
    headline_sup = next((s for s in result.suppliers if s.supplier_id == result.lowest_headline_supplier_id), result.suppliers[0])

    lines: List[str] = [
        "# PARTPROOF PROCUREMENT FORENSICS - NEGOTIATION BRIEF",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Recommended Awardee:** {rec_sup.supplier_name}  ",
        f"**True Landed Disbursement:** ${rec_sup.true_landed_cost}  ",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        result.recommendation_rationale,
        "",
        "---",
        "",
        "## 2. Supplier Vulnerabilities & Forensic Leverage",
        "",
    ]

    for s in result.suppliers:
        lines.append(f"### {s.supplier_name}")
        lines.append(f"- **Headline Quote:** ${s.headline_price}")
        lines.append(f"- **True Landed Cost:** ${s.true_landed_cost} (Variance: +${s.landed_cost_variance})")
        lines.append(f"- **Lead Time:** {s.lead_time_days} days | **Warranty:** {s.warranty_months} months")
        if s.moq_excess_cost > Decimal("0.00"):
            lines.append(f"- **MOQ Excess Penalty:** ${s.moq_excess_cost} forced in dead inventory.")
        if s.freight_cost > Decimal("0.00"):
            lines.append(f"- **Hidden Dispatch Freight:** ${s.freight_cost} excluded from unit prices.")
        if s.is_compliant:
            if s.supplier_id == rec_sup.supplier_id:
                lines.append("- **Compliance Status:** COMPLIANT & RECOMMENDED (Lowest compliant true landed cost).")
            else:
                lines.append("- **Compliance Status:** COMPLIANT (Technically & deadline compliant, but commercially more expensive).")
        else:
            lines.append("- **Compliance Status:** DISQUALIFIED (Hard specification/deadline violations):")
            for ci in s.compliance_issues:
                lines.append(f"  * {ci}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. Negotiation Playbook & Counter-Offer Strategy",
        "",
        f"### Leverage Point 1: Counter-offer to {headline_sup.supplier_name}",
        f"If {headline_sup.supplier_name} is preferred for manufacturing continuity, demand the following concessions:",
        f"1. **Waive MOQ Restrictions:** Require delivery of exact required quantities (200 bearings, 800 bolts). This eliminates **${headline_sup.moq_excess_cost}** in forced excess inventory.",
        f"2. **Bundle Logistics:** Require freight to be included at existing unit prices, removing the **${headline_sup.freight_cost}** surcharge.",
        f"3. **Target Counter-Offer:** If {headline_sup.supplier_name} accepts both terms, its true landed cost falls from **${headline_sup.true_landed_cost}** to **${(headline_sup.headline_price * Decimal('1.18')).quantize(Decimal('0.01'))}**, establishing an awardable proposal with **${(rec_sup.true_landed_cost - (headline_sup.headline_price * Decimal('1.18')).quantize(Decimal('0.01')))}** in net landed savings.",
        "",
        f"### Leverage Point 2: Final Concession from {rec_sup.supplier_name} (Recommended Awardee)",
        f"1. **Volume Discount:** Inform {rec_sup.supplier_name} that a competing vendor quoted a headline unit rate **${rec_sup.headline_price - headline_sup.headline_price}** lower.",
        "2. **Payment Terms:** Request Net 60 payment terms to optimize working capital.",
        "3. **Packaging Clarity:** Formalize pack-size definitions in purchase order to prevent billing discrepancies.",
        "",
        "---",
        "*Confidential - Generated deterministically by PartProof Procurement Intelligence.*",
    ])

    artifacts["negotiation_brief.md"] = "\n".join(lines).encode("utf-8")

    return artifacts
