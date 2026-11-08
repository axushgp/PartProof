import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.database.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="auditor")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="user", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Task Lifecycle State:
    # created, planning, awaiting_approval, queued, preparing, running, verifying, succeeded, failed, cancel_requested, cancelled, timed_out, rejected
    status: Mapped[str] = mapped_column(String(50), default="created", index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="tasks")
    plan: Mapped[Optional["TaskPlan"]] = relationship("TaskPlan", back_populates="task", uselist=False, cascade="all, delete-orphan")
    executions: Mapped[List["Execution"]] = relationship("Execution", back_populates="task", cascade="all, delete-orphan")
    events: Mapped[List["ExecutionEvent"]] = relationship("ExecutionEvent", back_populates="task", cascade="all, delete-orphan")
    artifacts: Mapped[List["Artifact"]] = relationship("Artifact", back_populates="task", cascade="all, delete-orphan")
    approvals: Mapped[List["Approval"]] = relationship("Approval", back_populates="task", cascade="all, delete-orphan")


class TaskPlan(Base):
    __tablename__ = "task_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Validated structured JSON plan
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Deterministic cryptographic SHA-256 digest of canonical plan_json
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Deterministic policy engine evaluation
    policy_result: Mapped[dict] = mapped_column(JSON, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    policy_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    
    # pending, approved, rejected
    approval_status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="plan")


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    approval_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    
    # Canonical hash and immutable snapshot of the plan approved for this run
    plan_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    plan_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    sandbox_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # queued, preparing, running, verifying, succeeded, failed, timed_out, cancel_requested, cancelled, needs_reconciliation
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    
    runtime_image: Mapped[str] = mapped_column(String(100), default="python:3.12-slim")
    cpu_limit: Mapped[int] = mapped_column(Integer, default=1)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=512)
    network_mode: Mapped[str] = mapped_column(String(50), default="none")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    guest_kernel: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Distributed worker execution lease tracking
    worker_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=utc_now)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # verified_destroyed, leak_detected, pending_cleanup
    cleanup_status: Mapped[str] = mapped_column(String(50), default="pending_cleanup")
    
    # Full cryptographic execution receipt
    receipt_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="executions")
    approval: Mapped[Optional["Approval"]] = relationship("Approval", back_populates="execution")
    steps: Mapped[List["ExecutionStep"]] = relationship("ExecutionStep", back_populates="execution", cascade="all, delete-orphan")
    artifacts: Mapped[List["Artifact"]] = relationship("Artifact", back_populates="execution", cascade="all, delete-orphan")


class ExecutionStep(Base):
    __tablename__ = "execution_steps"
    __table_args__ = (
        UniqueConstraint("execution_id", "step_number", "attempt_number", name="uq_execution_step_attempt"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    execution_id: Mapped[str] = mapped_column(String(36), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, index=True)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    execution_type: Mapped[str] = mapped_column(String(50), default="python")
    code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    stdout: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stderr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    execution: Mapped["Execution"] = relationship("Execution", back_populates="steps")


class ExecutionEvent(Base):
    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="events")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("executions.id", ondelete="CASCADE"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="text/plain")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="artifacts")
    execution: Mapped[Optional["Execution"]] = relationship("Execution", back_populates="artifacts")


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("task_id", "approved_plan_hash", name="uq_approvals_task_plan_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_plan_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)  # approved, rejected
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["Task"] = relationship("Task", back_populates="approvals")
    execution: Mapped[Optional["Execution"]] = relationship("Execution", back_populates="approval", uselist=False)
