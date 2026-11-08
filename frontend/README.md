# PartProof Frontend Console

Deterministic AI Task Planning, Policy Validation, and MicroVM Execution Platform.

## Runtime & Node.js Alignment

- **Target LTS Runtime**: Node.js 26 (Active LTS target declared in `.nvmrc`)
- **Minimum Supported Runtime**: Node.js `>=22.0.0` (Maintenance LTS engine constraint declared in `package.json`)
- **Package Manager**: npm `>=10.0.0`

To use the recommended Node version:
```bash
nvm use
```

## Quick Start

### 1. Install Dependencies
```bash
npm install
```

### 2. Configure Environment
Copy `.env.example` to `.env.local` (or configure required environment variables):
```env
BACKEND_INTERNAL_URL=http://127.0.0.1:8000
NEXT_PUBLIC_APP_ENV=production
```

### 3. Run Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the application.

## Quality & Verification Commands

```bash
# Typecheck
npm run typecheck

# Linting
npm run lint

# Unit & Component Tests (Vitest)
npm run test:unit

# End-to-End & Accessibility Tests (Playwright)
npm run test:e2e

# Production Build
npm run build
```

## Architecture & Security Model

- **Next.js 16 (App Router)** with React 19.
- **BFF (Backend-For-Frontend) Architecture**: All client requests route through secure Next.js API route proxies (`/api/*`), attaching `HttpOnly`, `SameSite=Lax` session cookies. Raw backend tokens and internal URLs are never exposed to client-side code.
- **Strict Authorization & Integrity Controls**:
  - Deterministic policy enforcement before approval.
  - Full 64-character canonical SHA-256 plan hash comparison.
  - Strict boolean cryptographic execution receipt verification (`security_verified === true`).
  - Quarantine state for orphaned sandboxes requiring host reconciliation (`needs_reconciliation`).
  - Zero demo credentials or bypass buttons in production code.
