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
# Context-managed lifecycle ensures destruction even on exceptions:
async with await Sandbox.create(
    sandbox_id,
    image="python:3.12-slim",
    cpus=1,
    memory=512,
    network=Network.none(),
    replace=True
) as sandbox:
    result = await sandbox.exec("python", ["-c", sanitized_code])
# MicroVM immediately destroyed upon exiting context block
```
* After task completion or timeout, the sandbox manager confirms cleanup.
* The execution receipt records the cleanup verification status.
