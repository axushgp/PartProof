import os
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        """Hard safety invariant: Production environment MUST NOT run with mock sandbox."""
        if self.PARTPROOF_ENV == "production" and self.SANDBOX_BACKEND == "mock":
            raise RuntimeError(
                "CRITICAL SECURITY INVARIANT VIOLATION: "
                "PartProof cannot run in production mode with SANDBOX_BACKEND='mock'. "
                "Hardware-isolated Microsandbox is mandatory for production."
            )


settings = Settings()
