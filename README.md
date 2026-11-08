# PartProof

> **Autonomous Procurement Forensics, Engineering Task Planning & Isolated MicroVM Execution Engine**

PartProof is an industrial-grade procurement intelligence and verified computation platform. It audits complex engineering bills of materials (BOMs), investigates supplier quotations, exposes hidden landed-cost discrepancies, and executes computational tasks within hardware-isolated microVMs—producing cryptographically signed, independently verifiable execution receipts.

---

## Table of Contents

- [Overview & Problem Statement](#overview--problem-statement)
- [Core Capabilities](#core-capabilities)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Procurement Forensics & Landed Cost Engine](#procurement-forensics--landed-cost-engine)
- [Security & Containment Model](#security--containment-model)
- [Supported Formats & Operational Limits](#supported-formats--operational-limits)
- [API Reference](#api-reference)
- [Installation & Local Development](#installation--local-development)
- [Environment Configuration](#environment-configuration)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [Production Deployment](#production-deployment)

---

## Overview & Problem Statement

Engineering and manufacturing organizations lose up to 15% of direct material budgets to invisible procurement discrepancies buried across 40+ page quotations, nested spreadsheets, and conflicting commercial terms. Traditional procurement workflows suffer from three structural failures:

1. **Headline Quote Deception**: A supplier may offer a lower unit price on primary parts but impose punitive Minimum Order Quantities (MOQs), unbudgeted freight terms (EXW vs. DDP), and mandatory tooling or NRE fees.
2. **Manual Reconciliation Bottlenecks**: Auditing 500+ line items across multiple competing quotes requires hours of error-prone manual spreadsheet checks, leading to missed specification or revision mismatches.
3. **The Unsafe Agent Problem**: Standard LLM agents cannot be trusted for financial math (due to floating-point rounding errors and hallucinations) and cannot safely execute code on host infrastructure without exposing networks, credentials, and host files.

### The PartProof Solution

PartProof establishes a zero-trust pipeline separating **probabilistic reasoning** from **deterministic calculation** and **untrusted code execution**:

- **AI Document Interpretation**: High-throughput extraction and plan synthesis powered by Vultr Serverless Inference (`GLM-5.3` with automatic failover to `GLM-5.3-flash`).
- **Deterministic Financial Engine**: Exact arithmetic via Python `Decimal` (`ROUND_HALF_UP`) evaluating 14 automated discrepancy rules and calculating true landed costs.
- **Interactive Decision Replay**: Real-time counterfactual simulation allowing engineers to model supplier negotiations (waived MOQs, adjusted freight, price cuts) before committing capital.
- **Hypervisor-Level MicroVM Isolation**: MicroSandbox microVMs booted via Linux KVM with hardware virtualization, dedicated guest kernels, and zero network access (`Network.none()`).
- **Cryptographic Evidence Trail**: RFC 8785 JSON Canonicalization Scheme (JCS) and Ed25519 digital signatures binding task parameters, plan hashes, microVM specs, and output artifact hashes into an immutable execution receipt.

---

## Core Capabilities

| Capability | Technical Mechanism | Benefit |
|---|---|---|
| **Multi-Source Ingestion** | Extract BOMs and quotations from digital PDF, Excel (`.xlsx`, `.xls`), CSV, and JSON. | Eliminates manual copy-pasting across disparate vendor documents. |
| **14-Rule Forensics** | Rule-based discrepancy analysis checking price variances, MOQ penalties, revision codes, and Incoterms. | Surfaces hidden procurement traps and revision mismatches in seconds. |
| **True Landed Cost** | Deterministic pre-tax, tax, freight, and excess capital calculation using exact Decimal arithmetic. | Reverses headline quote deception by revealing the true total cost of ownership. |
| **Decision Replay** | Counterfactual simulation engine with reactive state updates. | Enables interactive "what-if" negotiation analysis before issuing purchase orders. |
| **AI Task Planning** | Translates natural-language objectives into bounded, typed Python execution steps (max 3 steps). | Eliminates prompt injection risks while producing transparent, inspectable code. |
| **Human-in-the-Loop Gate** | Mandatory plan approval with immutable SHA-256 plan hash locking. | Prevents unvetted autonomous code execution; nothing runs without explicit approval. |
| **MicroVM Sandboxing** | Linux KVM guest isolation (`python:3.12-slim`), read-only input mounting, zero network egress. | Guarantees blast-radius-zero execution for generated scripts. |
| **Verifiable Receipts** | RFC 8785 JCS canonicalization with Ed25519 digital signature. | Provides tamper-evident audit evidence verifiable in-browser or offline via OpenSSL. |
| **Authenticated Artifacts** | Task-scoped streaming downloads with real-time SHA-256 integrity verification. | Prevents path traversal and guarantees file authenticity before download. |

---

## System Architecture

PartProof is built as a connected five-layer architecture enforcing strict separation of concerns:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          1. PRESENTATION & DASHBOARD                            │
│           Next.js 16 (App Router) • React 19 • TypeScript • Tailwind CSS         │
│  BFF Route Handlers • Secure HttpOnly Cookies • Web Crypto Receipt Verification │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ JSON over HTTPS / SSE
┌────────────────────────────────────────▼────────────────────────────────────────┐
│                             2. SECURE CONTROL PLANE                             │
│                  FastAPI (Python 3.12) • Pydantic v2 • SQLAlchemy 2.0           │
│       PostgreSQL (AsyncPG / SKIP LOCKED) • Deterministic Policy Engine (14 Rules)│
└──────────────────┬──────────────────────────────────────────────┬───────────────┘
                   │                                              │
┌──────────────────▼──────────────────┐        ┌──────────────────▼───────────────┐
│     3. AI INFERENCE ENGINE          │        │      4. ISOLATED EXECUTION       │
│  Vultr Serverless Inference         │        │  Persistent Execution Worker     │
│  Primary: GLM-5.3 (low reasoning)   │        │  MicroSandbox MicroVMs via KVM   │
│  Fallback: GLM-5.3-flash (5xx/tout) │        │  Hardware Virtualization (Linux) │
│  SDK max_retries=0 • 8192 Tokens    │        │  Read-only /workspace/input/     │
│  Zero Host Credential Leakage       │        │  Network: None • 512MB RAM Capped│
└─────────────────────────────────────┘        └──────────────────┬───────────────┘
                                                                  │
┌─────────────────────────────────────────────────────────────────▼───────────────┐
│                         5. TRUST & EVIDENCE LAYER                               │
│     RFC 8785 JSON Canonicalization (JCS) • Ed25519 Cryptographic Signatures      │
│     SHA-256 Artifact Digests • Open-File-Descriptor Path Security Verification   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### The 7-Stage Execution Lifecycle

1. **Upload & Ingestion**: Digital BOM and multi-supplier quotations are uploaded; SHA-256 manifests are generated.
2. **Document Extraction**: Text streams are extracted and normalized into structured JSON schemas.
3. **Forensic Investigation**: The 14-rule discrepancy engine inspects part numbers, quantities, MOQs, and commercial clauses.
4. **Deterministic Calculation**: Landed costs are computed with exact Decimal arithmetic; ranking reversals are identified.
5. **Decision Replay & Task Creation**: Engineers test negotiation scenarios and commit a reconciled procurement plan.
6. **Isolated MicroVM Execution**: The worker launches an isolated microVM, executes the generated Python script, verifies output artifacts, and destroys the sandbox.
7. **Cryptographic Verification**: An Ed25519-signed execution receipt is generated, binding the plan hash, microVM specs, and artifact hashes.

---

## Technology Stack

| Layer | Technologies | Rationale |
|---|---|---|
| **Frontend** | Next.js 16.4, React 19, TypeScript, Tailwind CSS, TanStack Query 5 | High-performance dashboard with Backend-for-Frontend (BFF) proxy and HttpOnly cookie security. |
| **Backend API** | FastAPI 0.115, Pydantic v2, Python 3.12, Uvicorn | Async ASGI control plane with strict schema validation and high-throughput concurrency. |
| **Database** | PostgreSQL 16 (production), SQLite via `aiosqlite` (local development) | AsyncPG connection pooling with pessimistic row locking (`SKIP LOCKED`) for worker queues. |
| **AI Inference** | Vultr Serverless Inference (`GLM-5.3`, `GLM-5.3-flash`) | OpenAI-compatible serverless inference endpoint with bounded retries and fast reasoning. |
| **MicroVM Isolation** | MicroSandbox (`msb 0.7.13`), Linux KVM, `libkrun` | True hardware virtualization with dedicated guest kernel (`6.12.113`) and zero host attack surface. |
| **Cryptography** | RFC 8785 (`rfc8785`), Ed25519 (`cryptography`), SHA-256 | Deterministic JSON canonicalization and asymmetric digital signatures for tamper-evident audit trails. |
| **Document Parsers** | `pdfplumber`, `pypdf`, `openpyxl`, `csv` | Native digital text stream extraction from PDFs, Excel sheets, and CSVs. |

---

## Procurement Forensics & Landed Cost Engine

### The 14 Discrepancy Rules

PartProof evaluates every BOM line item against competing supplier quotations using 14 rules categorized by severity:

| Rule Code | Rule Description | Severity | Example Detection |
|---|---|---|---|
| `RULE-001` | **Unit Price Variance** | `WARNING` | Supplier unit price varies by >5% from baseline or lowest quote. |
| `RULE-002` | **Missing Line Item** | `CRITICAL` | Required BOM part number was omitted from supplier quotation. |
| `RULE-003` | **Quantity Mismatch** | `CRITICAL` | Quoted quantity deviates from engineering BOM requirement. |
| `RULE-004` | **MOQ Penalty** | `WARNING` | Supplier MOQ exceeds BOM demand, causing dead inventory and tied-up capital. |
| `RULE-005` | **Calculation Error** | `CRITICAL` | Supplier extended price does not equal unit price $\times$ quantity. |
| `RULE-006` | **Currency Mismatch** | `WARNING` | Quotation currency differs from BOM standard (e.g. EUR vs. USD). |
| `RULE-007` | **Revision Code Mismatch** | `CRITICAL` | Supplier quoted older Revision C when engineering BOM mandates Revision D. |
| `RULE-008` | **Specification Variance** | `WARNING` | Quoted component material, tolerance, or rating differs from BOM notes. |
| `RULE-009` | **Incoterms Shift** | `WARNING` | Supplier quoted EXW (buyer pays freight) instead of required DDP. |
| `RULE-010` | **Validity Risk** | `INFO` | Quotation expiration date is less than 30 days out. |
| `RULE-011` | **Lead Time Risk** | `WARNING` | Quoted lead time exceeds project manufacturing schedule. |
| `RULE-012` | **Payment Terms Risk** | `WARNING` | Supplier demands 100% advance deposit rather than Net 30/60 terms. |
| `RULE-013` | **Compliance Missing** | `CRITICAL` | Required ISO 9001, AS9100, or RoHS certifications not verified. |
| `RULE-014` | **Tooling / NRE Fee** | `INFO` | Additional non-recurring engineering or setup charge identified. |

### True Landed Cost Formulation

Headline quotes regularly hide thousands of dollars in commercial overhead. PartProof calculates landed costs with exact Decimal arithmetic:

$$\text{Pre-Tax Total} = \sum (\text{Required Qty} \times \text{Unit Price}) + \text{MOQ Excess Cost} + \text{Freight} + \text{Tooling/NRE}$$

$$\text{Tax Amount} = \text{Pre-Tax Total} \times \text{Tax Rate}$$

$$\mathbf{\text{True Landed Cost}} = \text{Pre-Tax Total} + \text{Tax Amount}$$

#### Verified Benchmark Example:
- **Supplier A (Apex)**: Headline quote **\$25,680.00** + \$2,920.00 MOQ excess + \$1,850.00 EXW freight = \$30,450.00 pre-tax. At 18% GST (\$5,481.00), the **true landed cost is \$35,931.00**.
- **Supplier B (Beacon)**: Headline quote **\$27,948.00** + \$0 MOQ + \$0 freight (DDP) = \$27,948.00 pre-tax. At 18% GST (\$5,030.64), the **true landed cost is \$32,978.64**.
- **Financial Finding**: Supplier B saves **\$2,952.36 (8.2%)** net cash despite having a \$2,268.00 higher headline quote.

---

## Security & Containment Model

PartProof implements defense-in-depth across six distinct containment boundaries:

| Security Domain | Implementation | Security Guarantee |
|---|---|---|
| **Hypervisor Boundary** | KVM microVM (`SANDBOX_BACKEND=microsandbox`) | Hardware-level memory isolation. Dedicated guest kernel (`6.12.113`) prevents kernel-sharing container escapes. |
| **Network Egress** | `Network.none()` via `iptables` drop | Guest microVM has no external IP, no gateway, and cannot initiate outbound socket connections. |
| **Credential Isolation** | Environment variable filtering | Host secrets (`VULTR_INFERENCE_API_KEY`, `DATABASE_URL`, `SECRET_KEY`) reside exclusively in host memory and are never mounted into microVMs. |
| **Input Staging** | Read-only `/workspace/input/` mount | Inputs are staged read-only via 9p filesystem. Staged file SHA-256 hashes must match the approved plan manifest. |
| **Output Jailing** | `/workspace/output/` directory restriction | MicroVM code can only persist files to `/workspace/output/`. File paths outside this mount are purged on VM destruction. |
| **Execution Authority** | Cryptographic plan hash approval | No worker executes any task without an approved `TaskPlan` signed with the exact SHA-256 hash of the plan schema. |

---

## Supported Formats & Operational Limits

### Supported Document Types

| Ingestion Category | Formats | Processing Method | Limitations / Boundaries |
|---|---|---|---|
| **Engineering BOMs** | `.csv`, `.xlsx`, `.xls`, `.json` | Deterministic column mapping & validation. | File size limit: 5 MB. Maximum 5,000 line items per BOM. |
| **Supplier Quotes** | `.pdf`, `.csv`, `.xlsx`, `.xls`, `.json` | Text-stream extraction via `pdfplumber` / `openpyxl`. | **Digital native PDFs only.** Scanned image-only PDFs trigger an explicit warning (heuristic OCR is rejected to prevent number hallucinations). |

### Sandbox Operational Bounds

- **Execution Steps**: Maximum 3 steps per plan (`MAX_PLAN_STEPS=3`).
- **CPU Quota**: Default 1 vCPU, Maximum 1 vCPU (`SANDBOX_MAX_CPUS=1`).
- **Memory Quota**: Default 512 MB, Maximum 1024 MB (`SANDBOX_MAX_MEMORY_MB=1024`).
- **Execution Timeout**: Default 30s, Maximum 120s (`SANDBOX_MAX_TIMEOUT_SECONDS=120`).
- **Total Artifact Cap**: Maximum 10 files or 20 MB total per execution.

---

## API Reference

All backend API routes are prefixed with `/api/v1`. Authentication uses standard `Bearer <JWT>` headers or secure HttpOnly session cookies.

### Authentication (`/api/v1/auth`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Register a new user with email and password. |
| `POST` | `/auth/login` | Authenticate credentials and receive JWT access token. |
| `POST` | `/auth/logout` | Invalidate current session and clear session cookie. |
| `GET` | `/auth/me` | Retrieve profile of currently authenticated user. |

### Procurement Intelligence (`/api/v1/procurement`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/procurement/extract` | Upload BOM and quotes; extract normalized line items. |
| `POST` | `/procurement/reconcile` | Run 14-rule discrepancy audit and compute landed costs. |
| `POST` | `/procurement/replay` | Simulate counterfactual price, MOQ, and freight terms. |
| `POST` | `/procurement/create-task` | Generate deterministic Python audit script and enqueue task. |
| `GET` | `/procurement/demo` | Retrieve pre-loaded EV powertrain benchmark dataset. |

### Task Lifecycle & Planning (`/api/v1/tasks`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/tasks` | List all tasks owned by current user. |
| `POST` | `/tasks` | Create task and generate AI execution plan. |
| `GET` | `/tasks/{task_id}` | Fetch full task details, plan, execution logs, and artifacts. |
| `POST` | `/tasks/{task_id}/plan` | Regenerate plan if previously rejected. |
| `POST` | `/tasks/{task_id}/approve` | Formally approve or reject plan (approved enqueues worker). |
| `POST` | `/tasks/{task_id}/cancel` | Cancel an in-flight or awaiting task. |
| `GET` | `/tasks/{task_id}/artifacts/{id}/download` | Stream authenticated artifact with integrity verification. |

### System & Health (`/api/v1/system`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Basic liveness check for load balancers. |
| `GET` | `/system/status` | Detailed status of database, worker, and storage subsystem. |
| `GET` | `/system/inference` | Connectivity and latency check for Vultr Serverless Inference. |

---

## Installation & Local Development

### Prerequisites

- **Python**: Version 3.12 or newer
- **Node.js**: Version 20 or newer (Node 22 recommended)
- **Database**: SQLite (built-in default) or PostgreSQL 15+
- **Virtualization**: Linux KVM required for hardware microVMs; Windows/macOS supported via `SANDBOX_BACKEND=mock`.

### 1. Clone Repository

```bash
git clone https://github.com/axushgp/PartProof.git
cd PartProof
```

### 2. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment file
cp ../.env.example .env

# Run database migrations
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend Setup

In a separate terminal:

```bash
cd frontend

# Install Node dependencies
npm install

# Start Next.js development server
npm run dev
```

Visit `http://localhost:3000` to access the PartProof dashboard.

### 4. Running the Execution Worker

The persistent worker polls PostgreSQL/SQLite for approved execution leases:

```bash
cd backend
# Run a single execution pass and exit:
python -m app.workers.execution_worker --once

# Or run the worker continuously:
python -m app.workers.execution_worker
```

---

## Environment Configuration

Configure the following variables in `.env` (backend) or `.env.local` (frontend):

### Backend Settings (`backend/.env`)

```ini
# Environment Mode: development | staging | production
PARTPROOF_ENV=development

# Server Host & Port
HOST=0.0.0.0
PORT=8000
DEBUG=true

# Security (Generate a secure 64-char key in production: openssl rand -hex 32)
SECRET_KEY=development-insecure-secret-key-32-chars-min-needed-here!
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Vultr Serverless Inference Configuration
VULTR_INFERENCE_BASE_URL=https://api.vultrinference.com/v1
VULTR_INFERENCE_API_KEY=your_vultr_api_key_here
VULTR_INFERENCE_MODEL=glm-5.3
VULTR_INFERENCE_FALLBACK_MODEL=glm-5.3-flash
VULTR_INFERENCE_TIMEOUT_SECONDS=60
VULTR_INFERENCE_MAX_RETRIES=3
VULTR_INFERENCE_MAX_COMPLETION_TOKENS=8192
VULTR_INFERENCE_REASONING_EFFORT=low
VULTR_INFERENCE_TEMPERATURE=0.1

# Sandbox Isolation (use 'mock' locally, 'microsandbox' on Linux with /dev/kvm)
SANDBOX_BACKEND=mock
SANDBOX_DEFAULT_IMAGE=python:3.12-slim
SANDBOX_MAX_CONCURRENT=1
SANDBOX_DEFAULT_TIMEOUT_SECONDS=30
SANDBOX_MAX_TIMEOUT_SECONDS=120
SANDBOX_DEFAULT_CPUS=1
SANDBOX_DEFAULT_MEMORY_MB=512
SANDBOX_DEFAULT_NETWORK=none

# Database URL
# Local SQLite:
DATABASE_URL=sqlite+aiosqlite:///./partproof.db
# Production PostgreSQL:
# DATABASE_URL=postgresql+asyncpg://partproof:password@localhost:5432/partproof_db

# Cryptographic Receipt Signing (Ed25519)
RECEIPT_KEY_ID=partproof-ed25519-v1
# Provide 32-byte hex key or path to PEM key file:
# RECEIPT_SIGNING_KEY=your_ed25519_private_key_hex
# RECEIPT_SIGNING_KEY_PATH=/etc/partproof/receipt_key.pem

# Storage Directory for Generated Artifacts
ARTIFACT_STORAGE_DIR=./partproof_artifacts

# CORS Allowed Origins
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

### Frontend Settings (`frontend/.env.local`)

```ini
NEXT_PUBLIC_APP_URL=http://localhost:3000
PARTPROOF_API_URL=http://127.0.0.1:8000
```

---

## Testing & Quality Assurance

PartProof maintains a comprehensive test suite covering unit logic, cryptographic proofs, and end-to-end API workflows.

### Backend Test Suite

```bash
cd backend
source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows

# Run all 200+ unit tests
pytest tests/unit -v

# Run targeted inference and client tests
pytest tests/unit/test_inference_client.py tests/unit/test_planner.py -v

# Run live Vultr inference diagnostic (requires live API key)
RUN_VULTR_INFERENCE_INTEGRATION=1 \
VULTR_INFERENCE_API_KEY="your_api_key" \
pytest tests/integration/test_vultr_inference_real.py -v
```

### Frontend Test Suite

```bash
cd frontend

# Run Vitest unit & component tests
npm test

# Run TypeScript static type checking
npm run typecheck

# Run ESLint validation
npm run lint

# Execute production build verification
npm run build
```

---

## Production Deployment

### Production Hardening Invariants

When `PARTPROOF_ENV=production`, PartProof enforces strict security invariants at boot time:

- `DEBUG` must be set to `False`.
- `SECRET_KEY` must be a high-entropy string of at least 32 characters.
- `SANDBOX_BACKEND` must be set to `microsandbox` with `/dev/kvm` accessible.
- `DATABASE_URL` must point to PostgreSQL (`sqlite` is strictly forbidden).
- `RECEIPT_SIGNING_KEY` or `RECEIPT_SIGNING_KEY_PATH` must be configured.
- Dedicated non-root service users must run the FastAPI API and execution worker.

### Systemd Service Configuration

On a hardened Ubuntu 24.04 server with KVM enabled:

```ini
# /etc/systemd/system/partproof-api.service
[Unit]
Description=PartProof FastAPI Control Plane
After=network.target postgresql.service

[Service]
Type=simple
User=partproof
WorkingDirectory=/opt/partproof/backend
ExecStart=/opt/partproof/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
EnvironmentFile=/opt/partproof/backend/.env

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/partproof-worker.service
[Unit]
Description=PartProof MicroSandbox Worker Daemon
After=network.target postgresql.service

[Service]
Type=simple
User=partproof
WorkingDirectory=/opt/partproof/backend
ExecStart=/opt/partproof/backend/.venv/bin/python -m app.workers.execution_worker
Restart=always
EnvironmentFile=/opt/partproof/backend/.env

[Install]
WantedBy=multi-user.target
```

---

## License

This project is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.
