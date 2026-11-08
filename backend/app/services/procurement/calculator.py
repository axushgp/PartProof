import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from app.schemas.procurement import (
    BOMItem,
    QuoteItem,
    SupplierCostBreakdown,
)

TWO_PLACES = Decimal("0.01")


def _quantize(val: Decimal) -> Decimal:
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_supplier_landed_cost(
    supplier_id: str,
    supplier_name: str,
    bom_items: List[BOMItem],
    quote_items: List[QuoteItem],
    delivery_deadline_days: Optional[int] = None,
) -> SupplierCostBreakdown:
    """
    Deterministically computes true landed cost using Python Decimal arithmetic.
    Calculates pack size conversions, MOQ-induced excess purchases, freight surcharges,
    and applicable GST/taxes.
    """
    bom_map = {b.part_number: b for b in bom_items}
    # Match by exact part number first
    quote_map: Dict[str, QuoteItem] = {}
    for q in quote_items:
        quote_map[q.part_number] = q

    headline_sum = Decimal("0.00")
    effective_purchased_total = Decimal("0.00")
    moq_excess_total = Decimal("0.00")
    subtotal_with_excess = Decimal("0.00")
    taxes_total = Decimal("0.00")
    freight_total = Decimal("0.00")
    tooling_total = Decimal("0.00")

    max_lead_time = 0
    min_warranty = 999
    payment_terms_set = set()
    compliance_issues: List[str] = []
    line_details: List[Dict] = []

    # Check for general quote-level freight
    for q in quote_items:
        if q.freight_amount > Decimal("0.0"):
            freight_total += q.freight_amount
        if q.tooling_charge > Decimal("0.0"):
            tooling_total += q.tooling_charge
        if q.lead_time_days > max_lead_time:
            max_lead_time = q.lead_time_days
        if q.warranty_months < min_warranty:
            min_warranty = q.warranty_months
        payment_terms_set.add(q.payment_terms)

    for bom in bom_items:
        # Match part number
        q_item = quote_map.get(bom.part_number)
        
        # If not exact match, search fuzzy / substitute
        if not q_item:
            for candidate in quote_items:
                # E.g. CTR-BLDC-48V quoted for CTR-BLDC-72V
                if candidate.category == bom.category if hasattr(candidate, "category") else False:
                    q_item = candidate
                    break
                elif "CTR" in bom.part_number and "CTR" in candidate.part_number:
                    q_item = candidate
                    break
                elif "BRG" in bom.part_number and "BRG" in candidate.part_number:
                    q_item = candidate
                    break
                elif "FST" in bom.part_number and "FST" in candidate.part_number:
                    q_item = candidate
                    break
                elif "BRK" in bom.part_number and "BRK" in candidate.part_number:
                    q_item = candidate
                    break
                elif "HAR" in bom.part_number and "HAR" in candidate.part_number:
                    q_item = candidate
                    break

        if not q_item:
            compliance_issues.append(f"Missing BOM item: {bom.part_number} ({bom.description}) was not quoted.")
            line_details.append({
                "part_number": bom.part_number,
                "description": bom.description,
                "status": "unquoted",
                "required_qty": float(bom.required_qty),
                "purchased_qty": 0.0,
                "unit_price": 0.0,
                "line_cost": 0.0,
                "excess_cost": 0.0,
            })
            continue

        # Check specification equivalence
        if q_item.part_number != bom.part_number:
            compliance_issues.append(
                f"Specification substitution: BOM requires {bom.part_number}, but supplier quoted {q_item.part_number}."
            )

        req_qty = bom.required_qty
        pack_size = max(q_item.pack_size, Decimal("1"))
        moq = max(q_item.moq, Decimal("1"))
        unit_price = q_item.unit_price

        if pack_size > Decimal("1"):
            # Quoted per pack/box (e.g. $18.00 per box of 50 bolts)
            packs_needed = Decimal(str(math.ceil(float(req_qty / pack_size))))
            effective_packs = max(packs_needed, moq)
            effective_qty = effective_packs * pack_size
            excess_qty = effective_qty - req_qty
            
            # Unit price is per box/pack
            line_cost = effective_packs * unit_price
            headline_line_cost = (req_qty / pack_size) * unit_price
            excess_cost = (excess_qty / pack_size) * unit_price
        else:
            # Quoted per single piece
            effective_qty = max(req_qty, moq)
            excess_qty = effective_qty - req_qty
            line_cost = effective_qty * unit_price
            headline_line_cost = req_qty * unit_price
            excess_cost = excess_qty * unit_price

        # Line tax
        tax_pct = q_item.tax_pct if not q_item.tax_inclusive else Decimal("0.00")
        line_tax = line_cost * tax_pct

        headline_sum += headline_line_cost
        effective_purchased_total += effective_qty
        moq_excess_total += excess_cost
        subtotal_with_excess += line_cost
        taxes_total += line_tax

        line_details.append({
            "part_number": bom.part_number,
            "quoted_part_number": q_item.part_number,
            "description": bom.description,
            "status": "compliant" if q_item.part_number == bom.part_number else "substituted",
            "required_qty": float(req_qty),
            "pack_size": float(pack_size),
            "moq": float(moq),
            "effective_purchased_qty": float(effective_qty),
            "excess_qty": float(excess_qty),
            "unit_price": float(unit_price),
            "headline_cost": float(_quantize(headline_line_cost)),
            "line_cost": float(_quantize(line_cost)),
            "excess_cost": float(_quantize(excess_cost)),
            "tax_amount": float(_quantize(line_tax)),
        })

    # Tax on freight and tooling if applicable (standard 18%)
    freight_tax = freight_total * Decimal("0.18")
    tooling_tax = tooling_total * Decimal("0.18")
    taxes_total += freight_tax + tooling_tax

    true_landed_cost = subtotal_with_excess + freight_total + tooling_total + taxes_total
    variance = true_landed_cost - headline_sum

    if delivery_deadline_days and max_lead_time > delivery_deadline_days:
        compliance_issues.append(
            f"Delivery lead time ({max_lead_time} days) exceeds required project deadline ({delivery_deadline_days} days)."
        )

    is_compliant = len(compliance_issues) == 0
    compliance_status = "compliant" if is_compliant else "disqualified"

    return SupplierCostBreakdown(
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        currency="USD",
        headline_price=_quantize(headline_sum),
        effective_purchased_qty_total=_quantize(effective_purchased_total),
        moq_excess_cost=_quantize(moq_excess_total),
        subtotal_with_excess=_quantize(subtotal_with_excess),
        freight_cost=_quantize(freight_total),
        tooling_cost=_quantize(tooling_total),
        tax_amount=_quantize(taxes_total),
        true_landed_cost=_quantize(true_landed_cost),
        landed_cost_variance=_quantize(variance),
        lead_time_days=max_lead_time,
        warranty_months=min_warranty if min_warranty != 999 else 12,
        payment_terms=", ".join(payment_terms_set) if payment_terms_set else "Net 30",
        is_compliant=is_compliant,
        compliance_status=compliance_status,
        commercial_status="expensive" if is_compliant else "disqualified",
        compliance_issues=compliance_issues,
        line_item_details=line_details,
    )
