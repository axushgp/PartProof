import json
from decimal import Decimal
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.entities import Task, TaskPlan, User
from app.schemas.execution import TaskDetail
from app.schemas.plan import PlanStepSchema, TaskPlanSchema
from app.schemas.procurement import (
    BOMItem,
    DecisionReplayRequest,
    DecisionReplayResult,
    ExtractedDocument,
    ProcurementAuditPayload,
    QuoteItem,
    SupplierComparisonResult,
)
from app.schemas.task import TaskPlanRead, TaskRead
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.policy.engine import DeterministicPolicyEngine
from app.services.procurement.demo_data import get_synthetic_demo_payload
from app.services.procurement.execution_script import generate_procurement_execution_script
from app.services.procurement.intelligence import evaluate_supplier_intelligence
from app.services.procurement.parsers.normalizer import (
    normalize_to_bom_items,
    normalize_to_quote_items,
    parse_and_normalize_file,
)
from app.services.procurement.replay import replay_procurement_decision

router = APIRouter()


@router.get("/demo", response_model=ProcurementAuditPayload)
async def get_demo_case():
    """Returns the preloaded synthetic demonstration dataset."""
    return get_synthetic_demo_payload()


@router.post("/extract", response_model=List[ExtractedDocument])
async def extract_procurement_documents(
    bom_file: Optional[UploadFile] = File(None),
    quote_files: List[UploadFile] = File(...),
    supplier_names: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    Extracts text and line-items from uploaded BOM and supplier quotation files.
    Identifies file types (CSV, XLSX, PDF) and surfaces OCR warnings for scanned documents.
    """
    results: List[ExtractedDocument] = []

    # Parse BOM file if provided
    if bom_file and bom_file.filename:
        bom_bytes = await bom_file.read()
        extracted_bom = parse_and_normalize_file(
            content_bytes=bom_bytes,
            filename=bom_file.filename,
            doc_type="bom",
        )
        results.append(extracted_bom)

    # Parse supplier quotation files
    sup_name_list = [s.strip() for s in (supplier_names or "").split(",") if s.strip()]

    for idx, q_file in enumerate(quote_files):
        if not q_file.filename:
            continue
        q_bytes = await q_file.read()
        sup_id = f"sup-{idx + 1}"
        sup_name = (
            sup_name_list[idx]
            if idx < len(sup_name_list)
            else f"Supplier {chr(65 + idx)}"
        )

        extracted_quote = parse_and_normalize_file(
            content_bytes=q_bytes,
            filename=q_file.filename,
            doc_type="quote",
            supplier_id=sup_id,
            supplier_name=sup_name,
        )
        results.append(extracted_quote)

    return results


@router.post("/reconcile", response_model=SupplierComparisonResult)
async def reconcile_procurement(
    payload: ProcurementAuditPayload,
    current_user: User = Depends(get_current_user),
):
    """
    Performs deterministic forensics, landed-cost calculation, and supplier intelligence.
    """
    try:
        return evaluate_supplier_intelligence(
            bom_items=payload.bom_items,
            supplier_quotes=payload.supplier_quotes,
            delivery_deadline_days=payload.delivery_deadline_days,
            budget_limit=payload.budget_limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Reconciliation error: {str(e)}",
        )


@router.post("/replay", response_model=DecisionReplayResult)
async def replay_decision(
    audit_payload: ProcurementAuditPayload,
    replay_request: DecisionReplayRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Deterministically evaluates what-if scenario assumptions (discounts, freight waivers, MOQs).
    """
    try:
        return replay_procurement_decision(
            bom_items=audit_payload.bom_items,
            supplier_quotes=audit_payload.supplier_quotes,
            delivery_deadline_days=audit_payload.delivery_deadline_days,
            budget_limit=audit_payload.budget_limit,
            request=replay_request,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Decision replay error: {str(e)}",
        )


@router.post("/create-task", response_model=TaskDetail)
async def create_procurement_task(
    payload: ProcurementAuditPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiates the official PartProof execution lifecycle for a procurement audit.
    Generates a deterministic Python execution step that writes the 5 decision pack artifacts:
    bom_audit.csv, supplier_comparison.csv, discrepancy_register.csv, procurement_decision.json, negotiation_brief.md.
    Evaluates policy and transitions task to awaiting_approval.
    """
    # 1. Create Task record
    task = Task(
        user_id=current_user.id,
        title=f"Procurement Audit: {payload.title}",
        description=(
            f"Deterministic forensic audit of {len(payload.bom_items)} BOM items across "
            f"{len(payload.supplier_quotes)} supplier quotations."
        ),
        status="planning",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 2. Build Python Execution Script containing the deterministic audit calculation
    python_code = generate_procurement_execution_script(payload)

    expected_artifacts = [
        "bom_audit.csv",
        "supplier_comparison.csv",
        "discrepancy_register.csv",
        "procurement_decision.json",
        "negotiation_brief.md",
    ]

    plan_schema = TaskPlanSchema(
        title=task.title,
        summary="Deterministic forensic procurement audit and decision pack generation.",
        reasoning_summary="Executes isolated deterministic arithmetic to generate verifiable procurement pack artifacts.",
        steps=[
            PlanStepSchema(
                step_id="step-procurement-001",
                description="Deterministic Procurement Calculation & Decision Pack Generation",
                execution_type="python",
                code=python_code,
            )
        ],
        expected_artifacts=expected_artifacts,
        network_required=False,
    )

    # 3. Deterministic Policy Evaluation
    policy_engine = DeterministicPolicyEngine()
    policy_res = policy_engine.evaluate(plan_schema)
    plan_hash = policy_res.plan_hash or compute_plan_hash(plan_schema)

    # 4. Store TaskPlan
    task_plan = TaskPlan(
        task_id=task.id,
        model="vultr-glm-5.3-procurement",
        plan_json=plan_schema.model_dump(mode="json"),
        plan_hash=plan_hash,
        policy_result=policy_res.model_dump(mode="json"),
        policy_version=policy_res.policy_version,
        policy_evaluated_at=policy_res.evaluated_at,
        approval_status="pending" if policy_res.allowed else "rejected",
    )
    db.add(task_plan)
    task.status = "awaiting_approval" if policy_res.allowed else "failed"

    await db.commit()
    await db.refresh(task)
    await db.refresh(task_plan)

    return TaskDetail(
        task=TaskRead.model_validate(task),
        plan=TaskPlanRead.model_validate(task_plan),
        latest_execution=None,
        artifacts=[],
        events=[],
    )
