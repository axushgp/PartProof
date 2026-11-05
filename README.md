# PartProof

> **Autonomous Engineering Task & Procurement Auditor with Blast Radius Zero**
> Built for the **Vultr Agent Rush Hackathon** (Challenge 1: Blast Radius Zero)

---

## 🎯 What is PartProof?

**PartProof** is an AI-powered agent execution platform designed for high-risk computational workflows—such as auditing engineering bills of materials (BOMs), analyzing supplier quotations, and verifying calculations—without exposing the host infrastructure.

Every task follows a zero-trust lifecycle:
1. **Natural Language Task Ingestion**: The user describes the engineering audit or data analysis.
2. **AI Task Planning**: Vultr Serverless Inference (`glm-5.3`) produces a structured, typed execution plan.
3. **Deterministic Policy Gating**: The policy engine validates execution parameters, enforces quotas (1 vCPU, 512MB RAM, timeout), and confirms zero network access (`Network.none()`).
4. **Explicit User Approval**: The user reviews the plan and requested capabilities before execution.
5. **Isolated MicroVM Execution**: The task runs inside a dedicated, hardware-isolated Microsandbox microVM on Vultr Cloud Compute via KVM.
6. **Verifiable Execution Receipt**: Generates a cryptographic evidence report with SHA-256 artifact hashes, stdout/stderr logs, and microVM destruction verification.

---

## 🏛️ Architecture & Tech Stack

* **Host & Infrastructure**: Vultr Cloud Compute (VX1 Dedicated CPU, Ubuntu 24.04 LTS, AMD EPYC Turin, `/dev/kvm`).
* **Cognitive Plane**: Vultr Serverless Inference (`https://api.vultrinference.com/v1`, `glm-5.3`).
* **Isolation Boundary**: Microsandbox (`msb 0.7.13`, Python SDK `0.7.13`, `libkrun` microVM with dedicated guest kernel `6.12.113`).
* **Control Plane / Backend**: FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.x (async), Alembic, PostgreSQL.
* **Frontend Dashboard**: Next.js 14, React 18, TypeScript, Tailwind CSS, Server-Sent Events (SSE).

---

## 🔒 Security Guarantees & Containment
* **Zero Network Access**: Sandboxes run strictly with `Network.none()`.
* **Zero Host Credentials**: The Vultr API keys and database credentials reside exclusively in the host memory space and are never passed into microVMs.
* **Independent Guest Kernel**: MicroVMs boot an isolated guest kernel (`6.12.113`), preventing host kernel namespace escapes.
* **Guaranteed Ephemerality**: Sandboxes are context-managed and immediately destroyed post-execution.

---

## 🚀 Quick Start
See [docs/development.md](docs/development.md) for full local setup and testing instructions.
