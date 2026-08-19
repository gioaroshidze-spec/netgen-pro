import io
import json
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, text


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
PYTHON = Path(sys.executable)
BASELINE = "0001_phase3_baseline"


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


def test_baseline_revision_is_an_explicit_immutable_snapshot():
    source = (
        BACKEND / "alembic/versions/0001_phase3_baseline.py"
    ).read_text(encoding="utf-8")
    assert "import models" not in source
    assert "metadata.create_all" not in source
    assert "op.create_table" in source
    assert "op.create_index" in source


def test_current_head_is_discovered_separately_from_baseline(monkeypatch):
    import migration_state

    class FakeScripts:
        def get_current_head(self):
            return "0099_future_head"

    monkeypatch.setattr(
        migration_state.ScriptDirectory,
        "from_config",
        lambda config: FakeScripts(),
    )
    assert migration_state.BASELINE_REVISION == BASELINE
    assert migration_state.get_current_migration_head() == "0099_future_head"


def test_baseline_accepts_a_later_migration_exactly_once(tmp_path):
    scripts = tmp_path / "alembic"
    versions = scripts / "versions"
    versions.mkdir(parents=True)
    shutil.copy(
        BACKEND / "alembic/versions/0001_phase3_baseline.py",
        versions / "0001_phase3_baseline.py",
    )
    (scripts / "env.py").write_text(
        """
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
engine = engine_from_config(
    config.get_section(config.config_ini_section) or {},
    prefix="sqlalchemy.",
    poolclass=pool.NullPool,
)
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (versions / "0002_future_probe.py").write_text(
        """
from alembic import op
import sqlalchemy as sa

revision = "0002_future_probe"
down_revision = "0001_phase3_baseline"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "future_migration_probe",
        sa.Column("id", sa.Integer(), primary_key=True),
    )

def downgrade():
    op.drop_table("future_migration_probe")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    database = tmp_path / "forward.db"
    config = Config()
    config.set_main_option("script_location", str(scripts))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")

    command.upgrade(config, BASELINE)
    engine = create_engine(f"sqlite:///{database}")
    assert "future_migration_probe" not in inspect(engine).get_table_names()

    command.upgrade(config, "head")
    assert "future_migration_probe" in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0002_future_probe"
    engine.dispose()


def test_readiness_compares_database_revision_to_dynamic_head(monkeypatch):
    from routers import system

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for table_name in ("users", "network_devices", "scheduled_jobs"):
            connection.execute(text(f"CREATE TABLE {table_name} (id INTEGER)"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('0001_phase3_baseline')")
        )
    monkeypatch.setattr(system, "engine", engine)
    monkeypatch.setattr(system, "is_production", lambda: True)
    monkeypatch.setattr(system, "get_current_migration_head", lambda: "0002_future")

    result = system.readiness_snapshot()
    assert result["status"] == "not_ready"
    assert "expected head '0002_future'" in result["detail"]
    engine.dispose()


def test_image_metadata_cannot_be_falsified_by_release_tag(tmp_path, monkeypatch):
    import runtime_config

    metadata_file = tmp_path / "vnms_build_metadata.json"
    metadata_file.write_text(
        json.dumps(
            {
                "version": "0.4.1-image",
                "build_sha": "image-sha",
                "build_time": "2026-08-19T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "IMAGE_BUILD_METADATA", metadata_file)
    monkeypatch.setenv("VNMS_RELEASE_TAG", "9.9.9-host")
    monkeypatch.setenv("VNMS_VERSION", "8.8.8-host")
    assert runtime_config.build_metadata()["version"] == "0.4.1-image"


def test_ai_provider_config_supports_root_style_secret_file(tmp_path, monkeypatch):
    from runtime_config import ConfigurationError, ai_provider_config

    key_file = tmp_path / "ai_api_key"
    key_file.write_text("FAKE_AI_KEY_TEST", encoding="utf-8")
    monkeypatch.setenv("ACTIVE_AI_MODEL", "provider/test-model")
    monkeypatch.setenv("VNMS_AI_API_KEY_FILE", str(key_file))
    assert ai_provider_config() == ("provider/test-model", "FAKE_AI_KEY_TEST")

    monkeypatch.delenv("ACTIVE_AI_MODEL")
    monkeypatch.setenv("VNMS_ENV", "production")
    with pytest.raises(ConfigurationError, match="AI generation is not configured"):
        ai_provider_config()


def test_json_redaction_and_update_log_in_support_bundle(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    for directory in ("backend", "ansible", "frontend"):
        (log_root / directory).mkdir(parents=True)
    sentinels = (
        '{"password": "FAKE_JSON_PASSWORD_TEST"}\n'
        "{'token':'FAKE_JSON_TOKEN_TEST'}\n"
        '{"api_key": "FAKE_JSON_API_KEY_TEST"}\n'
        '{"authorization": "Bearer SUPER_SECRET_SUPPORT_TEST"}\n'
        "password = SUPER_SECRET_SUPPORT_TEST\n"
    )
    (log_root / "update.log").write_text(
        "update start requested=0.4.1 previous=0.4.0\n" + sentinels,
        encoding="utf-8",
    )
    monkeypatch.setenv("VNMS_LOG_DIR", str(log_root))

    from support_bundle import build_support_bundle

    bundle = build_support_bundle([])
    for sentinel in (
        b"FAKE_JSON_PASSWORD_TEST",
        b"FAKE_JSON_TOKEN_TEST",
        b"FAKE_JSON_API_KEY_TEST",
        b"SUPER_SECRET_SUPPORT_TEST",
    ):
        assert sentinel not in bundle
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert "logs/update.log" in archive.namelist()
        contents = b"".join(archive.read(name) for name in archive.namelist())
    assert b"update start requested=0.4.1 previous=0.4.0" in contents
    assert b"[REDACTED]" in contents
    assert b"FAKE_JSON_PASSWORD_TEST" not in contents


def test_real_backend_exception_reaches_redacted_support_bundle(tmp_path):
    database = tmp_path / "exception.db"
    log_root = tmp_path / "logs"
    env = {
        "VNMS_ENV": "production",
        "VNMS_DATABASE_URL": f"sqlite:///{database}",
        "VNMS_LOG_DIR": str(log_root),
        "JWT_SECRET_KEY": "fake-production-jwt",
        "VNMS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }
    code = r"""
import io
import logging
import zipfile
from fastapi.testclient import TestClient
from migration_manager import upgrade

upgrade()
import main

@main.app.get("/test-only-controlled-exception")
async def controlled_exception():
    raise RuntimeError(
        "CONTROLLED_BACKEND_EXCEPTION password=SUPER_SECRET_SUPPORT_TEST"
    )

with TestClient(main.app, raise_server_exceptions=False) as client:
    response = client.get("/test-only-controlled-exception")
    assert response.status_code == 500

for handler in logging.getLogger().handlers:
    handler.flush()

from support_bundle import build_support_bundle
bundle = build_support_bundle([])
assert b"SUPER_SECRET_SUPPORT_TEST" not in bundle
with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
    contents = b"".join(archive.read(name) for name in archive.namelist())
assert b"CONTROLLED_BACKEND_EXCEPTION" in contents
assert b"SUPER_SECRET_SUPPORT_TEST" not in contents
assert b"[REDACTED]" in contents
"""
    result = run_backend(code, env=env, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_update_script_has_manifest_and_failure_rollback_controls():
    update = (ROOT / "deploy/update.sh").read_text(encoding="utf-8")
    assert "deployment manifest install outcome=success" in update
    assert "restore_deployment_file" in update
    assert "rollback outcome=success health=passed" in update
    assert "VNMS_UPDATE_FAILURE_INJECTION" in update
    assert "VNMS_UPDATE_RUNNING_COPY" in update
    assert "VNMS_RELEASE_TAG" in update
    assert "VNMS_VERSION=" not in update
