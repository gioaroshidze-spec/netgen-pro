import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import rollback_service
from change_control import proposal_hash
from database import Base
from rollback_service import (
    RollbackRejected,
    authorize_rollback,
    prepare_manual_restore,
    verify_manual_restore,
)
from routers import configuration


SECRET_CONFIG = "username admin secret SUPER_SECRET_TEST"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    Base.metadata.create_all(engine)
    yield session
    session.close()


def _setup_change(db, tmp_path):
    device = models.NetworkDevice(
        hostname="sw1",
        ip_address="192.0.2.10",
        device_type="switch",
        os_type="cisco",
        username="network-user",
        encrypted_password="ciphertext",
    )
    payload = {
        "sw1": {"config": ["hostname sw1"], "exec": ["write memory"]}
    }
    change = models.ConfigurationChange(
        change_id="change-safety",
        created_by="admin",
        prompt="test",
        source_template="approved",
        target_devices=["sw1"],
        config_payload=payload,
        proposal_hash=proposal_hash(payload, ["sw1"], "approved"),
        status="verified",
        simulation_success=True,
        pre_backup_success=True,
        pre_backup_files={},
        pre_backup_completed_at=datetime.now(timezone.utc),
    )
    db.add_all([device, change])
    db.commit()

    filename = "Pre_Config_cisco_switch_sw1_20260810_120000.txt"
    content = b"hostname sw1\n"
    (tmp_path / filename).write_bytes(content)
    change.pre_backup_files = {"sw1": filename}
    db.add(
        models.ConfigurationBackupArtifact(
            change_id=change.change_id,
            hostname="sw1",
            artifact_type="pre_config",
            filename=filename,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )
    )
    db.commit()
    return change


def _capture_result(tmp_path, prefix, content, success=True):
    if not success:
        return {}, [{
            "hostname": "sw1",
            "success": False,
            "error": SECRET_CONFIG,
            "config": SECRET_CONFIG,
        }]
    filename = f"{prefix}_cisco_switch_sw1_20260810_120001.txt"
    data = content.encode()
    (tmp_path / filename).write_bytes(data)
    return {"sw1": filename}, [{
        "hostname": "sw1",
        "success": True,
        "filename": filename,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "config": SECRET_CONFIG,
    }]


def _status(db, change):
    return configuration.get_change_status(
        change.change_id,
        db,
        SimpleNamespace(username="admin", role="admin"),
    )


def test_prepare_projects_secret_config_out_of_db_api_audit_and_response(
    db, tmp_path, monkeypatch,
):
    change = _setup_change(db, tmp_path)
    rollback = authorize_rollback(
        db,
        change,
        "admin",
        "Prepare secret projection test.",
        tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    events = []
    result = prepare_manual_restore(
        db,
        change,
        rollback,
        "admin",
        tmp_path,
        backup_runner=lambda *args, **kwargs: _capture_result(
            tmp_path, "Pre_Rollback", SECRET_CONFIG
        ),
        audit_logger=lambda **kwargs: events.append(kwargs),
    )

    artifact_path = tmp_path / result.pre_rollback_files["sw1"]
    assert SECRET_CONFIG in artifact_path.read_text(encoding="utf-8")
    assert SECRET_CONFIG not in str(result.per_device_results)
    assert "config" not in result.per_device_results["sw1"]
    assert SECRET_CONFIG not in str(events)
    assert SECRET_CONFIG not in str(_status(db, change))

    monkeypatch.setattr(
        configuration, "prepare_manual_restore", lambda *args, **kwargs: result
    )
    monkeypatch.setattr(
        configuration,
        "manual_restore_handoff",
        lambda db_arg, change_arg, rollback_arg, **kwargs: (
            rollback_service.manual_restore_handoff(
                db_arg,
                change_arg,
                rollback_arg,
                tmp_path,
                device_contact_performed=kwargs.get(
                    "device_contact_performed", False
                ),
            )
        ),
    )
    response = configuration.prepare_change_manual_restore(
        change.change_id,
        SimpleNamespace(rollback_id=rollback.rollback_id),
        db,
        SimpleNamespace(username="admin", role="admin"),
    )
    assert SECRET_CONFIG not in str(response)
    assert "config" not in str(response)


def test_prepare_failure_is_sanitized_single_use_and_allows_new_authorization(
    db, tmp_path,
):
    change = _setup_change(db, tmp_path)
    old = authorize_rollback(
        db,
        change,
        "admin",
        "Prepare failure projection test.",
        tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    events = []
    failed = prepare_manual_restore(
        db,
        change,
        old,
        "admin",
        tmp_path,
        backup_runner=lambda *args, **kwargs: _capture_result(
            tmp_path, "Pre_Rollback", SECRET_CONFIG, success=False
        ),
        audit_logger=lambda **kwargs: events.append(kwargs),
    )

    assert failed.status == "manual_restore_prepare_failed"
    assert SECRET_CONFIG not in str(failed.per_device_results)
    assert SECRET_CONFIG not in str(events)
    with pytest.raises(RollbackRejected, match="single-use"):
        prepare_manual_restore(
            db,
            change,
            old,
            "admin",
            tmp_path,
            backup_runner=lambda *args, **kwargs: pytest.fail("must not retry"),
            audit_logger=lambda **kwargs: None,
        )
    status = _status(db, change)
    assert status["rollback"]["eligible"] is True
    assert status["rollback"]["authorized"] is False
    new = authorize_rollback(
        db,
        change,
        "admin",
        "New authorization after prepare failure.",
        tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    assert new.rollback_id != old.rollback_id


@pytest.mark.parametrize(
    ("post_content", "post_success", "terminal_status"),
    [
        ("hostname different\n", True, "manual_restore_verification_failed"),
        (SECRET_CONFIG, False, "manual_restore_verification_error"),
    ],
)
def test_verification_terminal_failure_is_sanitized_and_reauthorizable(
    db, tmp_path, post_content, post_success, terminal_status, monkeypatch,
):
    change = _setup_change(db, tmp_path)
    old = authorize_rollback(
        db,
        change,
        "admin",
        "Verification failure projection test.",
        tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    prepare_manual_restore(
        db,
        change,
        old,
        "admin",
        tmp_path,
        backup_runner=lambda *args, **kwargs: _capture_result(
            tmp_path, "Pre_Rollback", "current state\n"
        ),
        audit_logger=lambda **kwargs: None,
    )
    events = []
    result = verify_manual_restore(
        db,
        change,
        old,
        "admin",
        tmp_path,
        post_backup_runner=lambda *args, **kwargs: _capture_result(
            tmp_path, "Post_Rollback", post_content, success=post_success
        ),
        audit_logger=lambda **kwargs: events.append(kwargs),
    )

    assert result.status == terminal_status
    assert SECRET_CONFIG not in str(result.per_device_results)
    assert SECRET_CONFIG not in str(events)
    assert SECRET_CONFIG not in str(_status(db, change))
    monkeypatch.setattr(
        configuration, "verify_manual_restore", lambda *args, **kwargs: result
    )
    response = configuration.verify_change_manual_restore(
        change.change_id,
        SimpleNamespace(rollback_id=old.rollback_id),
        db,
        SimpleNamespace(username="admin", role="admin"),
    )
    assert SECRET_CONFIG not in str(response)
    with pytest.raises(RollbackRejected, match="only once"):
        verify_manual_restore(
            db,
            change,
            old,
            "admin",
            tmp_path,
            post_backup_runner=lambda *args, **kwargs: pytest.fail("must not retry"),
            audit_logger=lambda **kwargs: None,
        )
    status = _status(db, change)
    assert status["rollback"]["eligible"] is True
    assert status["rollback"]["authorized"] is False
    new = authorize_rollback(
        db,
        change,
        "admin",
        "New authorization after verification failure.",
        tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    assert new.rollback_id != old.rollback_id


def test_verified_is_terminal_in_backend_status_and_ui_source(db, tmp_path):
    change = _setup_change(db, tmp_path)
    rollback = authorize_rollback(
        db,
        change,
        "admin",
        "Successful manual restore verification.",
        tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    prepare_manual_restore(
        db,
        change,
        rollback,
        "admin",
        tmp_path,
        backup_runner=lambda *args, **kwargs: _capture_result(
            tmp_path, "Pre_Rollback", "current state\n"
        ),
        audit_logger=lambda **kwargs: None,
    )
    events = []
    verify_manual_restore(
        db,
        change,
        rollback,
        "admin",
        tmp_path,
        post_backup_runner=lambda *args, **kwargs: _capture_result(
            tmp_path, "Post_Rollback", "hostname sw1\n"
        ),
        audit_logger=lambda **kwargs: events.append(kwargs),
    )

    assert SECRET_CONFIG not in str(rollback.per_device_results)
    assert SECRET_CONFIG not in str(events)
    status = _status(db, change)
    assert status["rollback"]["status"] == "manual_restore_verified"
    assert status["rollback"]["authorized"] is False
    assert status["rollback"]["eligible"] is False
    with pytest.raises(RollbackRejected, match="already completed"):
        authorize_rollback(
            db,
            change,
            "admin",
            "Prohibited authorization after verified restore.",
            tmp_path,
            audit_logger=lambda **kwargs: None,
        )

    ui_source = (
        configuration.__file__.replace(
            "backend/routers/configuration.py",
            "frontend/src/components/Configuration.jsx",
        )
    )
    with open(ui_source, encoding="utf-8") as source_file:
        source = source_file.read()
    assert "Manual Restore Verified" in source
    assert "changeStatus.rollback?.authorized" in source


def test_source_assigns_only_sanitized_backup_results_to_rollback_json():
    with open(rollback_service.__file__, encoding="utf-8") as source_file:
        source = source_file.read()
    assert "rollback.per_device_results = post_by_host" not in source
    assert "rollback.per_device_results = results or {}" not in source
    assert "safe_post_by_host = sanitize_backup_results(post_results)" in source
    assert "results_by_host = sanitize_backup_results(backup_results)" in source
