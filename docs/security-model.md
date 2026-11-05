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
* **Hardware Quotas**: Enforced via backend policy validation before microVM creation (1 vCPU, 512 MB memory, max 30s default timeout, max 120s limit).
* **Process Killing**: SDK timeout mechanism kills processes if their deadline elapses, returning exit code 124 and capturing timeout telemetry.
* **Local Development Safety**: The `MockSandboxAdapter` never executes untrusted code on the Windows host. It uses deterministic fixtures and marks all outputs with `execution_mode="mock"`.
* **Production Guardrail**: The system strictly refuses to run `MockSandboxAdapter` in production (`PARTPROOF_ENV="production"`).
