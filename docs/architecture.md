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
* **`services/inference/`**: Vultr Serverless Inference client using an OpenAI-compatible async interface. Enforces structured JSON output parsing (`TaskPlanSchema`), latency tracking, and error handling.
* **`services/policy/`**: Deterministic policy validator. Assesses requested capabilities, enforces maximum memory/CPU quotas, confirms network mode is `none`, and flags tasks requiring explicit user approval.
* **`services/sandbox/`**: Abstract sandbox interface with two concrete adapters:
  1. `MockSandboxAdapter`: Deterministic, secure local simulator used on Windows/macOS for rapid development. Explicitly flagged as simulated.
  2. `MicrosandboxAdapter`: Direct driver for `microsandbox` SDK (v0.7.13) on Vultr Linux host using `/dev/kvm`.
* **`workers/`**: Single-worker background process claiming queued tasks using transactional row locking (`FOR UPDATE SKIP LOCKED`) to ensure exactly one microVM executes at a time on the 2 vCPU host.
* **`services/verification/`**: Evidence recorder compiling the cryptographic **Execution Receipt** (SHA-256 dataset hashes, guest kernel identity, stdout/stderr, artifact manifests, and microVM destruction verification).

### 2.2 Frontend Application (`frontend/`)
* **Next.js 14+ / React 18+ / TypeScript / Tailwind CSS**.
* **Clean, high-density infrastructure UI**:
  - Live execution terminal powered by Server-Sent Events (SSE).
  - Explicit plan breakdown with permission badges before execution approval.
  - Verifiable execution receipt viewer showing cryptographic hashes and sandbox lifecycle timestamps.
  - Containment demonstration panel showcasing real boundary-enforcement tests.
