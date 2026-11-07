import json
import os
import tempfile
from typing import get_type_hints
import pytest

from app.core.config import Settings


def test_cors_origins_default_value():
    """Verify default CORS_ORIGINS when no environment override is present."""
    # Ensure env var is clean
    orig_val = os.environ.pop("CORS_ORIGINS", None)
    try:
        s = Settings()
        assert s.CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]
        assert isinstance(s.CORS_ORIGINS, list)
    finally:
        if orig_val is not None:
            os.environ["CORS_ORIGINS"] = orig_val


def test_cors_origins_type_annotation():
    """Verify CORS_ORIGINS is typed as List[str]."""
    hints = get_type_hints(Settings)
    assert hints["CORS_ORIGINS"] == list[str] or str(hints["CORS_ORIGINS"]) == "typing.List[str]"
    assert str(Settings.model_fields["CORS_ORIGINS"].annotation) in ("typing.List[str]", "list[str]")


def test_cors_origins_from_comma_separated_env(monkeypatch):
    """Verify comma-separated string with multiple origins from env var."""
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,https://app.partproof.io")
    s = Settings()
    assert s.CORS_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://app.partproof.io",
    ]


def test_cors_origins_from_comma_separated_env_with_whitespace(monkeypatch):
    """Verify comma-separated string with whitespace and trailing comma is cleaned properly."""
    monkeypatch.setenv("CORS_ORIGINS", "  http://localhost:3000 ,  http://127.0.0.1:3000 ,  ")
    s = Settings()
    assert s.CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_cors_origins_from_single_origin_env(monkeypatch):
    """Verify single origin without comma."""
    monkeypatch.setenv("CORS_ORIGINS", "https://app.partproof.io")
    s = Settings()
    assert s.CORS_ORIGINS == ["https://app.partproof.io"]


def test_cors_origins_from_json_array_env(monkeypatch):
    """Verify JSON array string format from env var."""
    json_val = json.dumps(["http://localhost:3000", "http://127.0.0.1:3000", "https://staging.partproof.io"])
    monkeypatch.setenv("CORS_ORIGINS", json_val)
    s = Settings()
    assert s.CORS_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://staging.partproof.io",
    ]


def test_cors_origins_from_empty_env(monkeypatch):
    """Verify empty string or whitespace-only results in empty list."""
    monkeypatch.setenv("CORS_ORIGINS", "")
    s = Settings()
    assert s.CORS_ORIGINS == []

    monkeypatch.setenv("CORS_ORIGINS", "   ")
    s2 = Settings()
    assert s2.CORS_ORIGINS == []

    monkeypatch.setenv("CORS_ORIGINS", "[]")
    s3 = Settings()
    assert s3.CORS_ORIGINS == []


def test_cors_origins_from_dotenv_comma_separated():
    """Verify loading from .env file with comma-separated format matching .env.example."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".env") as f:
        f.write("CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000\n")
        f_path = f.name

    try:
        class FileSettings(Settings):
            model_config = {**Settings.model_config, "env_file": f_path}

        s = FileSettings()
        assert s.CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)


def test_cors_origins_from_dotenv_json_array():
    """Verify loading from .env file with JSON array format."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".env") as f:
        f.write('CORS_ORIGINS=["http://localhost:3000", "http://127.0.0.1:3000"]\n')
        f_path = f.name

    try:
        class FileSettings(Settings):
            model_config = {**Settings.model_config, "env_file": f_path}

        s = FileSettings()
        assert s.CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)


def test_other_list_settings_json_decoding_preserved(monkeypatch):
    """
    Ensure other list-valued settings (e.g. SANDBOX_ALLOWED_IMAGES) are NOT broken
    and still undergo standard JSON decoding from environment variables.
    """
    custom_images = ["custom-python:3.12", "custom-node:20"]
    monkeypatch.setenv("SANDBOX_ALLOWED_IMAGES", json.dumps(custom_images))
    s = Settings()
    assert s.SANDBOX_ALLOWED_IMAGES == custom_images


def test_cors_origins_fallback_when_nodecode_is_none(monkeypatch):
    """
    Verify fallback behavior if NoDecode is unavailable in an older pydantic-settings version.
    """
    import app.core.config as config_mod

    monkeypatch.setattr(config_mod, "NoDecode", None)

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".env") as f:
        f.write("CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000\n")
        f_path = f.name

    try:
        class FallbackSettings(Settings):
            model_config = {**Settings.model_config, "env_file": f_path}

        s = FallbackSettings()
        assert s.CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)

