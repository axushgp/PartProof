import copy
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_task_planner
from app.core.config import settings
from app.database.session import get_db
from app.models.entities import Approval, Execution, ExecutionEvent, Task, TaskPlan, User
from app.schemas.plan import PolicyEvaluationResult, TaskPlanSchema
from app.schemas.task import (
    ApprovalRead,
    TaskApproveRequest,
    TaskCancelRequest,
    TaskCreate,
    TaskPlanRead,
    TaskRead,
)
from app.schemas.execution import (
    ArtifactRead,
    ExecutionEventRead,
    ExecutionRead,
    ExecutionStepRead,
    TaskDetail,
)
from app.services.inference.exceptions import InferenceError, TaskPlanningError
from app.services.inference.planner import TaskPlanner
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.policy.engine import DeterministicPolicyEngine

router = APIRouter()


def _build_execution_read(execution: Execution) -> ExecutionRead:
    """Safely constructs ExecutionRead without triggering async greenlet lazy-loading."""
    steps = (
        [ExecutionStepRead.model_validate(s) for s in execution.steps]
        if "steps" in execution.__dict__ and execution.steps
        else []
    )
    artifacts = (
        [ArtifactRead.model_validate(a) for a in execution.artifacts]
        if "artifacts" in execution.__dict__ and execution.artifacts
        else []
    )
    return ExecutionRead(
        id=execution.id,
        task_id=execution.task_id,
        sandbox_id=execution.sandbox_id,
        status=execution.status,
        runtime_image=execution.runtime_image,
        cpu_limit=execution.cpu_limit,
        memory_limit_mb=execution.memory_limit_mb,
        network_mode=execution.network_mode,
        guest_kernel=execution.guest_kernel,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        exit_code=execution.exit_code,
        cleanup_status=execution.cleanup_status,
        receipt_json=execution.receipt_json,
        steps=steps,
        artifacts=artifacts,
    )


def _build_task_detail(task: Task) -> TaskDetail:
    """Builds a typed TaskDetail response from a task and its loaded relationships."""
    plan_read = TaskPlanRead.model_validate(task.plan) if getattr(task, "plan", None) else None
    
    executions = task.executions if "executions" in task.__dict__ and task.executions else []
    latest_execution = _build_execution_read(executions[-1]) if executions else None

    approvals = task.approvals if "approvals" in task.__dict__ and task.approvals else []
    latest_approval = ApprovalRead.model_validate(approvals[-1]) if approvals else None

    artifacts = [ArtifactRead.model_validate(a) for a in task.artifacts] if "artifacts" in task.__dict__ and task.artifacts else []
    events = [ExecutionEventRead.model_validate(e) for e in task.events] if "events" in task.__dict__ and task.events else []

    return TaskDetail(
        task=TaskRead.model_validate(task),
        plan=plan_read,
        latest_execution=latest_execution,
        latest_approval=latest_approval,
        artifacts=artifacts,
        events=events,
    )


@router.post("", response_model=TaskDetail, status_code=status.HTTP_201_CREATED)
async def create_and_plan_task(
    payload: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    planner: TaskPlanner = Depends(get_task_planner),
):
    """
    Creates a new task and generates an AI execution plan via Vultr Serverless Inference.
    Does NOT execute any code automatically; transitions task to 'awaiting_approval'.
    """
    task = Task(
        user_id=current_user.id,
        title=payload.title or payload.description[:50],
        description=payload.description,
        status="planning",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    try:
        plan_schema, metadata = await planner.plan_task(payload.description)
        
        # Apply deterministic policy engine evaluation
        policy_engine = DeterministicPolicyEngine()
        policy_res = policy_engine.evaluate(plan_schema)
        plan_hash = policy_res.plan_hash or compute_plan_hash(plan_schema)

        # Update task title from plan if not explicitly supplied
        if not payload.title:
            task.title = plan_schema.title

        task_plan = TaskPlan(
            task_id=task.id,
            model=metadata.model,
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

    except (InferenceError, TaskPlanningError) as e:
        logger_status = "failed"
        task.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY if isinstance(e, InferenceError) else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Task planning failed: {e.message if hasattr(e, 'message') else str(e)}",
        )
    except Exception as e:
        task.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during task planning: {str(e)}",
        )

    # Return full task detail
    return TaskDetail(
        task=TaskRead.model_validate(task),
        plan=TaskPlanRead.model_validate(task_plan),
        latest_execution=None,
        artifacts=[],
        events=[],
    )


@router.post("/{task_id}/plan", response_model=TaskPlanRead)
async def generate_or_regenerate_plan(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    planner: TaskPlanner = Depends(get_task_planner),
):
    """
    Generates or regenerates an AI execution plan for an existing task.
    Enforces pessimistic row-locking and strict state validation:
    - Rejects regeneration if task plan has already been approved (approval_status == 'approved')
    - Rejects regeneration if task has queued, active, or completed executions
    - Rejects regeneration if task is currently undergoing planning
    - Rejects regeneration if task is in non-plannable states (queued, running, succeeded, etc.)
    - Preserves prior approval records and immutable execution snapshots
    - Permits regeneration after plan rejection, producing a fresh canonical plan hash
    """
    # 1. Acquire pessimistic lock on Task row
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.plan),
            selectinload(Task.executions),
            selectinload(Task.approvals),
        )
        .with_for_update(of=Task)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Verify authorization
    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # 2. Strict State Validation
    if task.plan and task.plan.approval_status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot regenerate plan: plan has already been approved.",
        )

    if task.executions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot regenerate plan: task already has {len(task.executions)} execution record(s).",
        )

    if task.status in ["queued", "preparing", "running", "verifying", "succeeded", "timed_out", "cancelled", "cancel_requested"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot regenerate plan: task is in non-plannable status '{task.status}'.",
        )

    if task.status == "planning":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot regenerate plan: task is currently undergoing planning.",
        )

    # Transition to planning and commit to release lock during inference
    task.status = "planning"
    await db.commit()

    # 3. AI Planning Call
    try:
        plan_schema, metadata = await planner.plan_task(task.description)
        policy_engine = DeterministicPolicyEngine()
        policy_res = policy_engine.evaluate(plan_schema)
        plan_hash = policy_res.plan_hash or compute_plan_hash(plan_schema)
    except Exception as e:
        # Re-lock task to record failed state if not cancelled
        res = await db.execute(
            select(Task).where(Task.id == task_id).with_for_update(of=Task)
        )
        t_locked = res.scalar_one_or_none()
        if t_locked and t_locked.status != "cancelled":
            t_locked.status = "failed"
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY if isinstance(e, InferenceError) else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plan generation failed: {str(e)}",
        )

    # 4. Re-acquire lock to atomically update Task and TaskPlan
    res = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.plan))
        .with_for_update(of=Task)
    )
    task_locked = res.scalar_one()

    if task_locked.status == "cancelled":
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task was cancelled while plan generation was in progress.",
        )

    if task_locked.status not in ["planning", "awaiting_approval", "rejected", "failed"]:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task transitioned to unexpected state '{task_locked.status}' during planning.",
        )

    if task_locked.plan:
        task_locked.plan.model = metadata.model
        task_locked.plan.plan_json = plan_schema.model_dump(mode="json")
        task_locked.plan.plan_hash = plan_hash
        task_locked.plan.policy_result = policy_res.model_dump(mode="json")
        task_locked.plan.policy_version = policy_res.policy_version
        task_locked.plan.policy_evaluated_at = policy_res.evaluated_at
        task_locked.plan.approval_status = "pending" if policy_res.allowed else "rejected"
        task_plan = task_locked.plan
    else:
        task_plan = TaskPlan(
            task_id=task_locked.id,
            model=metadata.model,
            plan_json=plan_schema.model_dump(mode="json"),
            plan_hash=plan_hash,
            policy_result=policy_res.model_dump(mode="json"),
            policy_version=policy_res.policy_version,
            policy_evaluated_at=policy_res.evaluated_at,
            approval_status="pending" if policy_res.allowed else "rejected",
        )
        db.add(task_plan)

    task_locked.status = "awaiting_approval" if policy_res.allowed else "failed"
    await db.commit()
    await db.refresh(task_plan)
    return TaskPlanRead.model_validate(task_plan)


@router.get("/{task_id}/plan", response_model=TaskPlanRead)
async def get_task_plan(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves the validated AI execution plan for a task.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.plan))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not task.plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No plan generated for this task")

    return TaskPlanRead.model_validate(task.plan)


@router.get("", response_model=List[TaskRead])
async def list_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists tasks belonging to the authenticated user."""
    stmt = select(Task).order_by(Task.created_at.desc())
    if current_user.role != "admin":
        stmt = stmt.where(Task.user_id == current_user.id)
    
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [TaskRead.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task_detail(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves full details of a task, including its plan, execution, and artifacts."""
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.plan),
            selectinload(Task.executions),
            selectinload(Task.approvals),
            selectinload(Task.artifacts),
            selectinload(Task.events),
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return _build_task_detail(task)


@router.post("/{task_id}/approve", response_model=TaskDetail)
async def approve_or_reject_task(
    task_id: str,
    payload: TaskApproveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submits a user approval or rejection decision for a task plan.
    Atomically binds decision to canonical plan hash, verifies deterministic policy,
    and queues exactly one execution record if approved.
    """
    stmt = (
        select(Task)
        .where(Task.id == task_id)
        .with_for_update(of=Task)
        .options(
            selectinload(Task.plan),
            selectinload(Task.executions),
            selectinload(Task.approvals),
            selectinload(Task.events),
            selectinload(Task.artifacts),
        )
    )
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    decision = payload.decision.strip().lower()
    if decision not in ("approved", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be either 'approved' or 'rejected'.",
        )

    # 1. Plan existence validation
    if not task.plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No plan exists for this task. Plan must be generated before approval.",
        )
    task_plan = task.plan

    # 2. Cryptographic plan integrity check
    recomputed_hash = compute_plan_hash(task_plan.plan_json)
    if recomputed_hash != task_plan.plan_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Plan integrity compromised: recomputed hash ({recomputed_hash[:12]}...) "
                f"does not match stored hash ({task_plan.plan_hash[:12]}...)."
            ),
        )

    # 3. Policy re-evaluation and verification
    persisted_policy = task_plan.policy_result
    if not isinstance(persisted_policy, dict) or not persisted_policy.get("allowed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Persisted policy evaluation is missing, invalid, or disallowed.",
        )

    try:
        plan_schema = TaskPlanSchema.model_validate(task_plan.plan_json)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stored plan JSON fails schema validation: {str(e)}",
        )

    policy_engine = DeterministicPolicyEngine()
    fresh_policy_res = policy_engine.evaluate(plan_schema)
    if not fresh_policy_res.allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plan policy evaluation disallowed: {'; '.join(fresh_policy_res.violations)}",
        )

    # 4. Check for existing approval records for this plan hash
    existing_approval = next(
        (a for a in task.approvals if a.approved_plan_hash == task_plan.plan_hash),
        None,
    )

    if existing_approval:
        if existing_approval.decision == decision:
            # Idempotent repeat: return current task state
            return _build_task_detail(task)
        else:
            # Conflicting decision on same plan hash
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conflicting decision: plan was already {existing_approval.decision}.",
            )

    # 5. State eligibility check
    if task.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is in rejected state. A new plan must be generated before approval.",
        )

    if task.status != "awaiting_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is in state '{task.status}' and cannot receive an approval decision.",
        )

    # 6. Apply atomic state transition
    try:
        if decision == "approved":
            approval = Approval(
                task_id=task.id,
                approved_by=current_user.email,
                approved_plan_hash=task_plan.plan_hash,
                decision="approved",
                reason=payload.reason,
            )
            db.add(approval)
            await db.flush()  # Populates approval.id for execution FK

            task_plan.approval_status = "approved"

            execution = Execution(
                task_id=task.id,
                approval_id=approval.id,
                plan_hash=task_plan.plan_hash,
                plan_snapshot=copy.deepcopy(task_plan.plan_json),
                status="queued",
                runtime_image=fresh_policy_res.image or settings.SANDBOX_DEFAULT_IMAGE,
                cpu_limit=fresh_policy_res.cpu_limit or settings.SANDBOX_DEFAULT_CPUS,
                memory_limit_mb=fresh_policy_res.memory_limit_mb or settings.SANDBOX_DEFAULT_MEMORY_MB,
                network_mode=fresh_policy_res.network_mode or "none",
                timeout_seconds=fresh_policy_res.timeout_seconds or settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS,
                queued_at=datetime.now(timezone.utc),
            )
            db.add(execution)
            await db.flush()

            task.status = "queued"

            event = ExecutionEvent(
                task_id=task.id,
                execution_id=execution.id,
                event_type="execution_queued",
                message=f"Plan approved by {current_user.email} (hash={task_plan.plan_hash[:12]}...). Execution queued.",
                metadata_json={
                    "approved_by": current_user.email,
                    "plan_hash": task_plan.plan_hash,
                    "policy_version": task_plan.policy_version,
                    "reason": payload.reason,
                },
            )
            db.add(event)

            await db.commit()
            await db.refresh(task)
            await db.refresh(task_plan)
            await db.refresh(execution)
            await db.refresh(approval)

        elif decision == "rejected":
            approval = Approval(
                task_id=task.id,
                approved_by=current_user.email,
                approved_plan_hash=task_plan.plan_hash,
                decision="rejected",
                reason=payload.reason,
            )
            db.add(approval)

            task_plan.approval_status = "rejected"
            task.status = "rejected"

            event = ExecutionEvent(
                task_id=task.id,
                event_type="plan_rejected",
                message=f"Plan rejected by {current_user.email}: {payload.reason or 'No reason provided'}",
                metadata_json={
                    "rejected_by": current_user.email,
                    "plan_hash": task_plan.plan_hash,
                    "reason": payload.reason,
                },
            )
            db.add(event)

            await db.commit()
            await db.refresh(task)
            await db.refresh(task_plan)
            await db.refresh(approval)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: A concurrent approval or execution record already exists for this task.",
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record approval decision: {str(e)}",
        )

    return _build_task_detail(task)


@router.post("/{task_id}/cancel", response_model=TaskDetail)
async def cancel_task(
    task_id: str,
    payload: TaskCancelRequest = TaskCancelRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancels a task according to the strict state machine:
    - created/planning/awaiting_approval: marked 'cancelled' safely.
    - queued: queued execution and task atomically marked 'cancelled'.
    - preparing/running/verifying: marked 'cancel_requested'.
    - terminal states (succeeded, failed, timed_out, rejected): 409 conflict.
    - cancelled/cancel_requested: idempotent 200.
    """
    stmt = (
        select(Task)
        .where(Task.id == task_id)
        .with_for_update(of=Task)
        .options(
            selectinload(Task.plan),
            selectinload(Task.executions),
            selectinload(Task.approvals),
            selectinload(Task.events),
            selectinload(Task.artifacts),
        )
    )
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    reason = payload.reason or "Cancelled by user"

    # 1. Idempotent repeat if already cancelled
    if task.status == "cancelled":
        return _build_task_detail(task)

    # 2. Idempotent repeat if cancel already requested
    if task.status == "cancel_requested":
        return _build_task_detail(task)

    # 3. Created, planning, or awaiting_approval (no execution running or queued)
    if task.status in ("created", "planning", "awaiting_approval"):
        task.status = "cancelled"
        if task.plan:
            task.plan.approval_status = "cancelled"

        event = ExecutionEvent(
            task_id=task.id,
            event_type="task_cancelled",
            message=f"Task cancelled before execution: {reason}",
            metadata_json={"cancelled_by": current_user.email, "reason": reason},
        )
        db.add(event)
        await db.commit()
        await db.refresh(task)
        return _build_task_detail(task)

    # 4. Queued: execution is waiting in persistent queue
    if task.status == "queued":
        queued_exec = next((e for e in task.executions if e.status == "queued"), None)
        if queued_exec:
            queued_exec.status = "cancelled"
            queued_exec.completed_at = datetime.now(timezone.utc)
            queued_exec.exit_code = 130  # Standard SIGINT/Abort exit code

        task.status = "cancelled"

        event = ExecutionEvent(
            task_id=task.id,
            execution_id=queued_exec.id if queued_exec else None,
            event_type="execution_cancelled",
            message=f"Execution cancelled while queued: {reason}",
            metadata_json={"cancelled_by": current_user.email, "reason": reason},
        )
        db.add(event)
        await db.commit()
        await db.refresh(task)
        return _build_task_detail(task)

    # 5. Active execution: preparing, running, verifying
    if task.status in ("preparing", "running", "verifying"):
        task.status = "cancel_requested"
        running_exec = next(
            (e for e in task.executions if e.status in ("preparing", "running", "verifying")),
            None,
        )
        if running_exec:
            running_exec.status = "cancel_requested"

        event = ExecutionEvent(
            task_id=task.id,
            execution_id=running_exec.id if running_exec else None,
            event_type="cancel_requested",
            message=f"Cancellation requested for running execution: {reason}",
            metadata_json={"cancelled_by": current_user.email, "reason": reason},
        )
        db.add(event)
        await db.commit()
        await db.refresh(task)
        return _build_task_detail(task)

    # 6. Terminal states cannot be rewritten
    if task.status in ("succeeded", "failed", "timed_out", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is in terminal state '{task.status}' and cannot be cancelled.",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Cannot cancel task in state '{task.status}'.",
    )
