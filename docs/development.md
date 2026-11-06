# PartProof Development Guide

## 1. Local Development Setup (Windows / macOS / Linux)

PartProof uses a dual-adapter pattern allowing rapid, complete end-to-end development locally without needing a local KVM hypervisor:
* **`SANDBOX_BACKEND=mock`**: Simulates microVM creation, execution, and artifact generation locally with strict safety boundaries.
* **`SANDBOX_BACKEND=microsandbox`**: Used exclusively on the Vultr Cloud Compute Ubuntu host with `/dev/kvm`.

### Prerequisites
* Python 3.12+
* Node.js 20+ & npm
* Git

### Backend Setup
```bash
# 1. Create and activate a Python virtual environment
cd backend
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp ../.env.example .env
# Set SANDBOX_BACKEND=mock for local development

# 4. Run database migrations
alembic upgrade head
# Or initialize tables directly in development:
python -m app.database.init_db

# 5. Start the FastAPI development server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup
```bash
# In a separate terminal:
cd frontend
npm install
npm run dev
# Access the dashboard at http://localhost:3000
```

---

## 2. Running Automated Tests

### Unit Tests (Local Windows / macOS / Linux)
Runs all core unit tests, including authentication, health checks, mock sandbox adapter, artifact manager, plan integrity hashing, deterministic policy engine, Vultr inference client, task planner, and task planning APIs:
```bash
# In backend virtual environment:
pytest backend/tests/unit backend/tests/test_health_and_auth.py -v
```

### Real Microsandbox Integration Test (Exclusively on Vultr Host)
The real integration test (`tests/integration/test_microsandbox_real.py`) launches actual microVMs via KVM, executes code, generates a CSV artifact, extracts it to the host, verifies network denial, and checks `msb ls` cleanup:
```bash
# On Vultr VM (partproof-sandbox-01 as linuxuser):
RUN_MICROSANDBOX_INTEGRATION=1 pytest backend/tests/integration/test_microsandbox_real.py -v
```

### Live Vultr Serverless Inference Integration Test
The live inference test (`tests/integration/test_vultr_inference_real.py`) tests direct connectivity to `https://api.vultrinference.com/v1`, requests a structured plan using `glm-5.3`, validates schema compliance, and verifies token/latency metadata. Clients are managed via asynchronous context managers (`async with VultrInferenceClient()`) to ensure deterministic closure before the event loop terminates:
```bash
# On Vultr VM or with VULTR_INFERENCE_API_KEY configured:
VULTR_INFERENCE_API_KEY="your-key" RUN_VULTR_INFERENCE_INTEGRATION=1 pytest backend/tests/integration/test_vultr_inference_real.py -v
```

### Isolated PostgreSQL Concurrency Integration Test
The PostgreSQL concurrency test (`tests/integration/test_postgres_concurrency.py`) verifies pessimistic row-level locking (`SELECT ... FOR UPDATE OF tasks`), idempotent duplicate approval handling, and rejection immutability against a real PostgreSQL instance:
* **Dedicated Test DB**: Requires `TEST_POSTGRES_DATABASE_URL` pointing to a database containing `test` (e.g. `partproof_test`). Targeting production `partproof_db` triggers an immediate safety failure.
* **Schema Provisioning**: Automatically executes actual Alembic migrations (`alembic upgrade head`) against the test database before test execution.
* **Session Isolation**: Dynamically overrides FastAPI's `get_db` dependency with an isolated async PostgreSQL session factory and restores original overrides after test completion.
* **Zero Production Secret Leakage**: Dynamically provisions isolated test users and JWT tokens; planning tests use local test doubles without calling live LLMs.

```bash
# Run PostgreSQL concurrency integration test (requires running PostgreSQL test DB):
TEST_POSTGRES_DATABASE_URL="postgresql+asyncpg://linuxuser:secret@localhost:5432/partproof_test" \
RUN_POSTGRES_TESTS=1 \
pytest backend/tests/integration/test_postgres_concurrency.py -v

# Run real Microsandbox worker multi-step integration test on Vultr VM (KVM):
RUN_MICROSANDBOX_WORKER_INTEGRATION=1 \
pytest backend/tests/integration/test_microsandbox_worker_real.py -v
```

### Running the Execution Worker

The worker daemon runs as an independent process from the FastAPI server:

```bash
# Run worker once (processes next queued execution and exits):
python -m app.workers.execution_worker --once

# Run worker continuously:
python -m app.workers.execution_worker
```

---

## 3. Production Deployment on Vultr Host
On the Vultr VM (`partproof-sandbox-01`, 207.148.105.25):
* User: `linuxuser`
* Backend runs natively with `SANDBOX_BACKEND=microsandbox`
* PostgreSQL runs via Docker Compose on `127.0.0.1:5432`
* Systemd manages FastAPI and Worker daemons (`infra/systemd/partproof-worker.service`):

```bash
sudo cp infra/systemd/partproof-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now partproof-worker
sudo systemctl status partproof-worker
```
