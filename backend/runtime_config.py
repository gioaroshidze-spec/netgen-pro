"""Environment-aware VNMS runtime configuration helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path


PRODUCTION = "production"
IMAGE_BUILD_METADATA = Path(__file__).with_name("vnms_build_metadata.json")


class ConfigurationError(RuntimeError):
    """Raised when required production configuration is absent or invalid."""


def environment() -> str:
    return os.getenv("VNMS_ENV", "development").strip().lower() or "development"


def is_production() -> bool:
    return environment() == PRODUCTION


def read_secret(name: str, *, required_in_production: bool = False) -> str | None:
    """Read a secret from NAME or NAME_FILE without logging its value."""
    direct = os.getenv(name)
    file_name = os.getenv(f"{name}_FILE")
    if direct is not None and file_name:
        raise ConfigurationError(
            f"Configure only one of {name} or {name}_FILE, not both."
        )
    value = direct
    if file_name:
        path = Path(file_name)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to read {name} from configured secret file {path}."
            ) from exc
    if value:
        return value
    if required_in_production and is_production():
        raise ConfigurationError(
            f"Production requires {name} or {name}_FILE to contain a value."
        )
    return None


def database_url() -> str:
    return os.getenv("VNMS_DATABASE_URL", "sqlite:///./netgen.db")


def log_dir() -> Path | None:
    configured = os.getenv("VNMS_LOG_DIR")
    return Path(configured) if configured else None


def archive_dir() -> Path:
    return Path(os.getenv("VNMS_ARCHIVE_DIR", "archive"))


def ai_provider_config() -> tuple[str, str | None]:
    """Return the LiteLLM model/key pair without exposing the key."""
    model = os.getenv("ACTIVE_AI_MODEL", "").strip()
    api_key = read_secret("VNMS_AI_API_KEY")
    if not is_production():
        return model or "claude-opus-4-7", api_key
    if not model or not api_key:
        raise ConfigurationError(
            "AI generation is not configured. Set ACTIVE_AI_MODEL and provision "
            "VNMS_AI_API_KEY_FILE using the production installer."
        )
    return model, api_key


def build_metadata() -> dict[str, str]:
    """Prefer the immutable metadata file baked into a production image."""
    try:
        parsed = json.loads(IMAGE_BUILD_METADATA.read_text(encoding="utf-8"))
        if set(parsed) == {"version", "build_sha", "build_time"} and all(
            isinstance(value, str) and value for value in parsed.values()
        ):
            return parsed
    except (OSError, ValueError, TypeError):
        pass
    return {
        "version": os.getenv("VNMS_VERSION", "0.0.0-dev"),
        "build_sha": os.getenv("VNMS_BUILD_SHA", "unknown"),
        "build_time": os.getenv("VNMS_BUILD_TIME", "unknown"),
    }
