# PartProof Architecture Specification

## 1. Executive Overview
**PartProof** is an autonomous engineering task and audit execution platform built for the **Vultr Agent Rush Hackathon (Challenge 1: Blast Radius Zero)**. It enforces a strict containment paradigm:
> *"Plan before execution. Policy before permissions. Isolated microVM execution instead of unrestricted host access."*

The architecture separates responsibilities across three discrete trust boundaries:
1. **Control & Ingestion Plane (FastAPI + PostgreSQL + Next.js)**: Runs on the Vultr Cloud Compute host as a dedicated non-root user (`linuxuser`). Manages user intent, authentication, orchestration, deterministic policy enforcement, and execution receipt storage.
2. **Cognitive Plane (Vultr Serverless Inference)**: Stateless OpenAI-compatible LLM endpoint (`glm-5.3`) providing task planning and Python analysis generation. Strictly isolated; inference credentials never enter sandboxes or browser requests.
3. **Execution Plane (Microsandbox on KVM)**: Ephemeral microVMs running on hardware-accelerated Linux KVM via `libkrun`. Each task executes with an independent guest kernel (`6.12.113`), zero network access (`Network.none()`), strict resource limits (1 vCPU, 512MB RAM), and automatic disposal.

```
                      +---------------------------------------+
                      |          Web Browser / User           |
                      |   (Next.js Dashboard + SSE Terminal)  |
                      +-------------------+-------------------+
                                          |
                                    HTTPS / REST
                                          |
+-----------------------------------------v-----------------------------------------+
| VULTR CLOUD COMPUTE HOST (Ubuntu 24.04 LTS / AMD EPYC Turin / VX1 Dedicated CPU)  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | CONTROL PLANE (FastAPI Service - Running as 'linuxuser')                    |  |
|  |                                                                             |  |
|  |  +------------------+     +--------------------+     +-------------------+  |  |
|  |  | Task API & SSE   |     | Agent Orchestrator |     | Policy Engine     |  |  |
|  |  +------------------+     +---------+----------+     +---------+---------+  |  |
|  |                                     |                          |            |  |
|  |                                     v                          v            |  |
|  |                          [ Structured Plan JSON ]   [ Deterministic Gate ]  |  |
|  |                                     |                          |            |  |
|  |                                     +------------+-------------+            |  |
|  |                                                  |                          |  |
|  |                                                  v                          |  |
|  |                                     +------------+------------+             |  |
|  |                                     | Single Execution Worker |             |  |
|  |                                     +------------+------------+             |  |
|  +--------------------------------------------------|--------------------------+  |
|                                                     |                             |
|       +---------------------------------------------+-----+                       |
|       |                                                   |                       |
|       v                                                   v                       |
|  +---------------------------+        +----------------------------------------+  |
|  | PostgreSQL (Docker)       |        | Sandbox Manager & Microsandbox Driver  |  |
|  | - Tasks & Executions      |        | (/home/linuxuser/.microsandbox)        |  |
|  | - Execution Receipts      |        +-------------------+--------------------+  |
|  | - Verified Artifacts      |                            |                       |
|  +---------------------------+                            |                       |
|                                                           v                       |
|                             +-----------------------------+---------------------+ |
|                             | HARDWARE VIRTUALIZATION (/dev/kvm)                | |
|                             |                                                   | |
|                             |  +----------------------------------------------+ | |
|                             |  | Ephemeral MicroVM (libkrun / python:3.12)    | | |
|                             |  | - Guest Kernel: 6.12.113                     | | |
|                             |  | - Network: Disabled (Network.none())         | | |
|                             |  | - CPU Limit: 1 vCPU, RAM Limit: 512 MB       | | |
|                             |  | - Filesystem: Isolated sparse guest fs       | | |
|                             |  | - Secrets: ZERO credentials injected         | | |
|                             |  +----------------------------------------------+ | |
|                             +---------------------------------------------------+ |
+-----------------------------------------------------------------------------------+
                                         |
                                    API Request
                                         |
                                         v
                      +---------------------------------------+
                      |       Vultr Serverless Inference      |
                      |   (https://api.vultrinference.com)    |
                      |   Model: glm-5.3 / glm-5.3-flash      |
                      +---------------------------------------+
```

---

## 2. Component Breakdown

### 2.1 Backend Application (`backend/app/`)
* **`api/`**: REST API endpoints for authentication, task creation, plan inspection, approval/cancellation, SSE event streaming, artifact downloads, and system health status.
  - `POST /api/v1/tasks/{task_id}/approve`: Validates user authorization; performs row-level locking (`with_for_update()`); ensures task is in `awaiting_approval` state; verifies cryptographic plan integrity against canonical SHA-256 hash; re-evaluates deterministic security policy; handles idempotent repeats and conflicting decisions; atomically records `Approval`, marks `TaskPlan` and `Task`, creates queued `Execution` snapshot, and records `ExecutionEvent`. Queued executions wait for the persistent background worker (Checkpoint 4C).
  - `POST /api/v1/tasks/{task_id}/cancel`: Validates user authorization; performs row-level locking; idempotently handles already cancelled tasks; cancels pending plans and queued executions; transitions active executions to `cancel_requested` without falsely claiming processes stopped; rejects terminal tasks with `409 Conflict`.
* **`services/inference/`**:
  - `VultrInferenceClient`: High-throughput async client for Vultr Serverless Inference (`https://api.vultrinference.com/v1`). Features bounded exponential backoff retries, rate limit (429) & timeout resilience, automatic fallback model routing (`glm-5.3` -> `glm-5.3-flash`), and token/latency observability. Redacts all authorization headers and credentials from logs.
  - `TaskPlanner`: Deterministic planning service converting natural-language engineering requests into strictly typed `TaskPlanSchema` objects. Enforces step limits (max 3), `execution_type="python"` restriction, code safety bounds, and artifact path safety.
  - `prompts.py`: Security-hardened prompt template incorporating prompt injection defense, sandboxing restrictions, and strict JSON output schemas.
* **`services/orchestration/`**:
  - `plan_integrity.py`: Cryptographic plan hashing. Computes canonical JSON serialization (key-sorted, compact delimiters, UTF-8 encoded) and SHA-256 digest (`plan_hash`). Ensures that any modification to plan steps, source code, capabilities, network mode, or artifacts changes the plan hash, guaranteeing tamper-evident binding across planning, policy evaluation, approval, and worker execution.
* **`services/policy/`**:
  - `DeterministicPolicyEngine`: Independent, non-LLM security enforcement engine (`blast_radius_zero_strict` v1.0.0). Validates proposed plans against 6 hard boundary rules:
    1. `SEC-001 (PermittedExecutionType)`: Strictly permits `execution_type="python"` only.
    2. `SEC-002 (StepCountBounds)`: Enforces non-empty step count within `settings.MAX_PLAN_STEPS` (default: 3).
    3. `SEC-003 (ZeroNetworkEnforcement)`: Strictly rejects plans requesting outbound network access (`network_required=True`).
    4. `SEC-004 (CapabilityAllowlist)`: Restricts requested capabilities to safe allowlist (`python_execution`, `math_computation`, `file_read`, `file_write`, `csv_processing`, `json_processing`, `data_analysis`, `text_processing`). Rejects forbidden capabilities (`host_filesystem`, `docker_socket`, `raw_socket`, `privileged_execution`, etc.).
    5. `SEC-005 (SourceCodeBounds)`: Enforces size limits (`MAX_SOURCE_INPUT_BYTES`) and checks for illegal control bytes (null bytes).
    6. `SEC-006 (ArtifactSafety)`: Validates filenames against path traversal, directory separators, hidden dotfiles, allowed extensions (`.csv`, `.json`, `.txt`, `.log`, `.md`, `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tsv`, `.html`), and batch count limits.
  - Generates immutable `PolicyEvaluationResult` bound to the canonical `plan_hash`.
* **`services/sandbox/`**: Abstract sandbox architecture with two concrete adapters:
  1. `BaseSandboxAdapter`: Common contract enforcing typed configuration, execution requests, process timeout bounds, and lifecycle cleanup.
  2. `MockSandboxAdapter`: Deterministic local development adapter for Windows/macOS. Explicitly marked with `execution_mode="mock"`. Never executes untrusted code on the host OS.
  3. `MicrosandboxAdapter`: Production driver using `microsandbox` SDK (0.7.13) via KVM on Vultr Cloud Compute (`AMD EPYC Turin`). Enforces `Network.none()`, captures independent guest kernel telemetry (`6.12.113`), and ensures context-managed microVM destruction.
  4. `SandboxManager`: Central orchestration service managing bounded concurrency (semaphore for 1 active microVM on the 2-vCPU host), policy validation, and lifecycle reporting.
* **`services/artifacts/`**:
  - `ArtifactManager`: Path traversal prevention, absolute path rejection, hidden dotfile blocking, symlink rejection, and SHA-256 calculation. Enforces strict limits: max 10 artifacts, max 5MB per artifact, max 20MB total, max 64KB Python source code.
* **`workers/`**: Single-worker background process claiming queued tasks using transactional row locking (`FOR UPDATE SKIP LOCKED`) to ensure exactly one microVM executes at a time on the 2 vCPU host.
* **`services/verification/`**: Evidence recorder compiling the cryptographic **Execution Receipt** (SHA-256 dataset hashes, guest kernel identity, stdout/stderr, artifact manifests, and microVM destruction verification).

### 2.2 Frontend Application (`frontend/`)
* **Next.js 14+ / React 18+ / TypeScript / Tailwind CSS**.
* **Clean, high-density infrastructure UI**:
  - Live execution terminal powered by Server-Sent Events (SSE).
  - Explicit plan breakdown with permission badges before execution approval.
  - Verifiable execution receipt viewer showing cryptographic hashes and sandbox lifecycle timestamps.
  - Containment demonstration panel showcasing real boundary-enforcement tests.

---

## 2.3 Task, Approval & Execution State Machine

PartProof enforces a strict state machine across the lifecycle of every audit task:

```
[ User Request ]
       |
       v
   (created) --------> (planning) --------> (awaiting_approval)
                           |                     |        |
                           v                     |        | (reject)
                       (failed)                  |        v
                                                 |   (rejected) [Terminal]
                                                 |
                                     (approve)   |
                                                 v
                                             (queued)
                                                 |
                                                 v
                                            (preparing)  <-- Worker Pick-Up (4C)
                                                 |
                                                 v
                                             (running)
                                                 |
                                                 v
                                            (verifying)
                                                 |
                                    +------------+------------+
                                    |                         |
                                    v                         v
                               (succeeded)                (failed)
                               [Terminal]                [Terminal]
```

### Cancellation Transitions
* **Pre-Execution** (`created`, `planning`, `awaiting_approval`): Transitions directly to `cancelled`. Any associated plan is marked `approval_status="cancelled"`.
* **Queued** (`queued`): Transitions task and execution atomically to `cancelled`. The background worker will skip this job.
* **In-Flight** (`preparing`, `running`, `verifying`): Transitions task and execution to `cancel_requested`. The worker signals cancellation to the sandbox adapter and records the final cancellation state once containment teardown is complete.
* **Terminal States** (`succeeded`, `failed`, `timed_out`, `rejected`): Cannot be cancelled; requests return `409 Conflict`.
* **Idempotency**: Repeated cancellation requests on `cancelled` or `cancel_requested` tasks return `200 OK` idempotently.

### Concurrency & Data Integrity
* **Row-Level Locking**: `SELECT ... FOR UPDATE OF tasks` guarantees mutual exclusion on task state transitions, eliminating race conditions during concurrent approval or cancellation requests.
* **Cryptographic Binding**: Approval re-computes `compute_plan_hash(plan_json)` and asserts equality against `plan_hash` before recording an approval or queuing an execution.
* **Plan Snapshot**: The queued `Execution` entity captures an immutable copy of `plan_snapshot` and `plan_hash` at the exact moment of approval, preventing post-approval modifications.
