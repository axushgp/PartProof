from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.entities import Task, TaskPlan, User
from app.schemas.plan import PolicyEvaluationResult, TaskPlanSchema
from app.schemas.task import TaskCreate, TaskPlanRead, TaskRead
from app.schemas.execution import TaskDetail
from app.services.inference.exceptions import InferenceError, TaskPlanningError
from app.services.inference.planner import TaskPlanner
from app.services.orchestration.plan_integrity import compute_plan_hash
from app.services.policy.engine import DeterministicPolicyEngine

router = APIRouter()


@router.post("", response_model=TaskDetail, status_code=status.HTTP_201_CREATED)
async def create_and_plan_task(
    payload: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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

    planner = TaskPlanner()

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
):
    """
    Generates or regenerates an AI execution plan for an existing task.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.plan))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Verify authorization
    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    task.status = "planning"
    await db.commit()

    planner = TaskPlanner()

    try:
        plan_schema, metadata = await planner.plan_task(task.description)
        policy_engine = DeterministicPolicyEngine()
        policy_res = policy_engine.evaluate(plan_schema)
        plan_hash = policy_res.plan_hash or compute_plan_hash(plan_schema)

        if task.plan:
            task.plan.model = metadata.model
            task.plan.plan_json = plan_schema.model_dump(mode="json")
            task.plan.plan_hash = plan_hash
            task.plan.policy_result = policy_res.model_dump(mode="json")
            task.plan.policy_version = policy_res.policy_version
            task.plan.policy_evaluated_at = policy_res.evaluated_at
            task.plan.approval_status = "pending" if policy_res.allowed else "rejected"
            task_plan = task.plan
        else:
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
        await db.refresh(task_plan)
        return TaskPlanRead.model_validate(task_plan)

    except Exception as e:
        task.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY if isinstance(e, InferenceError) else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plan generation failed: {str(e)}",
        )


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
            selectinload(Task.artifacts),
            selectinload(Task.events),
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    plan_read = TaskPlanRead.model_validate(task.plan) if task.plan else None

    return TaskDetail(
        task=TaskRead.model_validate(task),
        plan=plan_read,
        latest_execution=None,
        artifacts=[],
        events=[],
    )
