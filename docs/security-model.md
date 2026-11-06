# PartProof Security Model & Implementation Controls

## 1. Core Principles
1. **Zero-Trust Autonomous Execution**: Untrusted code is never executed directly on the host operating system.
2. **Least Privilege**: The control plane runs as unprivileged user `linuxuser`. Neither the API nor the sandboxes run as root.
3. **Defense in Depth**: Isolation is enforced at the hypervisor level (KVM microVMs), network stack (isolated/none), and application level (deterministic policy engine).
4. **Deterministic Policy Validation**: LLMs are creative planners, not security controllers. The deterministic policy engine validates plans against fixed system invariants before dispatch.

---

## 2. Hard Isolation Controls

### 2.1 Hardware-Assisted Virtualization (KVM + libkrun)
* Unlike standard Docker containers which share the host Linux kernel (`6.8.0-147-generic`), each PartProof sandbox executes within a `libkrun` microVM with its own dedicated guest kernel (`6.12.113`).
* Even if an execution payload manages to achieve root access inside the guest (`UID 0` in microVM), it is confined to the guest virtualization boundary and cannot compromise the host kernel.

### 2.2 Network Boundary Enforcement
* Default policy: `Network.none()`.
* Outbound connections receive immediate rejection (`[Errno 111] Connection refused`).
* No network interface bridging to host private networks or Docker subnets.

### 2.3 Secret Management & Segregation
* The Vultr Serverless Inference API Key is stored strictly within the host `.env` file and read by the FastAPI process.
* Secrets are never passed to the guest environment or stored in persistent database fields exposed to the frontend.
* Logs automatically redact authorization headers and credential patterns.

### 2.4 Lifecycle Management & Guaranteed Cleanup
```python
## 3. Artifact Security & Path Traversal Prevention
* **Directory Isolation**: Artifacts are written strictly to `{ARTIFACT_STORAGE_DIR}/{task_id}/{execution_id}/`.
* **Path Validation**: Filenames containing `/`, `\`, `..`, null bytes, control characters, or absolute path patterns are rejected with an explicit `ArtifactCollectionError`.
* **Symlink Traversal Prevention**: Host-side file registration explicitly inspects `source_path.is_symlink()` and rejects symlinks or non-regular files to eliminate container-escape tricks via host mount symlinks.
* **Volume Limits**: Hard maximums enforced: 10 artifacts per execution, 5 MB maximum single artifact size, 20 MB maximum total per execution, and 64 KB source code length limit.
* **Cryptographic Hashing**: Streaming SHA-256 calculation for every collected artifact, providing tamper-evident receipts.

---

## 4. Execution Policy & Timeout Controls
* **Deterministic Policy Engine (`DeterministicPolicyEngine`)**:
  - Independent security gate enforcing system invariants regardless of LLM generation.
  - Policy version: `blast_radius_zero_strict` v1.0.0.
  - Rules enforced:
    - `SEC-001`: Python runtime only; blocks shells or unmanaged interpreters.
    - `SEC-002`: Bounded step counts (1 to 3 steps).
    - `SEC-003`: Hard zero network (`Network.none()`), rejecting outbound network requests.
    - `SEC-004`: Capability allowlist (`file_read`, `file_write`, `math_computation`, `csv_processing`, `json_processing`, `data_analysis`, `text_processing`, `python_execution`). Explicitly denies dangerous system capabilities (`host_filesystem`, `docker_socket`, `raw_socket`, `ssh_access`, `root_access`, `cloud_api`).
    - `SEC-005`: Source code size bounds (<= 64KB) and binary null-byte injection detection.
    - `SEC-006`: Artifact name safety, path traversal checks, and whitelisted extensions.
* **Cryptographic Plan Binding & Approval Gate**:
  - Every plan is serialized into canonical JSON and hashed with SHA-256 (`plan_hash`).
  - The plan hash is bound to the `TaskPlan`, the `PolicyEvaluationResult`, the user's `Approval` record (`approved_plan_hash`), and the worker `Execution` record (`plan_hash` and `plan_snapshot`).
  - **Approval-Time Re-evaluation**: At the moment of approval (`POST /api/v1/tasks/{task_id}/approve`), the backend recomputes the SHA-256 hash of `task_plan.plan_json` to detect any database tampering, and runs `DeterministicPolicyEngine.evaluate()` fresh against current security rules. Any discrepancy halts execution immediately with an unprocessable entity or conflict response.
  - **Rejection Immutability**: If a plan is marked `rejected`, it can never be approved in a subsequent request. Re-submitting an approval for a rejected plan raises `409 Conflict`.
  - **TOCTOU Elimination**: When an approval is recorded, the full approved plan structure is serialized into `Execution.plan_snapshot` alongside `Execution.plan_hash`. The worker executes strictly against this immutable snapshot, eliminating time-of-check-to-time-of-use exploits.
  - **Plan Overwrite Defense**: The `POST /api/v1/tasks/{task_id}/plan` endpoint is strictly guarded: once a plan is approved or an execution record exists, regeneration is blocked with `409 Conflict`. Pessimistic row locking (`with_for_update(of=Task)`) eliminates race conditions between simultaneous plan regeneration and approval dispatch. When a plan is rejected, regeneration is permitted to produce an alternative plan with a distinct canonical hash, while all prior approval/rejection audit records remain immutable in the database.
  - **Concurrency Protection**: Task row-locking (`with_for_update()`) ensures that parallel approval requests cannot race to queue multiple duplicate executions. Idempotency guarantees safe retries from UI or network dropped connections.

* **Worker Pre-Execution 12-Point Defense-in-Depth Verification (`SecurityExecutionValidator`)**:
  Before any microVM is provisioned or code executed, the worker re-validates 12 mandatory security criteria:
  1. Execution state is strictly `queued` or `preparing`.
  2. Associated `Approval` record exists and decision is `approved`.
  3. `Approval.approved_plan_hash` matches `Execution.plan_hash`.
  4. `Execution.plan_snapshot` is present and valid dictionary.
  5. `plan_snapshot` parses successfully into `TaskPlanSchema`.
  6. Recomputed SHA-256 hash of `plan_snapshot` matches `Execution.plan_hash`.
  7. Deterministic policy evaluation returns `allowed == True` with zero violations.
  8. Step count is bounded within 1 to 3 steps.
  9. All execution types are strictly `python`.
  10. Zero-network enforcement (`network_mode == "none"` and `network_required is False`).
  11. Runtime image is in allowlist (`SANDBOX_ALLOWED_IMAGES`).
  12. Resource bounds (CPU <= 1, Memory <= 1024MB, Timeout <= 120s) and artifact filename safety.

* **Sandbox Reliability & Teardown Integrity**:
  - `BaseSandboxAdapter.__aexit__`: Preserves and chains exceptions: if code execution failed and teardown failed, the cleanup exception chains from the execution error (`cleanup_exc from exec_val`). If execution succeeded but teardown failed, `cleanup_exc` is raised.
  - `MicrosandboxAdapter.destroy()`: Sets `_is_destroyed = True` *only* after confirmed destruction. If destruction raises, `_is_destroyed` remains `False` so cleanup can be retried.
  - **Missing Artifact Enforcement**: Missing declared expected artifacts raise `ArtifactCollectionError` and transition the execution to `failed`. Artifact errors are never silently swallowed.
* **Database & Concurrency Isolation**:
  - PostgreSQL integration tests run against a dedicated, isolated test database (`TEST_POSTGRES_DATABASE_URL`). Production database names (`partproof_db`) are hard-blocked by automated guardrails.
  - Schema migrations run through actual Alembic revisions (`alembic upgrade head`) to mirror production DDL and index constraints.
  - Test authentication utilizes dynamically seeded, isolated test credentials rather than production tokens.
* **Hardware Quotas**: Enforced via backend policy validation before microVM creation (1 vCPU, 512 MB memory, max 30s default timeout, max 120s limit).
* **Process Killing**: SDK timeout mechanism kills processes if their deadline elapses, returning exit code 124 and capturing timeout telemetry.
* **Local Development Safety**: The `MockSandboxAdapter` never executes untrusted code on the Windows host. It uses deterministic fixtures and marks all outputs with `execution_mode="mock"`.
---

## 5. Cognitive Plane Security & Prompt Hardening
* **Inference Credential Isolation**: The Vultr Serverless Inference API key resides exclusively in host memory (`VULTR_INFERENCE_API_KEY`). It is never passed into the sandbox microVM, never returned in API responses, and automatically redacted from application logs.
* **Prompt Injection Defense**: User task descriptions are treated as untrusted data payloads. System prompts explicitly instruct the model to ignore attempts to leak credentials, override system rules, or run unrestricted commands.
* **Schema Gating**: The backend never executes raw LLM strings. Output is parsed as JSON, strictly validated against `TaskPlanSchema`, checked for step limits (max 3), execution types (strictly `python`), and safe artifact filenames via `ArtifactManager`.
* **Planning / Execution Decoupling**: Planning never triggers code execution. After successful planning, the task enters `awaiting_approval` and waits for explicit user authorization.

---

## 6. Production Invariants & Configuration Hardening
* **Secret Key Enforcement**: In production (`PARTPROOF_ENV="production"`), `SECRET_KEY` must be a high-entropy custom secret (>= 32 characters). Known development defaults are hard-rejected at startup.
* **Debug Guardrail**: `DEBUG` must be False in production.
* **Demo Password Guardrail**: Default predictable demo passwords are prohibited in production.
* **Sandbox Enforcement**: `SANDBOX_BACKEND="mock"` is strictly forbidden in production.
