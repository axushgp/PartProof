import io
import pytest
from decimal import Decimal
import openpyxl

from app.schemas.procurement import BOMItem, QuoteItem, ProcurementAuditPayload
from app.services.procurement.calculator import calculate_supplier_landed_cost
from app.services.procurement.forensics import evaluate_procurement_forensics
from app.services.procurement.intelligence import evaluate_supplier_intelligence
from app.services.procurement.parsers.csv_parser import parse_csv_document
from app.services.procurement.parsers.normalizer import parse_and_normalize_file, normalize_to_bom_items, normalize_to_quote_items
from app.services.procurement.parsers.xlsx_parser import parse_xlsx_document
from app.services.procurement.parsers.pdf_parser import parse_pdf_document
from app.services.procurement.replay import replay_procurement_decision
from app.schemas.procurement import DecisionReplayRequest


def test_custom_non_ev_csv_parser_and_reconciliation():
    """
    Priority 4 Test: Validates that non-EV industrial pump BOM and supplier quotes
    are correctly parsed from CSV and reconciled using the exact uploaded supplier names and parts.
    """
    bom_csv = (
        "part_number,description,category,qty,uom,target_price\n"
        "PMP-HSG-316,Centrifugal Pump Casing SS316,Castings,50,pcs,450.00\n"
        "IMP-SFT-420,Martensitic Shaft SS420,Machined,50,pcs,120.00\n"
        "SEAL-SIC-50,Silicon Carbide Mechanical Seal,Seals,100,pcs,35.00\n"
    ).encode("utf-8")

    quote_a_csv = (
        "part_number,description,qty,unit_price,pack_size,moq,lead_time_days,freight\n"
        "PMP-HSG-316,Pump Casing Casting,50,440.00,1,50,21,1200.00\n"
        "IMP-SFT-420,Turned Shaft,50,115.00,1,50,14,0.00\n"
        "SEAL-SIC-50,SiC Cartridge Seal,100,32.00,1,150,10,0.00\n"
    ).encode("utf-8")

    quote_b_csv = (
        "part_number,description,qty,unit_price,pack_size,moq,lead_time_days,freight\n"
        "PMP-HSG-316,Pump Casing SS316,50,460.00,1,50,25,0.00\n"
        "IMP-SFT-420,Shaft SS420,50,118.00,1,50,18,0.00\n"
        "SEAL-SIC-50,Mechanical Seal SiC,100,34.00,10,100,14,0.00\n"
    ).encode("utf-8")

    quote_c_csv = (
        "part_number,description,qty,unit_price,pack_size,moq,lead_time_days,freight\n"
        "PMP-HSG-316,Centrifugal Pump Casing,50,450.00,1,50,20,500.00\n"
        "IMP-SFT-420,Machined Shaft 420,50,110.00,1,50,12,0.00\n"
        "SEAL-SIC-50,Cartridge Seal SiC-50,100,35.00,1,100,15,0.00\n"
    ).encode("utf-8")

    # 1. Parse BOM
    extracted_bom = parse_and_normalize_file(bom_csv, "industrial_pump_bom.csv", doc_type="bom")
    assert extracted_bom.doc_type == "bom"
    assert len(extracted_bom.items) == 3
    bom_items = normalize_to_bom_items(extracted_bom)
    assert bom_items[0].part_number == "PMP-HSG-316"
    assert bom_items[0].required_qty == Decimal("50")

    # 2. Parse Supplier Quotations (3 distinct suppliers)
    extracted_qa = parse_and_normalize_file(
        quote_a_csv,
        "apex_hydraulics_quote.csv",
        doc_type="quote",
        supplier_id="sup-hydraulics",
        supplier_name="Apex Flow Hydraulics",
    )
    extracted_qb = parse_and_normalize_file(
        quote_b_csv,
        "vortex_fluids_quote.csv",
        doc_type="quote",
        supplier_id="sup-vortex",
        supplier_name="Vortex Fluid Dynamics",
    )
    extracted_qc = parse_and_normalize_file(
        quote_c_csv,
        "hydrotech_quote.csv",
        doc_type="quote",
        supplier_id="sup-hydrotech",
        supplier_name="HydroTech Components",
    )

    quotes_a = normalize_to_quote_items(extracted_qa, "sup-hydraulics", "Apex Flow Hydraulics")
    quotes_b = normalize_to_quote_items(extracted_qb, "sup-vortex", "Vortex Fluid Dynamics")
    quotes_c = normalize_to_quote_items(extracted_qc, "sup-hydrotech", "HydroTech Components")

    assert len(quotes_a) == 3
    assert len(quotes_b) == 3
    assert len(quotes_c) == 3
    assert quotes_a[0].supplier_name == "Apex Flow Hydraulics"
    assert quotes_b[0].supplier_name == "Vortex Fluid Dynamics"
    assert quotes_c[0].supplier_name == "HydroTech Components"

    # 3. Reconcile side-by-side with 3 suppliers
    comparison = evaluate_supplier_intelligence(
        bom_items=bom_items,
        supplier_quotes={
            "sup-hydraulics": quotes_a,
            "sup-vortex": quotes_b,
            "sup-hydrotech": quotes_c,
        },
        delivery_deadline_days=30,
        budget_limit=Decimal("50000.00"),
    )

    # Check results strictly reflect the non-EV data across all 3 suppliers
    supplier_names = [s.supplier_name for s in comparison.suppliers]
    assert len(comparison.suppliers) == 3
    assert "Apex Flow Hydraulics" in supplier_names
    assert "Vortex Fluid Dynamics" in supplier_names
    assert "HydroTech Components" in supplier_names
    assert "Beacon Precision Dynamics" not in supplier_names  # Ensure demo data not leaked!

    # Apex Flow has 50 units MOQ excess on SEAL-SIC-50 (150 MOQ vs 100 required) and 1200 freight
    apex_sup = next(s for s in comparison.suppliers if s.supplier_id == "sup-hydraulics")
    assert apex_sup.moq_excess_cost == Decimal("1600.00")  # 50 excess * $32 = $1600
    assert apex_sup.freight_cost == Decimal("1200.00")

    # HydroTech has 0 MOQ excess, 500 freight, and competitive pricing
    hydro_sup = next(s for s in comparison.suppliers if s.supplier_id == "sup-hydrotech")
    assert hydro_sup.moq_excess_cost == Decimal("0.00")
    assert hydro_sup.freight_cost == Decimal("500.00")


def test_custom_non_ev_xlsx_parser():
    """
    Priority 4 Test: Tests XLSX spreadsheet parser with non-EV robotic actuator BOM.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Actuator_BOM"

    ws.append(["Part Number", "Description", "Required Qty", "Unit Price", "Category"])
    ws.append(["ROB-ACT-48V", "Robotic Harmonic Drive Actuator", 10, 850.00, "Motion"])
    ws.append(["ENC-ABS-20B", "20-bit Absolute Optical Encoder", 10, 195.00, "Sensors"])

    stream = io.BytesIO()
    wb.save(stream)
    xlsx_bytes = stream.getvalue()

    extracted = parse_xlsx_document(xlsx_bytes, "robotic_arm_bom.xlsx", doc_type="bom")
    assert extracted.has_extractable_text is True
    assert len(extracted.items) == 2
    assert extracted.items[0]["part_number"] == "ROB-ACT-48V"
    assert extracted.items[0]["qty"] == Decimal("10")
    assert extracted.items[1]["part_number"] == "ENC-ABS-20B"


def test_scanned_pdf_emits_ocr_warning_without_inventing_data():
    """
    Priority 4 Test: Digital PDF with no text must emit OCR warning and not invent values.
    """
    # Create empty PDF
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    pdf_bytes = stream.getvalue()

    extracted = parse_pdf_document(pdf_bytes, "scanned_invoice.pdf", doc_type="quote")
    assert extracted.ocr_required is True
    assert any("OCR" in w or "scanned" in w.lower() for w in extracted.warnings)
    assert len(extracted.items) == 0  # Does NOT invent rows!


def test_procurement_decision_replay_verified_scenarios():
    """
    Priority 5 Regression Test: Proves exact mathematical correctness for:
    Baseline:
      Apex Landed: $35,931.00
      Beacon Landed: $32,978.64 (Winner)
    Scenario 1:
      Waive $2,920 MOQ excess and waive $1,850 freight
      Apex Revised Landed: $30,302.40 (Savings: $2,676.24 vs Beacon)
      Apex becomes lowest-cost compliant option!
    Scenario 2:
      8% discount on $165 Controller price (CTR-BLDC-72V) for 100 units
      Revised controller rate: $151.80, pre-tax savings $1,320, GST reduction $237.60
      Apex Revised Landed: $34,373.40
      Beacon remains recommended winner!
    """
    from app.services.procurement.demo_data import get_synthetic_demo_payload

    demo = get_synthetic_demo_payload()

    # Baseline verification
    baseline = evaluate_supplier_intelligence(
        bom_items=demo.bom_items,
        supplier_quotes=demo.supplier_quotes,
        delivery_deadline_days=demo.delivery_deadline_days,
        budget_limit=demo.budget_limit,
    )
    apex_base = next(s for s in baseline.suppliers if s.supplier_id == "sup-a")
    beacon_base = next(s for s in baseline.suppliers if s.supplier_id == "sup-b")

    assert apex_base.true_landed_cost == Decimal("35931.00")
    assert beacon_base.true_landed_cost == Decimal("32978.64")
    assert baseline.recommended_supplier_id == "sup-b"

    # Scenario 1:
    req1 = DecisionReplayRequest(
        moq_overrides={"sup-a:BRG-6204-2RS": 200, "sup-a:FST-M8-ST-88": 800},
        freight_waivers={"sup-a": True},
    )
    res1 = replay_procurement_decision(
        bom_items=demo.bom_items,
        supplier_quotes=demo.supplier_quotes,
        delivery_deadline_days=demo.delivery_deadline_days,
        budget_limit=demo.budget_limit,
        request=req1,
    )

    apex_s1 = next(s for s in res1.suppliers if s.supplier_id == "sup-a")
    assert apex_s1.true_landed_cost == Decimal("30302.40"), f"Expected 30302.40, got {apex_s1.true_landed_cost}"
    assert res1.new_recommended_supplier_id == "sup-a"
    assert res1.winner_changed is True
    assert res1.projected_savings == Decimal("2676.24"), f"Expected 2676.24, got {res1.projected_savings}"

    # Scenario 2:
    req2 = DecisionReplayRequest(
        item_discounts_pct={"sup-a:CTR-BLDC-72V": 8.0},
    )
    res2 = replay_procurement_decision(
        bom_items=demo.bom_items,
        supplier_quotes=demo.supplier_quotes,
        delivery_deadline_days=demo.delivery_deadline_days,
        budget_limit=demo.budget_limit,
        request=req2,
    )

    apex_s2 = next(s for s in res2.suppliers if s.supplier_id == "sup-a")
    beacon_s2 = next(s for s in res2.suppliers if s.supplier_id == "sup-b")

    assert apex_s2.true_landed_cost == Decimal("34373.40"), f"Expected 34373.40, got {apex_s2.true_landed_cost}"
    assert beacon_s2.true_landed_cost == Decimal("32978.64")
    assert res2.new_recommended_supplier_id == "sup-b"
    assert res2.winner_changed is False
