"""Bounded, redacted Support Bundle v2 generation."""

from __future__ import annotations

import io
import json
import os
import platform
import re
import subprocess
import sys
import time
import zipfile
import urllib.request
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from sqlalchemy import inspect, text

from database import engine
from routers.system import readiness_snapshot
from runtime_config import build_metadata, log_dir


MAX_FILE_BYTES = 512 * 1024
MAX_BUNDLE_INPUT_BYTES = 5 * 1024 * 1024
SECRET_KEY_NAMES = (
    r"password|token|secret|api[_-]?key|apikey|authorization|"
    r"jwt_secret_key|vnms_encryption_key"
)
JSON_SECRET_PATTERN = re.compile(
    rf"""(?i)(["'](?:{SECRET_KEY_NAMES})["']\s*:\s*)(["'])([^\r\n]*?)(\2)"""
)
REDACTION_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(
        rf"""(?i)(\b(?:{SECRET_KEY_NAMES})\s*=\s*)"""
        r"""(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;&]+)"""
    ),
    re.compile(
        rf"(?i)(\b(?:{SECRET_KEY_NAMES})\s*:\s*)[^\s,;]+"
    ),
    re.compile(r"(?i)([?&]token=)[^\s&#]+"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/-]+"),
]


def redact_text(value: str) -> str:
    redacted = JSON_SECRET_PATTERN.sub(
        lambda match: (
            f"{match.group(1)}{match.group(2)}[REDACTED]{match.group(4)}"
        ),
        value,
    )
    for pattern in REDACTION_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1)}[REDACTED]",
            redacted,
        )
    return redacted


def _json_bytes(value) -> bytes:
    return redact_text(json.dumps(value, indent=2, default=str)).encode("utf-8")


def _tail(path: Path, maximum: int = MAX_FILE_BYTES) -> bytes:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > maximum:
                handle.seek(-maximum, os.SEEK_END)
            raw = handle.read(maximum)
    except OSError:
        return b"Log file is unavailable.\n"
    return redact_text(raw.decode("utf-8", errors="replace")).encode("utf-8")


def _command(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=5, check=False,
            env={"PATH": os.getenv("PATH", "")},
        )
        return redact_text((result.stdout or result.stderr or "No output.")[:MAX_FILE_BYTES])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Unavailable: {type(exc).__name__}\n"


def _frontend_health() -> dict:
    url = os.getenv("VNMS_FRONTEND_HEALTH_URL")
    if not url:
        return {"status": "not_configured"}
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return {"status": "ok" if response.status == 200 else "error", "http_status": response.status}
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}



def _migration_revision() -> str:
    try:
        with engine.connect() as connection:
            if "alembic_version" not in inspect(connection).get_table_names():
                return "not stamped"
            return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none())
    except Exception:
        return "unavailable"


def _dependency_summary() -> str:
    names = ["ansible", "ansible-core", "paramiko", "ansible-pylibssh", "scp", "sqlalchemy", "fastapi"]
    lines = []
    for name in names:
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            version = "not installed in API interpreter"
        lines.append(f"{name}={version}")
    return "\n".join(lines) + "\n"


def _log_candidates() -> list[tuple[str, Path]]:
    base = log_dir()
    if not base:
        return [
            ("logs/backend.log", Path("backend_app.log")),
            ("logs/ansible.log", Path("ansible.log")),
            ("logs/update.log", Path("update.log")),
        ]
    backend_primary = base / "backend" / "backend_app.log"
    ansible_primary = base / "ansible" / "ansible.log"
    candidates = [
        ("logs/backend.log", backend_primary),
        ("logs/ansible.log", ansible_primary),
        ("logs/update.log", base / "update.log"),
    ]
    rotated_groups = (
        ("backend", sorted((base / "backend").glob("backend_app.log.*"))[:3]),
        ("ansible", sorted((base / "ansible").glob("ansible.log.*"))[:3]),
        ("update", sorted(base.glob("update.log.*"))[:3]),
    )
    for log_name, paths in rotated_groups:
        for index, path in enumerate(paths, start=1):
            candidates.append((f"logs/{log_name}.log.{index}", path))
    candidates.extend([
        ("logs/nginx-access.log", base / "frontend" / "access.log"),
        ("logs/nginx-error.log", base / "frontend" / "error.log"),
    ])
    return candidates


def build_support_bundle(frontend_logs: list[dict] | None = None) -> bytes:
    from scheduler_engine import scheduler

    utc_now = datetime.now(timezone.utc)
    manifest = {
        "format": "VNMS Support Bundle v2",
        "created_at": utc_now.isoformat(),
        "handling_notice": "Redaction is best-effort. This bundle contains operational metadata and must be handled as sensitive.",
        "excluded": ["environment", "database", "configuration archives", "credentials", "private keys"],
        "maximum_input_bytes": MAX_BUNDLE_INPUT_BYTES,
    }
    scheduler_state = {
        "running": bool(getattr(scheduler, "running", False)),
        "scheduled_job_count": len(scheduler.get_jobs()) if getattr(scheduler, "running", False) else 0,
    }
    timezone_data = {
        "utc_timestamp": utc_now.isoformat(),
        "timezone_names": list(time.tzname),
        "utc_offset_seconds": -time.timezone,
    }
    entries: dict[str, bytes] = {
        "manifest.json": _json_bytes(manifest),
        "version.json": _json_bytes(build_metadata()),
        "health.json": _json_bytes({"backend": readiness_snapshot(), "frontend": _frontend_health()}),
        "logs/frontend-browser.log": _json_bytes((frontend_logs or [])[-100:]),
        "runtime/migration.json": _json_bytes({"revision": _migration_revision()}),
        "runtime/python-version.txt": (platform.python_version() + "\n").encode(),
        "runtime/ansible-version.txt": _command(["ansible", "--version"]).encode(),
        "runtime/ansible-collections.txt": _command(["ansible-galaxy", "collection", "list"]).encode(),
        "runtime/dependency-summary.txt": _dependency_summary().encode(),
        "runtime/scheduler-status.json": _json_bytes(scheduler_state),
        "runtime/timezone.json": _json_bytes(timezone_data),
    }
    consumed = sum(len(value) for value in entries.values())
    for archive_name, path in _log_candidates():
        if consumed >= MAX_BUNDLE_INPUT_BYTES:
            break
        content = _tail(path, min(MAX_FILE_BYTES, MAX_BUNDLE_INPUT_BYTES - consumed))
        entries[archive_name] = content
        consumed += len(content)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()
