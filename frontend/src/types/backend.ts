/**
 * PartProof Backend Schema Type Definitions
 * Strictly aligned with FastAPI Pydantic models in backend/app/schemas/
 */

export type TaskStatus =
  | "created"
  | "planning"
  | "awaiting_approval"
  | "queued"
  | "preparing"
  | "running"
  | "verifying"
  | "succeeded"
  | "failed"
  | "cancel_requested"
  | "cancelled"
  | "timed_out"
  | "rejected"
  | string;

export type ExecutionStatus =
  | "queued"
  | "preparing"
  | "running"
  | "verifying"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out"
  | "needs_reconciliation"
  | string;

export type CleanupStatus =
  | "untracked"
  | "verified_destroyed"
  | "leak_detected"
  | "timeout"
  | "failed"
  | string;

export interface UserRead {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  confirm_password?: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  role: string;
}

export interface PlanStepSchema {
  step_id: string;
  description: string;
  execution_type: string;
  code: string;
  expected_output?: string | null;
}

export interface TaskPlanSchema {
  title: string;
  summary: string;
  reasoning_summary: string;
  steps: PlanStepSchema[];
  required_capabilities: string[];
  network_required: boolean;
  success_criteria: string[];
  expected_artifacts: string[];
}

export interface PolicyEvaluationResult {
  allowed: boolean;
  policy_name: string;
  policy_version: string;
  image?: string;
  cpu_limit: number;
  memory_limit_mb: number;
  timeout_seconds: number;
  network_mode: string;
  approval_required?: boolean;
  plan_hash?: string | null;
  evaluated_at?: string | null;
  max_output_bytes?: number;
  reasons?: string[];
  violations?: string[];
  warnings?: string[];
  rule_results?: Array<Record<string, unknown>>;
}

export interface TaskPlanRead {
  id: string;
  task_id: string;
  model: string;
  plan_json: TaskPlanSchema;
  plan_hash: string;
  policy_result: PolicyEvaluationResult;
  policy_version: string;
  policy_evaluated_at?: string | null;
  approval_status: string;
  created_at: string;
}

export interface TaskRead {
  id: string;
  user_id?: string | null;
  title: string;
  description: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
}

export interface ApprovalRead {
  id: string;
  task_id: string;
  approved_by?: string | null;
  approved_plan_hash?: string | null;
  decision: "approved" | "rejected";
  reason?: string | null;
  created_at: string;
}

export interface ExecutionStepRead {
  id: string;
  task_id?: string;
  execution_id?: string;
  step_number: number;
  description: string;
  execution_type: string;
  code?: string | null;
  status: string;
  stdout?: string | null;
  stderr?: string | null;
  exit_code?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ArtifactRead {
  id: string;
  task_id: string;
  execution_id?: string | null;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface ExecutionReceipt {
  task_id: string;
  execution_id: string;
  plan_hash?: string;
  policy_name?: string;
  policy_version?: string;
  sandbox_id?: string | null;
  status: string;
  runtime_image: string;
  guest_kernel?: string | null;
  cpu_limit: number;
  memory_limit_mb: number;
  network_mode: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  exit_code?: number | null;
  cleanup_status: string;
  steps_executed: number;
  steps_failed?: number;
  artifacts: ArtifactRead[];
  security_verified: boolean;
  verification_hash: string;
  signature?: string;
}

export interface ExecutionRead {
  id: string;
  task_id: string;
  worker_id?: string | null;
  lease_expires_at?: string | null;
  sandbox_id?: string | null;
  status: ExecutionStatus;
  runtime_image: string;
  cpu_limit: number;
  memory_limit_mb: number;
  network_mode: string;
  guest_kernel?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  created_at?: string;
  updated_at?: string;
  exit_code?: number | null;
  cleanup_status: string;
  receipt_json?: ExecutionReceipt | null;
  steps: ExecutionStepRead[];
  artifacts: ArtifactRead[];
}

export interface ExecutionEventRead {
  id: string;
  task_id?: string;
  execution_id?: string | null;
  event_type: string;
  message: string;
  data?: Record<string, unknown>;
  metadata_json?: Record<string, unknown> | null;
  timestamp: string;
}

export interface TaskDetail {
  task: TaskRead;
  plan?: TaskPlanRead | null;
  latest_execution?: ExecutionRead | null;
  latest_approval?: ApprovalRead | null;
  artifacts: ArtifactRead[];
  events: ExecutionEventRead[];
}

export interface TaskCreate {
  title?: string | null;
  description: string;
}

export interface TaskApproveRequest {
  decision: "approved" | "rejected";
  reason?: string | null;
}

export interface TaskCancelRequest {
  reason?: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
  database_connected: boolean;
  sandbox_backend: string;
}

export interface SystemStatus {
  status: string;
  environment: string;
  vultr_inference_configured: boolean;
  vultr_inference_model: string;
  sandbox_backend: string;
  sandbox_ready: boolean;
  database_connected: boolean;
  active_sandboxes: number;
  max_concurrent_sandboxes: number;
  security_invariants: {
    network_disabled_by_default: boolean;
    credentials_in_sandbox: boolean;
    max_memory_mb: number;
    max_cpus: number;
    max_timeout_seconds: number;
    ephemeral_sandboxes: boolean;
    automatic_cleanup: boolean;
    [key: string]: unknown;
  };
}

export interface ProviderHealth {
  status: "reachable" | "not_configured" | "auth_failed" | "rate_limited" | "unreachable" | "degraded" | string;
  model: string;
  latency_ms?: number | null;
  message?: string | null;
}
