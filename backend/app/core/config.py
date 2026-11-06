import os
import platform
import uuid
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET_KEYS = {
    "development-insecure-secret-key-32-chars-min-needed-here!",
    "change-this-in-production-use-a-secure-random-64-char-string",
    "secret",
    "changeme",
}

INSECURE_DEFAULT_DEMO_PASSWORDS = {
    "PartProofSecureDemo2026!",
    "password",
    "admin",
    "demo",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment & Host
    PARTPROOF_ENV: str = Field(default="development", description="development | staging | production")
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=True)
    SECRET_KEY: str = Field(default="development-insecure-secret-key-32-chars-min-needed-here!")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60 * 24)  # 24 hours

    # Vultr Serverless Inference
    VULTR_INFERENCE_BASE_URL: str = Field(default="https://api.vultrinference.com/v1")
    VULTR_INFERENCE_API_KEY: str = Field(default="")
    VULTR_INFERENCE_MODEL: str = Field(default="glm-5.3")
    VULTR_INFERENCE_FALLBACK_MODEL: str = Field(default="glm-5.3-flash")
    VULTR_INFERENCE_TIMEOUT_SECONDS: int = Field(default=60)
    VULTR_INFERENCE_MAX_RETRIES: int = Field(default=3)
    VULTR_INFERENCE_TEMPERATURE: float = Field(default=0.1)

    # Planner Bounds
    MAX_PLAN_STEPS: int = Field(default=3)

    # Sandbox Isolation Configuration
    SANDBOX_BACKEND: str = Field(default="mock", description="'mock' for local dev, 'microsandbox' for Vultr host")
    SANDBOX_DEFAULT_IMAGE: str = Field(default="python:3.12-slim")
    SANDBOX_ALLOWED_IMAGES: List[str] = Field(default=["python:3.12-slim", "python:3.11-slim"])
    SANDBOX_MAX_CONCURRENT: int = Field(default=1)
    SANDBOX_DEFAULT_TIMEOUT_SECONDS: int = Field(default=30)
    SANDBOX_MAX_TIMEOUT_SECONDS: int = Field(default=120)
    SANDBOX_DEFAULT_CPUS: int = Field(default=1)
    SANDBOX_MAX_CPUS: int = Field(default=1)
    SANDBOX_DEFAULT_MEMORY_MB: int = Field(default=512)
    SANDBOX_MAX_MEMORY_MB: int = Field(default=1024)
    SANDBOX_DEFAULT_NETWORK: str = Field(default="none")
    SANDBOX_CLEANUP_TIMEOUT_SECONDS: float = Field(default=15.0)

    # Distributed Worker Configuration
    WORKER_ID: str = Field(default_factory=lambda: f"worker-{uuid.uuid4().hex[:8]}")
    WORKER_POLL_INTERVAL_SECONDS: float = Field(default=2.0)
    WORKER_LEASE_DURATION_SECONDS: int = Field(default=60)
    WORKER_HEARTBEAT_INTERVAL_SECONDS: float = Field(default=15.0)
    WORKER_MAX_ATTEMPTS: int = Field(default=3)
    WORKER_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS: float = Field(default=15.0)
    WORKER_LOCK_FILE_PATH: str = Field(default="/tmp/partproof_worker.lock")

    # Database
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./partproof.db")

    # Artifacts & Storage
    ARTIFACT_STORAGE_DIR: str = Field(default="./partproof_artifacts")
    MAX_ARTIFACTS_PER_EXECUTION: int = Field(default=10)
    MAX_ARTIFACT_SIZE_BYTES: int = Field(default=5 * 1024 * 1024)  # 5 MB
    MAX_TOTAL_ARTIFACT_BYTES: int = Field(default=20 * 1024 * 1024)  # 20 MB
    MAX_SOURCE_INPUT_BYTES: int = Field(default=64 * 1024)  # 64 KB

    # Demo Credentials
    DEMO_USER_EMAIL: str = Field(default="auditor@partproof.io")
    DEMO_USER_PASSWORD: str = Field(default="PartProofSecureDemo2026!")

    # CORS
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000", "http://127.0.0.1:3000"])

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    def validate_production_invariants(self):
        """Hard safety invariants for production environment."""
        if self.PARTPROOF_ENV == "production":
            if self.SANDBOX_BACKEND == "mock":
                raise RuntimeError(
                    "CRITICAL SECURITY INVARIANT VIOLATION: "
                    "PartProof cannot run in production mode with SANDBOX_BACKEND='mock'. "
                    "Hardware-isolated Microsandbox is mandatory for production."
                )
            if self.DEBUG is True:
                raise RuntimeError(
                    "CRITICAL SECURITY INVARIANT VIOLATION: "
                    "DEBUG must be False in production."
                )
            if len(self.SECRET_KEY) < 32 or self.SECRET_KEY in INSECURE_DEFAULT_SECRET_KEYS:
                raise RuntimeError(
                    "CRITICAL SECURITY INVARIANT VIOLATION: "
                    "A secure, randomly generated SECRET_KEY (minimum 32 characters) is mandatory in production. "
                    "The development default key was rejected."
                )
            if self.DEMO_USER_PASSWORD in INSECURE_DEFAULT_DEMO_PASSWORDS:
                raise RuntimeError(
                    "CRITICAL SECURITY INVARIANT VIOLATION: "
                    "Default predictable demo user password is not permitted in production."
                )

    def validate_worker_production_invariants(self):
        """Hard safety invariants for worker execution."""
        if self.PARTPROOF_ENV == "production":
            self.validate_production_invariants()
            if "sqlite" in self.DATABASE_URL.lower():
                raise RuntimeError(
                    "CRITICAL SECURITY INVARIANT VIOLATION: "
                    "Production worker requires PostgreSQL (SKIP LOCKED support); SQLite is forbidden in production."
                )
            if self.SANDBOX_BACKEND != "microsandbox":
                raise RuntimeError(
                    "CRITICAL SECURITY INVARIANT VIOLATION: "
                    "Production worker requires SANDBOX_BACKEND='microsandbox'."
                )
            if platform.system() != "Linux":
                raise RuntimeError(
                    "CRITICAL SECURITY INVARIANT VIOLATION: "
                    "Production worker with Microsandbox must run on Linux."
                )
            if not os.path.exists("/dev/kvm"):
                raise RuntimeError(
                    "CRITICAL SECURITY INVARIANT VIOLATION: "
                    "Production worker requires /dev/kvm for hardware-assisted virtualization."
                )


settings = Settings()
