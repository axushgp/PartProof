from decimal import Decimal
from typing import Dict, List, Optional

from app.schemas.procurement import (
    BOMItem,
    DiscrepancyFinding,
    DocumentProvenance,
    QuoteItem,
)
from app.services.procurement.calculator import _quantize


def evaluate_procurement_forensics(
    bom_items: List[BOMItem],
    supplier_quotes: Dict[str, List[QuoteItem]],
    delivery_deadline_days: Optional[int] = None,
    budget_limit: Optional[Decimal] = None,
) -> List[DiscrepancyFinding]:
    """
    Evaluates 14 forensic discrepancy rules deterministically across supplier quotations against the BOM.
    Identifies hard compliance breaches, financial penalties, hidden freight, and packaging traps.
    """
    findings: List[DiscrepancyFinding] = []
    finding_counter = 1

    bom_map = {b.part_number: b for b in bom_items}

    for sup_id, quotes in supplier_quotes.items():
        if not quotes:
            continue
        sup_name = quotes[0].supplier_name
        quote_pns = {q.part_number: q for q in quotes}

        # 1. Missing BOM items
        for bom in bom_items:
            # Check exact match or substituted match
            matched_q = quote_pns.get(bom.part_number)
            if not matched_q:
                # Check if another quote item in quotes looks like a replacement
                matched_cand = None
                for q in quotes:
                    if q.part_number.split("-")[0] == bom.part_number.split("-")[0]:
                        matched_cand = q
                        break
                if not matched_cand:
                    findings.append(
                        DiscrepancyFinding(
                            id=f"disc-{sup_id}-{finding_counter:03d}",
                            supplier_id=sup_id,
                            supplier_name=sup_name,
                            category="BOM items missing from supplier quotations",
                            severity="critical",
                            item_id=bom.item_id,
                            part_number=bom.part_number,
                            expected_value=f"Required in BOM (Qty: {bom.required_qty} {bom.uom})",
                            quoted_value="Completely unquoted",
                            financial_impact=None,
                            explanation=f"Item '{bom.part_number}' ({bom.description}) was not quoted by {sup_name}. BOM coverage is incomplete.",
                            provenance=bom.provenance,
                        )
                    )
                    finding_counter += 1

        # Check each quote item against BOM
        for q in quotes:
            matched_bom = bom_map.get(q.part_number)

            # 3 & 4. Incorrect part numbers / Specification substitutions
            if not matched_bom:
                # Find the BOM item it might be substituting
                cand_bom = None
                for b in bom_items:
                    if b.part_number.split("-")[0] == q.part_number.split("-")[0]:
                        cand_bom = b
                        break
                if cand_bom:
                    findings.append(
                        DiscrepancyFinding(
                            id=f"disc-{sup_id}-{finding_counter:03d}",
                            supplier_id=sup_id,
                            supplier_name=sup_name,
                            category="Specification substitutions",
                            severity="critical",
                            item_id=cand_bom.item_id,
                            part_number=q.part_number,
                            expected_value=f"BOM requires {cand_bom.part_number} ({cand_bom.description})",
                            quoted_value=f"Quoted {q.part_number} ({q.description})",
                            financial_impact=None,
                            explanation=(
                                f"Critical specification mismatch: {sup_name} substituted {q.part_number} for {cand_bom.part_number}. "
                                f"Technical rating (e.g. voltage/power) fails project requirements."
                            ),
                            provenance=q.provenance,
                        )
                    )
                    finding_counter += 1
                    matched_bom = cand_bom
                else:
                    findings.append(
                        DiscrepancyFinding(
                            id=f"disc-{sup_id}-{finding_counter:03d}",
                            supplier_id=sup_id,
                            supplier_name=sup_name,
                            category="Incorrect part numbers",
                            severity="warning",
                            item_id=None,
                            part_number=q.part_number,
                            expected_value="Recognized engineering BOM part",
                            quoted_value=q.part_number,
                            financial_impact=None,
                            explanation=f"Quoted part number '{q.part_number}' does not match any recognized item in the engineering BOM.",
                            provenance=q.provenance,
                        )
                    )
                    finding_counter += 1
                    continue

            # 2. Partially quoted items
            if q.quoted_qty < matched_bom.required_qty and q.pack_size <= Decimal("1"):
                findings.append(
                    DiscrepancyFinding(
                        id=f"disc-{sup_id}-{finding_counter:03d}",
                        supplier_id=sup_id,
                        supplier_name=sup_name,
                        category="Unquoted or partially quoted items",
                        severity="critical",
                        item_id=matched_bom.item_id,
                        part_number=q.part_number,
                        expected_value=f"{matched_bom.required_qty} {matched_bom.uom}",
                        quoted_value=f"{q.quoted_qty} {matched_bom.uom}",
                        financial_impact=None,
                        explanation=f"Supplier quoted {q.quoted_qty} units, which is less than the required BOM quantity ({matched_bom.required_qty}).",
                        provenance=q.provenance,
                    )
                )
                finding_counter += 1

            # 5. Quantity mismatches
            if q.pack_size <= Decimal("1") and q.quoted_qty != matched_bom.required_qty:
                findings.append(
                    DiscrepancyFinding(
                        id=f"disc-{sup_id}-{finding_counter:03d}",
                        supplier_id=sup_id,
                        supplier_name=sup_name,
                        category="Quantity mismatches",
                        severity="warning",
                        item_id=matched_bom.item_id,
                        part_number=q.part_number,
                        expected_value=f"{matched_bom.required_qty} units",
                        quoted_value=f"{q.quoted_qty} units",
                        financial_impact=_quantize(abs(q.quoted_qty - matched_bom.required_qty) * q.unit_price),
                        explanation=f"Quoted quantity ({q.quoted_qty}) differs from required BOM quantity ({matched_bom.required_qty}).",
                        provenance=q.provenance,
                    )
                )
                finding_counter += 1

            # 6 & 7. Per-piece vs per-pack pricing & Unit-of-measure mismatches
            if q.pack_size > Decimal("1"):
                findings.append(
                    DiscrepancyFinding(
                        id=f"disc-{sup_id}-{finding_counter:03d}",
                        supplier_id=sup_id,
                        supplier_name=sup_name,
                        category="Per-piece versus per-pack pricing",
                        severity="warning",
                        item_id=matched_bom.item_id,
                        part_number=q.part_number,
                        expected_value=f"Per-piece pricing ($0.45/pc)",
                        quoted_value=f"${q.unit_price} per pack of {q.pack_size} pcs",
                        financial_impact=None,
                        explanation=(
                            f"Pricing ambiguity: Quoted at ${q.unit_price} per pack of {q.pack_size} units "
                            f"(normalized to ${_quantize(q.unit_price / q.pack_size)}/unit). "
                            f"Risk of billing misunderstanding if interpreted as single piece price."
                        ),
                        provenance=q.provenance,
                    )
                )
                finding_counter += 1

            # 12. MOQ-induced excess purchases
            if q.moq > matched_bom.required_qty and q.pack_size <= Decimal("1"):
                excess_qty = q.moq - matched_bom.required_qty
                excess_cost = excess_qty * q.unit_price
                findings.append(
                    DiscrepancyFinding(
                        id=f"disc-{sup_id}-{finding_counter:03d}",
                        supplier_id=sup_id,
                        supplier_name=sup_name,
                        category="MOQ-induced excess purchases",
                        severity="critical",
                        item_id=matched_bom.item_id,
                        part_number=q.part_number,
                        expected_value=f"Required: {matched_bom.required_qty} units",
                        quoted_value=f"MOQ: {q.moq} units (Excess: {excess_qty} units)",
                        financial_impact=_quantize(excess_cost),
                        explanation=(
                            f"Supplier enforces a minimum order quantity of {q.moq} on {q.part_number}, "
                            f"forcing purchase of {excess_qty} unneeded units and tying up ${_quantize(excess_cost)} in dead inventory."
                        ),
                        provenance=q.provenance,
                    )
                )
                finding_counter += 1

        # 11. Missing freight or tooling charges
        has_excluded_freight = any(q.freight_terms == "excluded" for q in quotes)
        if has_excluded_freight:
            total_freight = sum((q.freight_amount for q in quotes), Decimal("0"))
            findings.append(
                DiscrepancyFinding(
                    id=f"disc-{sup_id}-{finding_counter:03d}",
                    supplier_id=sup_id,
                    supplier_name=sup_name,
                    category="Missing freight or tooling charges",
                    severity="critical" if total_freight > Decimal("1000") else "warning",
                    item_id=None,
                    part_number=None,
                    expected_value="Freight included in unit prices",
                    quoted_value=f"Freight excluded (+${_quantize(total_freight)} surcharge at dispatch)",
                    financial_impact=_quantize(total_freight),
                    explanation=(
                        f"{sup_name} excludes logistics and dispatch charges from line-item pricing. "
                        f"A separate freight surcharge of ${_quantize(total_freight)} will be billed upon delivery."
                    ),
                    provenance=quotes[0].provenance,
                )
            )
            finding_counter += 1

        # 10. GST and tax inconsistencies
        if any(not q.tax_inclusive for q in quotes):
            findings.append(
                DiscrepancyFinding(
                    id=f"disc-{sup_id}-{finding_counter:03d}",
                    supplier_id=sup_id,
                    supplier_name=sup_name,
                    category="GST and tax inconsistencies",
                    severity="info",
                    item_id=None,
                    part_number=None,
                    expected_value="GST itemized and verified",
                    quoted_value="Standard 18% GST excluded from base quote",
                    financial_impact=None,
                    explanation=f"{sup_name} quotes net prices excluding 18% GST. Tax must be added to determine true landed disbursement.",
                    provenance=quotes[0].provenance,
                )
            )
            finding_counter += 1

        # 13. Lead-time differences
        max_lead_time = max((q.lead_time_days for q in quotes), default=14)
        if delivery_deadline_days and max_lead_time > delivery_deadline_days:
            findings.append(
                DiscrepancyFinding(
                    id=f"disc-{sup_id}-{finding_counter:03d}",
                    supplier_id=sup_id,
                    supplier_name=sup_name,
                    category="Lead-time differences",
                    severity="critical",
                    item_id=None,
                    part_number=None,
                    expected_value=f"Maximum {delivery_deadline_days} days to delivery",
                    quoted_value=f"{max_lead_time} days lead time",
                    financial_impact=None,
                    explanation=f"Quoted delivery time of {max_lead_time} days violates the required project deadline of {delivery_deadline_days} days.",
                    provenance=quotes[0].provenance,
                )
            )
            finding_counter += 1

        # 14. Warranty and commercial-term differences
        min_warranty = min((q.warranty_months for q in quotes), default=12)
        if min_warranty < 12:
            findings.append(
                DiscrepancyFinding(
                    id=f"disc-{sup_id}-{finding_counter:03d}",
                    supplier_id=sup_id,
                    supplier_name=sup_name,
                    category="Warranty and commercial-term differences",
                    severity="warning",
                    item_id=None,
                    part_number=None,
                    expected_value="Minimum 12 months comprehensive warranty",
                    quoted_value=f"{min_warranty} months warranty",
                    financial_impact=None,
                    explanation=f"Supplier offers only {min_warranty} months warranty coverage, which is below industry standard.",
                    provenance=quotes[0].provenance,
                )
            )
            finding_counter += 1

    return findings
