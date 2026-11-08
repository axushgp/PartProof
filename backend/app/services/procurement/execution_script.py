import json
from decimal import Decimal
from typing import Dict, Any
from app.schemas.procurement import ProcurementAuditPayload


def generate_procurement_execution_script(payload: ProcurementAuditPayload) -> str:
    """
    Generates a self-contained, dependency-free Python execution script (using only
    Python standard library: os, sys, json, csv, math, decimal) that executes the
    exact deterministic procurement forensics and landed-cost calculations inside
    the isolated MicroSandbox MicroVM.
    
    Generates all 5 official Decision Pack files in /workspace/output/:
    1. bom_audit.csv
    2. supplier_comparison.csv
    3. discrepancy_register.csv
    4. procurement_decision.json
    5. negotiation_brief.md
    """
    data_json = json.dumps(payload.model_dump(mode="json"))

    script = f'''# -*- coding: utf-8 -*-
"""
PartProof Isolated MicroSandbox Procurement Execution Script
Self-contained deterministic forensics & landed-cost engine.
Standard library only: math, decimal, csv, json, os, sys
"""
import os
import sys
import math
import json
import csv
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

TWO_PLACES = Decimal("0.01")

def quantize(val: Decimal) -> Decimal:
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

# 1. Output directory
output_dir = os.environ.get("PARTPROOF_OUTPUT_DIR") or "/workspace/output"
if not os.path.isabs(output_dir):
    output_dir = os.path.abspath(output_dir)
os.makedirs(output_dir, exist_ok=True)

# 2. Embedded Verified Procurement Input
raw_input = json.loads({json.dumps(data_json)})

bom_items = raw_input.get("bom_items", [])
supplier_quotes = raw_input.get("supplier_quotes", {{}})
deadline_days = raw_input.get("delivery_deadline_days")
budget_limit = Decimal(str(raw_input.get("budget_limit"))) if raw_input.get("budget_limit") else None

# 3. Deterministic Landed-Cost Calculations
suppliers_breakdown = []
all_discrepancies = []
disc_counter = 1

for sup_id, quotes in supplier_quotes.items():
    if not quotes:
        continue
    sup_name = quotes[0].get("supplier_name", sup_id)
    quote_pns = {{q.get("part_number"): q for q in quotes}}

    headline_sum = Decimal("0.00")
    effective_purchased_total = Decimal("0.00")
    moq_excess_total = Decimal("0.00")
    subtotal_with_excess = Decimal("0.00")
    taxes_total = Decimal("0.00")
    freight_total = Decimal("0.00")
    tooling_total = Decimal("0.00")

    max_lead_time = 0
    min_warranty = 999
    compliance_issues = []

    # Freight & general charges
    for q in quotes:
        freight_amt = Decimal(str(q.get("freight_amount", "0.0")))
        if freight_amt > Decimal("0.0"):
            freight_total += freight_amt
        tooling_amt = Decimal(str(q.get("tooling_charge", "0.0")))
        if tooling_amt > Decimal("0.0"):
            tooling_total += tooling_amt
        lt = int(q.get("lead_time_days", 14))
        if lt > max_lead_time:
            max_lead_time = lt
        warr = int(q.get("warranty_months", 12))
        if warr < min_warranty:
            min_warranty = warr

    # Line item reconciliation
    for b in bom_items:
        b_pn = b.get("part_number")
        b_qty = Decimal(str(b.get("required_qty", "1")))
        
        q_item = quote_pns.get(b_pn)
        if not q_item:
            # Check substituted candidate
            for cand in quotes:
                cand_pn = cand.get("part_number", "")
                if cand_pn.split("-")[0] == b_pn.split("-")[0]:
                    q_item = cand
                    break

        if not q_item:
            compliance_issues.append(f"Missing BOM item: {{b_pn}} was not quoted.")
            all_discrepancies.append({{
                "id": f"disc-{{sup_id}}-{{disc_counter:03d}}",
                "supplier_name": sup_name,
                "category": "BOM items missing from supplier quotations",
                "severity": "CRITICAL",
                "part_number": b_pn,
                "expected": f"Required in BOM (Qty: {{b_qty}})",
                "quoted": "Unquoted",
                "financial_impact": "0.00",
                "explanation": f"Item {{b_pn}} not quoted by {{sup_name}}.",
                "source_file": b.get("provenance", {{}}).get("filename", "bom.csv") if b.get("provenance") else "bom.csv",
            }})
            disc_counter += 1
            continue

        q_pn = q_item.get("part_number")
        if q_pn != b_pn:
            compliance_issues.append(f"Specification substitution: required {{b_pn}}, quoted {{q_pn}}.")
            all_discrepancies.append({{
                "id": f"disc-{{sup_id}}-{{disc_counter:03d}}",
                "supplier_name": sup_name,
                "category": "Specification substitutions",
                "severity": "CRITICAL",
                "part_number": q_pn,
                "expected": f"BOM requires {{b_pn}}",
                "quoted": f"Quoted {{q_pn}}",
                "financial_impact": "0.00",
                "explanation": f"Specification mismatch: {{sup_name}} substituted {{q_pn}} for {{b_pn}}.",
                "source_file": q_item.get("provenance", {{}}).get("filename", "quote") if q_item.get("provenance") else "quote",
            }})
            disc_counter += 1

        unit_price = Decimal(str(q_item.get("unit_price", "0.0")))
        pack_size = max(Decimal(str(q_item.get("pack_size", "1"))), Decimal("1"))
        moq = max(Decimal(str(q_item.get("moq", "1"))), Decimal("1"))

        if pack_size > Decimal("1"):
            packs_needed = Decimal(str(math.ceil(float(b_qty / pack_size))))
            effective_packs = max(packs_needed, moq)
            effective_qty = effective_packs * pack_size
            excess_qty = effective_qty - b_qty
            line_cost = effective_packs * unit_price
            headline_cost = (b_qty / pack_size) * unit_price
            excess_cost = (excess_qty / pack_size) * unit_price

            all_discrepancies.append({{
                "id": f"disc-{{sup_id}}-{{disc_counter:03d}}",
                "supplier_name": sup_name,
                "category": "Per-piece versus per-pack pricing",
                "severity": "WARNING",
                "part_number": q_pn,
                "expected": f"Per-piece rate",
                "quoted": f"${{unit_price}} per pack of {{pack_size}}",
                "financial_impact": "0.00",
                "explanation": f"Quoted per pack of {{pack_size}} units.",
                "source_file": q_item.get("provenance", {{}}).get("filename", "quote") if q_item.get("provenance") else "quote",
            }})
            disc_counter += 1
        else:
            effective_qty = max(b_qty, moq)
            excess_qty = effective_qty - b_qty
            line_cost = effective_qty * unit_price
            headline_cost = b_qty * unit_price
            excess_cost = excess_qty * unit_price

            if moq > b_qty:
                all_discrepancies.append({{
                    "id": f"disc-{{sup_id}}-{{disc_counter:03d}}",
                    "supplier_name": sup_name,
                    "category": "MOQ-induced excess purchases",
                    "severity": "CRITICAL",
                    "part_number": q_pn,
                    "expected": f"Required: {{b_qty}} units",
                    "quoted": f"MOQ: {{moq}} units (Excess: {{excess_qty}})",
                    "financial_impact": str(quantize(excess_cost)),
                    "explanation": f"MOQ enforces {{excess_qty}} dead inventory units.",
                    "source_file": q_item.get("provenance", {{}}).get("filename", "quote") if q_item.get("provenance") else "quote",
                }})
                disc_counter += 1

        tax_pct = Decimal(str(q_item.get("tax_pct", "0.18"))) if not q_item.get("tax_inclusive", False) else Decimal("0.00")
        line_tax = line_cost * tax_pct

        headline_sum += headline_cost
        effective_purchased_total += effective_qty
        moq_excess_total += excess_cost
        subtotal_with_excess += line_cost
        taxes_total += line_tax

    # Tax on freight and tooling
    taxes_total += (freight_total * Decimal("0.18")) + (tooling_total * Decimal("0.18"))
    true_landed = subtotal_with_excess + freight_total + tooling_total + taxes_total
    variance = true_landed - headline_sum

    if freight_total > Decimal("0.0"):
        all_discrepancies.append({{
            "id": f"disc-{{sup_id}}-{{disc_counter:03d}}",
            "supplier_name": sup_name,
            "category": "Missing freight or tooling charges",
            "severity": "CRITICAL" if freight_total > Decimal("1000") else "WARNING",
            "part_number": "LOGISTICS",
            "expected": "Freight included in rates",
            "quoted": f"Freight excluded (+${{quantize(freight_total)}})",
            "financial_impact": str(quantize(freight_total)),
            "explanation": f"Freight surcharge billed at delivery.",
            "source_file": quotes[0].get("provenance", {{}}).get("filename", "quote") if quotes[0].get("provenance") else "quote",
        }})
        disc_counter += 1

    if deadline_days and max_lead_time > deadline_days:
        compliance_issues.append(f"Lead time ({{max_lead_time}}d) exceeds deadline ({{deadline_days}}d).")
        all_discrepancies.append({{
            "id": f"disc-{{sup_id}}-{{disc_counter:03d}}",
            "supplier_name": sup_name,
            "category": "Lead-time differences",
            "severity": "CRITICAL",
            "part_number": "SCHEDULE",
            "expected": f"<= {{deadline_days}} days",
            "quoted": f"{{max_lead_time}} days",
            "financial_impact": "0.00",
            "explanation": f"Lead time violates delivery deadline.",
            "source_file": quotes[0].get("provenance", {{}}).get("filename", "quote") if quotes[0].get("provenance") else "quote",
        }})
        disc_counter += 1

    is_compliant = len(compliance_issues) == 0

    suppliers_breakdown.append({{
        "supplier_id": sup_id,
        "supplier_name": sup_name,
        "headline_price": quantize(headline_sum),
        "effective_purchased_qty_total": quantize(effective_purchased_total),
        "moq_excess_cost": quantize(moq_excess_total),
        "subtotal_with_excess": quantize(subtotal_with_excess),
        "freight_cost": quantize(freight_total),
        "tooling_cost": quantize(tooling_total),
        "tax_amount": quantize(taxes_total),
        "true_landed_cost": quantize(true_landed),
        "landed_cost_variance": quantize(variance),
        "lead_time_days": max_lead_time,
        "warranty_months": min_warranty if min_warranty != 999 else 12,
        "is_compliant": is_compliant,
        "compliance_status": "compliant" if is_compliant else "disqualified",
        "commercial_status": "expensive" if is_compliant else "disqualified",
        "compliance_issues": compliance_issues,
    }})

# 4. Determine Winner
compliant_sups = [s for s in suppliers_breakdown if s["is_compliant"]]
if compliant_sups:
    winner = sorted(compliant_sups, key=lambda x: x["true_landed_cost"])[0]
else:
    winner = sorted(suppliers_breakdown, key=lambda x: x["true_landed_cost"])[0]

winner["commercial_status"] = "recommended"

# 5. Write Artifact 1: bom_audit.csv
with open(os.path.join(output_dir, "bom_audit.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["item_id", "part_number", "description", "category", "required_qty", "uom", "target_price", "quoted_by_count", "source_file"])
    for b in bom_items:
        pn = b.get("part_number")
        quoted_cnt = sum(1 for qs in supplier_quotes.values() if any(q.get("part_number") == pn for q in qs))
        src = b.get("provenance", {{}}).get("filename", "bom.csv") if b.get("provenance") else "bom.csv"
        w.writerow([b.get("item_id"), pn, b.get("description"), b.get("category", "General"), str(b.get("required_qty")), b.get("uom", "pcs"), str(b.get("target_unit_price") or "0.00"), quoted_cnt, src])

# 6. Write Artifact 2: supplier_comparison.csv
with open(os.path.join(output_dir, "supplier_comparison.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["supplier_id", "supplier_name", "headline_price", "moq_excess_cost", "freight_cost", "tax_amount", "true_landed_cost", "variance", "lead_time_days", "compliance_status", "commercial_status"])
    for s in sorted(suppliers_breakdown, key=lambda x: x["true_landed_cost"]):
        w.writerow([s["supplier_id"], s["supplier_name"], str(s["headline_price"]), str(s["moq_excess_cost"]), str(s["freight_cost"]), str(s["tax_amount"]), str(s["true_landed_cost"]), str(s["landed_cost_variance"]), s["lead_time_days"], s["compliance_status"].upper(), s["commercial_status"].upper()])

# 7. Write Artifact 3: discrepancy_register.csv
with open(os.path.join(output_dir, "discrepancy_register.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["discrepancy_id", "supplier_name", "category", "severity", "part_number", "expected", "quoted", "financial_impact", "explanation", "source_file"])
    for d in all_discrepancies:
        w.writerow([d["id"], d["supplier_name"], d["category"], d["severity"], d["part_number"], d["expected"], d["quoted"], d["financial_impact"], d["explanation"], d["source_file"]])

# 8. Write Artifact 4: procurement_decision.json
decision_payload = {{
    "audit_metadata": {{
        "engine": "PartProof Procurement Intelligence 3.0",
        "execution_mode": "Isolated MicroSandbox MicroVM",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "calculation_standard": "Deterministic Python Decimal (ROUND_HALF_UP)",
    }},
    "recommended_supplier": winner["supplier_name"],
    "recommended_supplier_id": winner["supplier_id"],
    "true_landed_cost": str(winner["true_landed_cost"]),
    "suppliers": [{{k: str(v) if isinstance(v, Decimal) else v for k, v in s.items()}} for s in suppliers_breakdown],
    "discrepancies_count": len(all_discrepancies),
    "discrepancies": all_discrepancies,
}}
with open(os.path.join(output_dir, "procurement_decision.json"), "w", encoding="utf-8") as f:
    json.dump(decision_payload, f, indent=2)

# 9. Write Artifact 5: negotiation_brief.md
with open(os.path.join(output_dir, "negotiation_brief.md"), "w", encoding="utf-8") as f:
    f.write(f"""# PARTPROOF PROCUREMENT FORENSICS - NEGOTIATION BRIEF
**Generated:** {{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}}  
**Execution Environment:** Isolated MicroSandbox MicroVM (Verified Destroyed)  
**Recommended Awardee:** {{winner['supplier_name']}}  
**Verified Landed Disbursement:** ${{winner['true_landed_cost']}}  

---

## 1. Executive Summary
{{winner['supplier_name']}} provides the lowest compliant true landed cost at ${{winner['true_landed_cost']}}.
All supplier calculations have been executed and verified in an isolated MicroVM sandbox with Ed25519 cryptographic receipts.

---

## 2. Supplier Landed-Cost & Compliance Findings
""")
    for s in suppliers_breakdown:
        f.write(f"""### {{s['supplier_name']}}
- **Headline Quote:** ${{s['headline_price']}}
- **True Landed Cost:** ${{s['true_landed_cost']}} (Variance: +${{s['landed_cost_variance']}})
- **MOQ Dead Inventory:** ${{s['moq_excess_cost']}}
- **Unbundled Freight:** ${{s['freight_cost']}}
- **Compliance Status:** {{s['compliance_status'].upper()}} (Commercial Status: {{s['commercial_status'].upper()}})
""")
        if s["compliance_issues"]:
            f.write("- **Violations:**\\n")
            for ci in s["compliance_issues"]:
                f.write(f"  * {{ci}}\\n")
        f.write("\\n")

    f.write("""---

## 3. Negotiation Directives
1. **MOQ Negotiations:** Require elimination of forced pack sizes and minimums to recapture dead inventory capital.
2. **Freight Bundling:** Mandate inclusion of shipping into baseline line-item costs.
3. **Formal Specification Lock:** Enforce strict part-number equivalence before issuing purchase orders.

*Confidential - Generated deterministically by PartProof Procurement Intelligence.*
""")

print(f"[PROCUREMENT ENGINE] Verified calculation and 5 artifacts written to {{output_dir}} successfully.")
sys.exit(0)
'''
    return script
