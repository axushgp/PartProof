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

# 4. Run database migrations or initialize tables
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

## 2. Running Tests
```bash
cd backend
pytest -v
```

---

## 3. Production Deployment on Vultr Host
On the Vultr VM (`partproof-sandbox-01`, 207.148.105.25):
* User: `linuxuser`
* Backend runs natively with `SANDBOX_BACKEND=microsandbox`
* PostgreSQL runs via Docker Compose on `127.0.0.1:5432`
* Systemd manages FastAPI and Worker daemons
