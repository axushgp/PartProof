from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class RuleResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    rule_name: str
    passed: bool
    message: str
    severity: str = Field(default="error", description="'error' | 'warning' | 'info'")
    details: Optional[Dict[str, Any]] = None


# Allowlist of safe capabilities for isolated Python microVM execution
PERMITTED_CAPABILITIES = {
    "python_execution",
    "math_computation",
    "file_read",
    "file_write",
    "csv_processing",
    "json_processing",
    "data_analysis",
    "text_processing",
}

# Explicitly forbidden capabilities that represent boundary violation attempts
FORBIDDEN_CAPABILITIES = {
    "network_access",
    "internet_access",
    "host_filesystem",
    "docker_socket",
    "ssh_access",
    "root_access",
    "system_admin",
    "privileged_execution",
    "secret_access",
    "cloud_api",
    "raw_socket",
    "process_spawn_unrestricted",
}

# Permitted artifact extensions for audit reports and data extraction
PERMITTED_ARTIFACT_EXTENSIONS = {
    ".csv",
    ".json",
    ".txt",
    ".log",
    ".md",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tsv",
    ".html",
}
