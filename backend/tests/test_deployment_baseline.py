import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet


BACKEND = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


def run_backend(code, *, env=None, check=True):
    process_env = os.environ.copy()
    process_env.update(env or {})
    process_env["PYTHONPATH"] = str(BACKEND)
    return subprocess.run(
        [str(PYTHON), "-c", code],
        cwd=BACKEND,
        env=process_env,
        text=True,
        capture_output=True,
        check=check,
    )


@pytest.mark.parametrize("missing", ["JWT_SECRET_KEY", "VNMS_ENCRYPTION_KEY"])
def test_production_rejects_missing_required_secret(missing):
    env = {
        "VNMS_ENV": "production",
        "JWT_SECRET_KEY": "fake-jwt-for-test",
        "VNMS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }
    env.pop(missing)
    env.pop(f"{missing}_FILE", None)
    result = run_backend("import routers.auth", env=env, check=False)
    assert result.returncode != 0
    assert missing in result.stderr
    assert "fake-jwt-for-test" not in result.stderr


def test_development_fallback_is_explicit_and_does_not_log_value():
    result = run_backend(
        "import routers.auth",
        env={"VNMS_ENV": "development", "JWT_SECRET_KEY": "", "VNMS_ENCRYPTION_KEY": ""},
    )
    combined = result.stdout + result.stderr
    assert "ephemeral development key" in combined
    assert "legacy development compatibility key" in combined
    assert "uO1v_Zt5" not in combined


def test_version_and_health_metadata_are_safe(monkeypatch):
    monkeypatch.setenv("VNMS_VERSION", "0.4.0-test")
    monkeypatch.setenv("VNMS_BUILD_SHA", "abc123")
    monkeypatch.setenv("VNMS_BUILD_TIME", "2026-08-14T12:00:00Z")
    monkeypatch.setenv("JWT_SECRET_KEY", "FAKE_JWT_SUPPORT_TEST")
    from routers.system import live, readiness_snapshot, version

    assert version() == {
        "version": "0.4.0-test",
        "build_sha": "abc123",
        "build_time": "2026-08-14T12:00:00Z",
    }
    assert "FAKE_JWT_SUPPORT_TEST" not in json.dumps(version())
    assert live()["status"] == "alive"
    assert readiness_snapshot()["status"] == "ready"


def test_fresh_migration_and_idempotent_bootstrap(tmp_path):
    database = tmp_path / "fresh.db"
    password_file = tmp_path / "bootstrap"
    password_file.write_text("A-strong-test-password-123!", encoding="utf-8")
    key = Fernet.generate_key().decode()
    env = {
        "VNMS_ENV": "production",
        "VNMS_DATABASE_URL": f"sqlite:///{database}",
        "JWT_SECRET_KEY": "fake-production-jwt",
        "VNMS_ENCRYPTION_KEY": key,
        "VNMS_BOOTSTRAP_PASSWORD_FILE": str(password_file),
    }
    code = """
from migration_manager import upgrade
upgrade()
from bootstrap_admin import bootstrap_admin
assert bootstrap_admin('first-admin', 'A-strong-test-password-123!') is True
assert bootstrap_admin('second-admin', 'Different-strong-password-123!') is False
from database import SessionLocal
import models
db = SessionLocal()
users = db.query(models.User).all()
assert len(users) == 1
assert users[0].username == 'first-admin'
assert users[0].hashed_password != 'A-strong-test-password-123!'
assert users[0].requires_password_change is True
db.close()
"""
    run_backend(code, env=env)
    raw = database.read_bytes()
    assert b"A-strong-test-password-123!" not in raw
    assert b"admin/admin" not in raw


def test_existing_database_requires_backup_then_validates_and_stamps(tmp_path):
    database = tmp_path / "existing.db"
    backup = tmp_path / "verified-backup.db"
    env = {"VNMS_DATABASE_URL": f"sqlite:///{database}", "VNMS_ENV": "development"}
    result = run_backend(
        "import models; from database import engine; models.Base.metadata.create_all(engine); "
        "from migration_manager import upgrade; upgrade()",
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "--existing-backup" in result.stderr
    backup.write_bytes(database.read_bytes())
    run_backend(
        f"from migration_manager import upgrade; upgrade({str(backup)!r}); "
        "from database import engine; from sqlalchemy import text; "
        "c=engine.connect(); assert c.execute(text('select version_num from alembic_version')).scalar_one() == '0001_phase3_baseline'; c.close()",
        env=env,
    )


def test_support_bundle_is_bounded_complete_and_redacted(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    for directory in ("backend", "ansible", "frontend"):
        (log_root / directory).mkdir(parents=True)
    sentinel_text = (
        "Authorization: Bearer SUPER_SECRET_SUPPORT_TEST\n"
        "GET /ws/cli/1?token=FAKE_JWT_SUPPORT_TEST HTTP/1.1\n"
        "api_key=FAKE_API_KEY_SUPPORT_TEST\n"
    )
    (log_root / "backend" / "backend_app.log").write_text(sentinel_text, encoding="utf-8")
    (log_root / "ansible" / "ansible.log").write_text("password=SUPER_SECRET_SUPPORT_TEST", encoding="utf-8")
    (log_root / "frontend" / "access.log").write_text(sentinel_text, encoding="utf-8")
    (log_root / "frontend" / "error.log").write_text("safe error", encoding="utf-8")
    monkeypatch.setenv("VNMS_LOG_DIR", str(log_root))

    from support_bundle import MAX_BUNDLE_INPUT_BYTES, build_support_bundle

    bundle = build_support_bundle([{"time": "now", "error": "secret=SUPER_SECRET_SUPPORT_TEST"}])
    assert len(bundle) < MAX_BUNDLE_INPUT_BYTES
    assert b"SUPER_SECRET_SUPPORT_TEST" not in bundle
    assert b"FAKE_JWT_SUPPORT_TEST" not in bundle
    assert b"FAKE_API_KEY_SUPPORT_TEST" not in bundle
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "version.json", "health.json"}.issubset(names)
        assert "logs/backend.log" in names
        assert "logs/ansible.log" in names
        assert "logs/nginx-access.log" in names
        assert "logs/frontend-browser.log" in names
        assert "runtime/migration.json" in names
        assert not any(name.endswith(".db") or "archive/" in name for name in names)
        uncompressed = b"".join(archive.read(name) for name in names)
    assert b"[REDACTED]" in uncompressed
    assert b"SUPER_SECRET_SUPPORT_TEST" not in uncompressed
