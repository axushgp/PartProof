import io
import pytest
from decimal import Decimal
from httpx import AsyncClient

from app.core.config import settings
from app.schemas.procurement import (
    ProcurementAuditPayload,
    SupplierComparisonResult,
)
from app.services.procurement.parsers.normalizer import (
    normalize_to_bom_items,
    normalize_to_quote_items,
    ExtractedDocument,
)


@pytest.mark.asyncio
async def test_custom_procurement_http_lifecycle(client: AsyncClient):
    """
    Requirement 4 HTTP Integration Test:
    Exercises the complete custom non-EV dataset workflow over actual FastAPI HTTP endpoints:
    1. Authenticate with credentials -> obtain JWT access token.
    2. Upload non-EV Industrial Pump BOM + 3 supplier quotations via POST /api/v1/procurement/extract.
    3. Verify text extraction and normalized line items for all 4 documents.
    4. Reconcile via POST /api/v1/procurement/reconcile and verify forensic evaluation across 3 suppliers.
    5. Initialize an official task via POST /api/v1/procurement/create-task and verify awaiting_approval status.
    """
    # 1. Authenticate
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEMO_USER_EMAIL,
            "password": settings.DEMO_USER_PASSWORD,
        },
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Non-EV Dataset: Industrial Centrifugal Pump Assembly + 3 Supplier Quotes
    bom_csv = (
        "part_number,description,category,qty,uom,target_price\n"
        "PMP-HSG-316,Centrifugal Pump Casing SS316,Castings,50,pcs,450.00\n"
        "IMP-SFT-420,Martensitic Shaft SS420,Machined,50,pcs,120.00\n"
        "SEAL-SIC-50,Silicon Carbide Mechanical Seal,Seals,100,pcs,35.00\n"
    ).encode("utf-8")

    quote_1_csv = (
        "part_number,description,qty,unit_price,pack_size,moq,lead_time_days,freight\n"
        "PMP-HSG-316,Pump Casing Casting,50,440.00,1,50,21,1200.00\n"
        "IMP-SFT-420,Turned Shaft,50,115.00,1,50,14,0.00\n"
        "SEAL-SIC-50,SiC Cartridge Seal,100,32.00,1,150,10,0.00\n"
    ).encode("utf-8")

    quote_2_csv = (
        "part_number,description,qty,unit_price,pack_size,moq,lead_time_days,freight\n"
        "PMP-HSG-316,Pump Casing SS316,50,460.00,1,50,25,0.00\n"
        "IMP-SFT-420,Shaft SS420,50,118.00,1,50,18,0.00\n"
        "SEAL-SIC-50,Mechanical Seal SiC,100,34.00,10,100,14,0.00\n"
    ).encode("utf-8")

    quote_3_csv = (
        "part_number,description,qty,unit_price,pack_size,moq,lead_time_days,freight\n"
        "PMP-HSG-316,Centrifugal Pump Casing,50,450.00,1,50,20,500.00\n"
        "IMP-SFT-420,Machined Shaft 420,50,110.00,1,50,12,0.00\n"
        "SEAL-SIC-50,Cartridge Seal SiC-50,100,35.00,1,100,15,0.00\n"
    ).encode("utf-8")

    files = [
        ("bom_file", ("industrial_pump_bom.csv", bom_csv, "text/csv")),
        ("quote_files", ("apex_hydraulics_quote.csv", quote_1_csv, "text/csv")),
        ("quote_files", ("vortex_fluids_quote.csv", quote_2_csv, "text/csv")),
        ("quote_files", ("hydrotech_quote.csv", quote_3_csv, "text/csv")),
    ]
    data = {
        "supplier_names": "Apex Flow Hydraulics, Vortex Fluid Dynamics, HydroTech Components"
    }

    # 3. HTTP POST /api/v1/procurement/extract
    extract_resp = await client.post(
        "/api/v1/procurement/extract",
        headers=headers,
        files=files,
        data=data,
    )
    assert extract_resp.status_code == 200, f"Extract failed: {extract_resp.text}"
    extracted_docs = extract_resp.json()
    assert len(extracted_docs) == 4, f"Expected 4 extracted docs, got {len(extracted_docs)}"

    bom_doc = next(d for d in extracted_docs if d["doc_type"] == "bom")
    quote_docs = [d for d in extracted_docs if d["doc_type"] == "quote"]
    assert len(quote_docs) == 3, f"Expected 3 quote docs, got {len(quote_docs)}"

    # Normalize extracted docs
    parsed_bom_doc = ExtractedDocument(**bom_doc)
    bom_items = normalize_to_bom_items(parsed_bom_doc)
    assert len(bom_items) == 3

    supplier_quotes = {}
    for qd in quote_docs:
        parsed_qd = ExtractedDocument(**qd)
        supplier_quotes[parsed_qd.supplier_id] = normalize_to_quote_items(
            parsed_qd, parsed_qd.supplier_id, parsed_qd.supplier_name
        )

    assert len(supplier_quotes) == 3

    # 4. HTTP POST /api/v1/procurement/reconcile
    audit_payload = ProcurementAuditPayload(
        title="Industrial Pump SS316 Casing & Rotor Procurement",
        bom_items=bom_items,
        supplier_quotes=supplier_quotes,
        delivery_deadline_days=30,
        budget_limit=Decimal("50000.00"),
    )

    reconcile_resp = await client.post(
        "/api/v1/procurement/reconcile",
        headers=headers,
        json=audit_payload.model_dump(mode="json"),
    )
    assert reconcile_resp.status_code == 200, f"Reconcile failed: {reconcile_resp.text}"
    comparison_data = reconcile_resp.json()

    # Verify comparison results across all 3 suppliers
    assert len(comparison_data["suppliers"]) == 3
    sup_names = [s["supplier_name"] for s in comparison_data["suppliers"]]
    assert "Apex Flow Hydraulics" in sup_names
    assert "Vortex Fluid Dynamics" in sup_names
    assert "HydroTech Components" in sup_names

    # Check that synthetic demo supplier Beacon Precision Dynamics is not leaked
    assert "Beacon Precision Dynamics" not in sup_names

    # Check MOQ excess detected for Apex Flow Hydraulics on SEAL-SIC-50
    apex_sup = next(s for s in comparison_data["suppliers"] if s["supplier_id"] == "sup-1")
    assert Decimal(str(apex_sup["moq_excess_cost"])) == Decimal("1600.00")
    assert Decimal(str(apex_sup["freight_cost"])) == Decimal("1200.00")

    # 5. HTTP POST /api/v1/procurement/create-task
    create_task_resp = await client.post(
        "/api/v1/procurement/create-task",
        headers=headers,
        json=audit_payload.model_dump(mode="json"),
    )
    assert create_task_resp.status_code == 200, f"Create task failed: {create_task_resp.text}"
    task_detail = create_task_resp.json()

    assert task_detail["task"]["status"] == "awaiting_approval"
    assert task_detail["plan"] is not None
    assert task_detail["plan"]["plan_hash"] is not None
    assert len(task_detail["plan"]["plan_hash"]) == 64
    assert task_detail["plan"]["policy_result"]["allowed"] is True
