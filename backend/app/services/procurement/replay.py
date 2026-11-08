import copy
from decimal import Decimal
from typing import Dict, List, Optional

from app.schemas.procurement import (
    BOMItem,
    DecisionReplayRequest,
    DecisionReplayResult,
    QuoteItem,
    SupplierComparisonResult,
)
from app.services.procurement.calculator import _quantize
from app.services.procurement.intelligence import evaluate_supplier_intelligence


def replay_procurement_decision(
    bom_items: List[BOMItem],
    supplier_quotes: Dict[str, List[QuoteItem]],
    delivery_deadline_days: Optional[int] = None,
    budget_limit: Optional[Decimal] = None,
    request: Optional[DecisionReplayRequest] = None,
) -> DecisionReplayResult:
    """
    Simulates what-if scenarios deterministically. Recalculates all landed costs,
    tax liabilities, MOQ excess, and compliance statuses under hypothetical negotiation terms.
    """
    req = request or DecisionReplayRequest()

    # 1. Baseline Run
    baseline_result = evaluate_supplier_intelligence(
        bom_items=bom_items,
        supplier_quotes=supplier_quotes,
        delivery_deadline_days=delivery_deadline_days,
        budget_limit=budget_limit,
    )

    baseline_winner_id = baseline_result.recommended_supplier_id
    baseline_winner_obj = next((s for s in baseline_result.suppliers if s.supplier_id == baseline_winner_id), baseline_result.suppliers[0])
    baseline_landed_cost = baseline_winner_obj.true_landed_cost

    # 2. Apply What-if modifications to a deepcopy of the quotes
    modified_quotes: Dict[str, List[QuoteItem]] = copy.deepcopy(supplier_quotes)

    effective_deadline = req.deadline_days_override if req.deadline_days_override is not None else delivery_deadline_days
    effective_budget = Decimal(str(req.budget_override)) if req.budget_override is not None else budget_limit

    scenario_notes: List[str] = []

    for sup_id, quotes in modified_quotes.items():
        # Supplier-wide discount check
        discount_pct = req.supplier_discounts_pct.get(sup_id, 0.0)
        if discount_pct > 0.0:
            scenario_notes.append(f"{quotes[0].supplier_name} price discounted by {discount_pct}%.")
            factor = Decimal(str(round(1.0 - (discount_pct / 100.0), 4)))
            for q in quotes:
                q.unit_price = _quantize(q.unit_price * factor)

        # Item-specific discount check
        for q in quotes:
            item_disc = None
            if req.item_discounts_pct:
                item_disc = req.item_discounts_pct.get(f"{sup_id}:{q.part_number}")
                if item_disc is None:
                    item_disc = req.item_discounts_pct.get(q.part_number)
            if item_disc is not None:
                scenario_notes.append(f"{q.part_number} for {quotes[0].supplier_name} discounted by {item_disc}%.")
                factor = Decimal(str(round(1.0 - (float(item_disc) / 100.0), 4)))
                q.unit_price = _quantize(q.unit_price * factor)

        # Freight waiver check
        if req.freight_waivers.get(sup_id, False):
            scenario_notes.append(f"{quotes[0].supplier_name} freight waived (included).")
            for q in quotes:
                q.freight_terms = "included"
                q.freight_amount = Decimal("0.00")

        # MOQ override check
        for q in quotes:
            if f"{sup_id}:{q.part_number}" in req.moq_overrides:
                new_moq = Decimal(str(req.moq_overrides[f"{sup_id}:{q.part_number}"]))
                scenario_notes.append(f"MOQ on {q.part_number} for {q.supplier_name} changed to {new_moq}.")
                q.moq = new_moq
            elif q.part_number in req.moq_overrides:
                new_moq = Decimal(str(req.moq_overrides[q.part_number]))
                scenario_notes.append(f"MOQ on {q.part_number} for {q.supplier_name} changed to {new_moq}.")
                q.moq = new_moq

    if req.deadline_days_override is not None and req.deadline_days_override != delivery_deadline_days:
        scenario_notes.append(f"Delivery deadline adjusted to {req.deadline_days_override} days.")

    # 3. Recalculate side-by-side comparison with modified inputs
    new_result = evaluate_supplier_intelligence(
        bom_items=bom_items,
        supplier_quotes=modified_quotes,
        delivery_deadline_days=effective_deadline,
        budget_limit=effective_budget,
    )

    new_winner_id = new_result.recommended_supplier_id
    new_winner_obj = next((s for s in new_result.suppliers if s.supplier_id == new_winner_id), new_result.suppliers[0])
    new_landed_cost = new_winner_obj.true_landed_cost

    winner_changed = new_winner_id != baseline_winner_id
    savings = _quantize(baseline_landed_cost - new_landed_cost)

    ranking_before = [s.supplier_name for s in sorted(baseline_result.suppliers, key=lambda x: x.true_landed_cost)]
    ranking_after = [s.supplier_name for s in sorted(new_result.suppliers, key=lambda x: x.true_landed_cost)]

    # 4. Generate Causal Explanation
    scenario_desc = " | ".join(scenario_notes) if scenario_notes else "Default baseline assumptions"

    driver_explanations: List[str] = []
    if winner_changed:
        driver_explanations.append(
            f"RECOMMENDATION SHIFT: {new_winner_obj.supplier_name} replaces {baseline_winner_obj.supplier_name} as the recommended supplier."
        )
        if savings > Decimal("0.00"):
            driver_explanations.append(
                f"This shift delivers a net landed procurement savings of ${savings} (${baseline_landed_cost} -> ${new_landed_cost})."
            )
        for sup in new_result.suppliers:
            if sup.supplier_id == new_winner_id:
                driver_explanations.append(
                    f"Driver: {sup.supplier_name}'s landed cost dropped to ${sup.true_landed_cost} due to reduced MOQ excess / waived freight / price adjustments."
                )
    else:
        driver_explanations.append(
            f"AWARD UNCHANGED: {new_winner_obj.supplier_name} remains the recommended awardee."
        )
        # Check if any supplier's cost was reduced
        for sup in new_result.suppliers:
            orig = next((b for b in baseline_result.suppliers if b.supplier_id == sup.supplier_id), None)
            if orig and sup.true_landed_cost < orig.true_landed_cost:
                reduction = orig.true_landed_cost - sup.true_landed_cost
                driver_explanations.append(
                    f"{sup.supplier_name}'s revised landed cost is ${sup.true_landed_cost} "
                    f"(a ${reduction} reduction from ${orig.true_landed_cost}). However, this reduction "
                    f"fails to overcome {new_winner_obj.supplier_name}'s ${new_winner_obj.true_landed_cost} landed cost."
                )
        if savings > Decimal("0.00"):
            driver_explanations.append(f"Negotiation concession yields ${savings} in additional landed savings.")
        elif not any(sup.true_landed_cost < orig.true_landed_cost for sup in new_result.suppliers for orig in baseline_result.suppliers if orig.supplier_id == sup.supplier_id):
            driver_explanations.append("Adjusted parameters did not alter supplier landed disbursements.")

    explanation = " ".join(driver_explanations)

    return DecisionReplayResult(
        scenario_description=scenario_desc,
        baseline_recommended_supplier_id=baseline_winner_id,
        new_recommended_supplier_id=new_winner_id,
        winner_changed=winner_changed,
        baseline_landed_cost=baseline_landed_cost,
        new_landed_cost=new_landed_cost,
        projected_savings=savings,
        explanation=explanation,
        supplier_ranking_before=ranking_before,
        supplier_ranking_after=ranking_after,
        suppliers=new_result.suppliers,
    )
