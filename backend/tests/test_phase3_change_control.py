import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import rollback_service
from change_control import proposal_hash
from database import Base, get_db
from rollback_service import (
    RollbackRejected,
    authorize_rollback,
    execute_rollback,
    prepare_manual_restore,
    verify_manual_restore,
    validate_preconfig_artifacts,
)
from routers import auth, configuration, jobs, maintenance
from device_capabilities import (
    AUTOMATED_RESTORE_UNQUALIFIED_REASON, get_device_capabilities,
)
from verification_service import (
    VerificationConflict,
    parse_verification_output,
    run_verification,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    session = Session()
    yield session
    session.close()


def add_device(db, hostname="sw1", os_type="cisco"):
    host_number = db.query(models.NetworkDevice).count() + 10
    device = models.NetworkDevice(
        hostname=hostname, ip_address=f"192.0.2.{host_number}", device_type="switch",
        os_type=os_type, username="network-user", encrypted_password="ciphertext",
    )
    db.add(device)
    db.commit()
    return device


def add_change(db, hostnames=("sw1",), status="verified", started=None):
    payload = {host: {"config": [f"hostname {host}"], "exec": ["write memory"]} for host in hostnames}
    change = models.ConfigurationChange(
        change_id=f"change-{db.query(models.ConfigurationChange).count() + 1}",
        created_by="admin", prompt="test", source_template="approved",
        target_devices=list(hostnames), config_payload=payload,
        proposal_hash=proposal_hash(payload, list(hostnames), "approved"),
        status=status, simulation_success=True, pre_backup_success=True,
        pre_backup_files={}, pre_backup_completed_at=started or datetime.now(timezone.utc),
    )
    db.add(change)
    db.commit()
    return change


def bind_artifact(db, tmp_path, change, hostname="sw1", content="hostname sw1\n"):
    filename = f"Pre_Config_cisco_switch_{hostname}_20260810_120000.txt"
    data = content.encode()
    (tmp_path / filename).write_bytes(data)
    change.pre_backup_files = {**(change.pre_backup_files or {}), hostname: filename}
    artifact = models.ConfigurationBackupArtifact(
        change_id=change.change_id, hostname=hostname, artifact_type="pre_config",
        filename=filename, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
    )
    db.add(artifact)
    db.commit()
    return artifact


def recap(host="sw1", ok=1, changed=0, unreachable=0, failed=0, complete=True):
    suffix = "PLAYBOOK COMPLETE: No errors detected.\n" if complete else "PLAYBOOK FINISHED WITH ERRORS.\n"
    return f"PLAY RECAP\n{host} : ok={ok} changed={changed} unreachable={unreachable} failed={failed}\n{suffix}"


@pytest.mark.parametrize(("output", "status"), [
    (recap(), "verified"),
    (recap(changed=1), "verification_failed"),
    (recap(failed=1, complete=False), "verification_error"),
    (recap(unreachable=1, complete=False), "verification_error"),
    ("PLAY RECAP\nr1 : ok=1 changed=0 unreachable=0 failed=0\nPLAYBOOK COMPLETE: No errors detected.", "verification_error"),
    ("PLAY RECAP\nsw1 : changed=0 failed=0\nPLAYBOOK COMPLETE: No errors detected.", "verification_error"),
    ("not an ansible recap", "verification_error"),
])
def test_verification_parser_fails_closed_per_expected_target(output, status):
    actual, results, _, _ = parse_verification_output(output, {"sw1"})
    assert actual == status
    if status != "verified":
        assert results.get("sw1", {}).get("status") != "verified"


def test_verification_uses_exact_stored_proposal_mode_and_persists_per_target(db):
    device = add_device(db)
    change = add_change(db)
    calls = []

    def runner(payload, devices, **kwargs):
        calls.append((payload, [item.hostname for item in devices], kwargs))
        return [recap()]

    record = run_verification(db, change, [device], "admin", runner, audit_logger=lambda **kwargs: None)
    assert calls == [(change.config_payload, ["sw1"], {"is_check_mode": True, "execution_mode": "verification"})]
    assert record.status == "verified"
    assert record.per_device_results["sw1"]["changed"] == 0
    assert change.status == "verified"


def test_verification_hash_mismatch_blocks_runner_and_records_error(db):
    device = add_device(db)
    change = add_change(db)
    change.config_payload = {}
    db.commit()
    calls = []
    record = run_verification(db, change, [device], "admin", lambda *a, **k: calls.append(True), audit_logger=lambda **kwargs: None)
    assert record.status == "verification_error"
    assert "integrity" in record.error.lower()
    assert record.per_device_results["sw1"]["status"] == "verification_error"
    assert calls == []


@pytest.mark.parametrize("os_type", ["mikrotik", "aruba"])
def test_unsupported_vendor_verification_fails_closed_before_skipped_check_tasks(db, os_type):
    device = add_device(db, os_type=os_type)
    change = add_change(db)
    calls = []

    def skipped_check_runner(*args, **kwargs):
        calls.append((args, kwargs))
        return [recap()]

    record = run_verification(
        db, change, [device], "System", skipped_check_runner,
        audit_logger=lambda **kwargs: None,
    )

    assert calls == []
    assert record.status == "verification_error"
    assert change.status == "verification_error"
    assert "supported only for Cisco IOS" in record.error
    assert os_type in record.error
    assert record.per_device_results["sw1"]["status"] == "verification_error"


def test_manual_reverification_creates_numbered_attempts_and_concurrency_rejects(db):
    device = add_device(db)
    change = add_change(db)
    runner = lambda *a, **k: [recap()]
    first = run_verification(db, change, [device], "admin", runner, audit_logger=lambda **kwargs: None)
    second = run_verification(db, change, [device], "admin", runner, audit_logger=lambda **kwargs: None)
    assert (first.attempt_number, second.attempt_number) == (1, 2)
    db.add(models.ConfigurationVerification(
        verification_id="active", change_id=change.change_id, attempt_number=3,
        requested_by="admin", started_at=datetime.now(timezone.utc), status="verifying",
        per_device_results={},
    ))
    db.commit()
    with pytest.raises(VerificationConflict):
        run_verification(db, change, [device], "admin", runner, audit_logger=lambda **kwargs: None)


def test_artifact_hash_size_and_binding_validate_then_modification_fails(db, tmp_path):
    add_device(db)
    change = add_change(db)
    artifact = bind_artifact(db, tmp_path, change)
    assert validate_preconfig_artifacts(db, change, tmp_path)["sw1"][0].sha256 == artifact.sha256
    (tmp_path / artifact.filename).write_text("modified")
    with pytest.raises(RollbackRejected, match="integrity"):
        validate_preconfig_artifacts(db, change, tmp_path)


def test_cisco_comparison_normalizes_only_line_endings_trailing_space_and_known_metadata():
    left = "hostname sw1  \r\n! Last configuration change at 12:00 UTC\r\n\r\n"
    right = "hostname sw1\n! NVRAM config last updated at 12:01 UTC"
    assert rollback_service.normalize_config_for_comparison(left) == "hostname sw1"
    assert rollback_service.normalize_config_for_comparison(left) == rollback_service.normalize_config_for_comparison(right)
    assert rollback_service.normalize_config_for_comparison("hostname other") != "hostname sw1"


def test_artifact_path_traversal_wrong_host_missing_and_legacy_fail_closed(db, tmp_path):
    add_device(db)
    change = add_change(db)
    change.pre_backup_files = {"sw1": "../outside.txt"}
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x")
    db.add(models.ConfigurationBackupArtifact(
        change_id=change.change_id, hostname="sw1", artifact_type="pre_config",
        filename="../outside.txt", sha256=hashlib.sha256(b"x").hexdigest(), size_bytes=1,
    ))
    db.commit()
    with pytest.raises(RollbackRejected, match="unsafe"):
        validate_preconfig_artifacts(db, change, tmp_path)

    db.query(models.ConfigurationBackupArtifact).delete()
    db.commit()
    with pytest.raises(RollbackRejected, match="legacy/unhashed"):
        validate_preconfig_artifacts(db, change, tmp_path)

    bind_artifact(db, tmp_path, change, hostname="r1")
    with pytest.raises(RollbackRejected, match="incomplete"):
        validate_preconfig_artifacts(db, change, tmp_path)


def test_authorization_is_device_io_free_server_generated_and_single_active(db, tmp_path, monkeypatch):
    add_device(db)
    change = add_change(db)
    bind_artifact(db, tmp_path, change)
    contacted = []
    monkeypatch.setattr(rollback_service, "create_prerollback_backups", lambda *a, **k: contacted.append(True))
    rollback = authorize_rollback(db, change, "admin", "Operational rollback required.", tmp_path, audit_logger=lambda **kwargs: None)
    assert rollback.status == "manual_restore_required" and len(rollback.rollback_id) == 36
    assert contacted == []
    with pytest.raises(RollbackRejected, match="active"):
        authorize_rollback(db, change, "admin", "Another valid rollback reason.", tmp_path, audit_logger=lambda **kwargs: None)


def test_active_rollback_rejects_overlapping_targets_but_allows_nonoverlap(db, tmp_path):
    add_device(db, "sw1")
    add_device(db, "sw2")
    first = add_change(db, ("sw1",))
    bind_artifact(db, tmp_path, first, "sw1", "hostname sw1\n")
    active = authorize_rollback(
        db, first, "admin", "Keep the first rollback active.", tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    assert active.status == "manual_restore_required"

    overlapping = add_change(db, ("sw1",))
    bind_artifact(db, tmp_path, overlapping, "sw1", "hostname sw1\n")
    with pytest.raises(RollbackRejected, match="overlapping target device.*sw1"):
        authorize_rollback(
            db, overlapping, "admin", "Reject this overlapping rollback.",
            tmp_path, audit_logger=lambda **kwargs: None,
        )

    nonoverlapping = add_change(db, ("sw2",))
    bind_artifact(db, tmp_path, nonoverlapping, "sw2", "hostname sw2\n")
    allowed = authorize_rollback(
        db, nonoverlapping, "admin", "Allow this independent rollback.",
        tmp_path, audit_logger=lambda **kwargs: None,
    )
    assert allowed.status == "manual_restore_required"


def test_overlapping_active_rollback_authorization_returns_http_409(db, tmp_path, monkeypatch):
    add_device(db, "sw1")
    first = add_change(db, ("sw1",))
    bind_artifact(db, tmp_path, first, "sw1", "hostname sw1\n")
    authorize_rollback(
        db, first, "admin", "Keep an overlapping rollback active.", tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    second = add_change(db, ("sw1",))
    bind_artifact(db, tmp_path, second, "sw1", "hostname sw1\n")

    app = FastAPI()
    app.include_router(configuration.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(
        username="admin", role="admin"
    )
    monkeypatch.setattr(configuration, "log_event", lambda **kwargs: None)
    with TestClient(app) as client:
        response = client.post(
            f"/configuration/changes/{second.change_id}/authorize-rollback",
            json={"reason": "Reject the overlapping device rollback."},
            headers={"Authorization": "Bearer x"},
        )
    assert response.status_code == 409
    assert "overlapping target device" in response.json()["detail"]


def test_newer_overlap_blocks_but_nonoverlap_and_deployment_failed_are_eligible(db, tmp_path):
    add_device(db, "sw1")
    add_device(db, "sw2")
    old = add_change(db, ("sw1",), status="deployment_failed", started=datetime.now(timezone.utc) - timedelta(hours=2))
    bind_artifact(db, tmp_path, old)
    add_change(db, ("sw2",), started=datetime.now(timezone.utc) - timedelta(hours=1))
    authorized = authorize_rollback(db, old, "admin", "Partial deployment recovery.", tmp_path, audit_logger=lambda **kwargs: None)
    assert authorized.status == "manual_restore_required"
    authorized.status = "rollback_failed"
    db.commit()
    add_change(db, ("sw1",), started=datetime.now(timezone.utc))
    with pytest.raises(RollbackRejected, match="Newer VNMS"):
        authorize_rollback(db, old, "admin", "Stale rollback should be rejected.", tmp_path, audit_logger=lambda **kwargs: None)


def test_unknown_vendor_manual_handoff_and_automated_restore_fail_closed(db, tmp_path):
    add_device(db, os_type="unknown-os")
    change = add_change(db)
    bind_artifact(db, tmp_path, change)
    rollback = authorize_rollback(
        db, change, "admin", "Unsupported vendor recovery.", tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    assert rollback.status == "manual_restore_required"
    with pytest.raises(RollbackRejected, match="Automated restore is unsupported"):
        execute_rollback(
            db, change, rollback, "admin", tmp_path,
            audit_logger=lambda **kwargs: None,
        )


def backup_result(tmp_path, prefix, content="hostname sw1\n", success=True):
    if not success:
        return {}, [{"hostname": "sw1", "success": False, "error": "timeout"}]
    filename = f"{prefix}_cisco_switch_sw1_20260810_120001.txt"
    data = content.encode()
    (tmp_path / filename).write_bytes(data)
    return {"sw1": filename}, [{"hostname": "sw1", "success": True, "filename": filename,
                                 "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}]


def authorized_change(db, tmp_path):
    device = add_device(db)
    change = add_change(db)
    bind_artifact(db, tmp_path, change)
    rollback = authorize_rollback(db, change, "admin", "Validated operational rollback.", tmp_path, audit_logger=lambda **kwargs: None)
    return device, change, rollback


def test_capabilities_default_false_cisco_does_not_enable_and_unknown_fails_closed():
    assert get_device_capabilities().automated_restore is False
    cisco = get_device_capabilities(SimpleNamespace(os_type="cisco", is_legacy=False))
    unknown = get_device_capabilities(SimpleNamespace(os_type="future-vendor"))
    assert cisco.automated_restore is False
    assert cisco.automated_restore_reason == AUTOMATED_RESTORE_UNQUALIFIED_REASON
    assert unknown.automated_restore is False
    assert unknown.backup is False


def test_automated_restore_code_and_device_operations_are_absent(db, tmp_path):
    _, change, rollback = authorized_change(db, tmp_path)
    source = open(rollback_service.__file__, encoding="utf-8").read()
    for forbidden in (
        "net_put", "cli_restore", "configure replace", "copy_file(",
        "send_command(", "dir flash:", "bytes free",
    ):
        assert forbidden not in source
    with pytest.raises(RollbackRejected, match="Automated restore is unsupported"):
        execute_rollback(
            db, change, rollback, "admin", tmp_path,
            audit_logger=lambda **kwargs: None,
        )
    assert rollback.status == "manual_restore_required"


def test_prepare_manual_restore_captures_central_prerollback_only_and_is_single_use(
    db, tmp_path,
):
    _, change, rollback = authorized_change(db, tmp_path)
    calls = []
    events = []

    def central_backup(devices, archive_dir=None):
        calls.append(([device.hostname for device in devices], archive_dir))
        return backup_result(tmp_path, "Pre_Rollback", "current state\n")

    result = prepare_manual_restore(
        db, change, rollback, "admin", tmp_path,
        backup_runner=central_backup, audit_logger=lambda **kwargs: events.append(kwargs),
    )
    assert calls == [(["sw1"], tmp_path)]
    assert events[-1]["details"]["device_contact_performed"] is True
    assert result.status == "manual_restore_ready"
    assert result.pre_rollback_files["sw1"].startswith("Pre_Rollback_")
    artifact = db.query(models.ConfigurationBackupArtifact).filter_by(
        rollback_id=rollback.rollback_id, artifact_type="pre_rollback"
    ).one()
    assert artifact.sha256 and artifact.size_bytes > 0
    with pytest.raises(RollbackRejected, match="single-use"):
        prepare_manual_restore(
            db, change, rollback, "admin", tmp_path,
            backup_runner=lambda *args, **kwargs: pytest.fail("must not capture twice"),
            audit_logger=lambda **kwargs: None,
        )


@pytest.mark.parametrize(
    ("post_content", "post_success", "expected"),
    [
        ("hostname sw1\r\n! Last configuration change at 12:00 UTC\n", True,
         "manual_restore_verified"),
        ("hostname different\n", True, "manual_restore_verification_failed"),
        ("hostname sw1\n", False, "manual_restore_verification_error"),
    ],
)
def test_verify_manual_restore_captures_and_compares_without_mutation(
    db, tmp_path, post_content, post_success, expected,
):
    _, change, rollback = authorized_change(db, tmp_path)
    prepare_manual_restore(
        db, change, rollback, "admin", tmp_path,
        backup_runner=lambda *args, **kwargs: backup_result(
            tmp_path, "Pre_Rollback", "current state\n"
        ),
        audit_logger=lambda **kwargs: None,
    )
    calls = []

    def post_capture(devices, archive_dir=None):
        calls.append(([device.hostname for device in devices], archive_dir))
        return backup_result(
            tmp_path, "Post_Rollback", post_content, post_success
        )

    result = verify_manual_restore(
        db, change, rollback, "admin", tmp_path,
        post_backup_runner=post_capture, audit_logger=lambda **kwargs: None,
    )
    assert calls == [(["sw1"], tmp_path)]
    assert result.status == expected
    if expected == "manual_restore_verified":
        assert result.verification_results["sw1"]["matches_pre_config"] is True
    elif expected == "manual_restore_verification_failed":
        assert result.verification_results["sw1"]["matches_pre_config"] is False
    else:
        assert result.verification_results["sw1"]["status"] == "verification_error"


def test_manual_restore_handoff_audit_has_metadata_no_secrets(db, tmp_path):
    add_device(db)
    change = add_change(db)
    artifact = bind_artifact(db, tmp_path, change)
    events = []
    rollback = authorize_rollback(
        db, change, "admin", "Audited manual restore reason.", tmp_path,
        audit_logger=lambda **kwargs: events.append(kwargs),
    )
    details = events[-1]["details"]
    assert details["rollback_id"] == rollback.rollback_id
    assert details["change_id"] == change.change_id
    assert details["target_hostnames"] == ["sw1"]
    assert details["artifacts"]["sw1"] == {
        "filename": artifact.filename,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }
    assert details["automated_restore"] is False
    assert details["device_contact_performed"] is False
    assert "ciphertext" not in str(details)
    assert "hostname sw1" not in str(details)


def test_manual_restore_endpoints_are_admin_only_and_bodies_are_strict(
    db, tmp_path, monkeypatch,
):
    add_device(db)
    change = add_change(db)
    bind_artifact(db, tmp_path, change)
    rollback = authorize_rollback(
        db, change, "admin", "Valid manual restore reason.", tmp_path,
        audit_logger=lambda **kwargs: None,
    )
    app = FastAPI()
    app.include_router(configuration.router)
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(configuration, "log_event", lambda **kwargs: None)
    headers = {"Authorization": "Bearer x"}
    with TestClient(app) as client:
        app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(
            username="viewer", role="viewer"
        )
        for action in ("prepare-manual-restore", "verify-manual-restore"):
            response = client.post(
                f"/configuration/changes/{change.change_id}/{action}",
                json={"rollback_id": rollback.rollback_id}, headers=headers,
            )
            assert response.status_code == 403
        app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(
            username="admin", role="admin"
        )
        response = client.post(
            f"/configuration/changes/{change.change_id}/prepare-manual-restore",
            json={"rollback_id": rollback.rollback_id, "filename": "forbidden"},
            headers=headers,
        )
        assert response.status_code == 422


def test_maintenance_restore_is_rejected_before_playbook_or_device_contact(
    db, monkeypatch,
):
    device = add_device(db)
    events = []
    monkeypatch.setattr(maintenance, "log_event", lambda **kwargs: events.append(kwargs))
    app = FastAPI()
    app.include_router(maintenance.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(
        username="admin", role="admin"
    )
    with TestClient(app) as client:
        response = client.post(
            "/restore-devices/",
            data={"device_ids": f"[{device.id}]", "archive_file": "backup.txt"},
            headers={"Authorization": "Bearer x"},
        )
    assert response.status_code == 409
    assert "unsupported" in response.json()["detail"].lower()
    assert events[-1]["details"]["device_contact_performed"] is False
    source = open(maintenance.__file__, encoding="utf-8").read()
    for forbidden in ("net_put", "configure replace", "create_subprocess_exec"):
        assert forbidden not in source


@pytest.mark.parametrize("flag", ["save_flash", "save_nvram"])
def test_mutating_manual_backup_options_are_rejected_before_capture(
    db, monkeypatch, flag,
):
    device = add_device(db)
    contacted = []
    monkeypatch.setattr(
        maintenance, "process_single_backup",
        lambda *args, **kwargs: contacted.append(True),
    )
    app = FastAPI()
    app.include_router(maintenance.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(
        username="admin", role="admin"
    )
    payload = {
        "save_nvram": flag == "save_nvram",
        "save_flash": flag == "save_flash",
        "download_local": True,
        "save_archive": True,
        "prefix": "safe",
    }
    with TestClient(app) as client:
        response = client.post(
            f"/backup-device/{device.id}", json=payload,
            headers={"Authorization": "Bearer x"},
        )
    assert response.status_code == 422
    assert contacted == []


@pytest.mark.parametrize("flag", ["save_flash", "save_nvram"])
def test_mutating_scheduled_backup_options_are_rejected(
    db, monkeypatch, flag,
):
    scheduler_calls = []
    monkeypatch.setattr(
        jobs, "sync_jobs_to_scheduler", lambda: scheduler_calls.append(True)
    )
    app = FastAPI()
    app.include_router(jobs.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(
        username="admin", role="admin"
    )
    payload = {
        "name": "read-only backup",
        "job_type": "backup",
        "target_devices": ["sw1"],
        "job_payload": {
            "save_nvram": flag == "save_nvram",
            "save_flash": flag == "save_flash",
            "save_archive": True,
        },
        "cron_day_of_week": "*",
        "cron_hour": "1",
        "cron_minute": "0",
    }
    with TestClient(app) as client:
        response = client.post(
            "/jobs/", json=payload,
            headers={"Authorization": "Bearer x"},
        )
    assert response.status_code == 422
    assert db.query(models.ScheduledJob).count() == 0
    assert scheduler_calls == []


def test_scheduled_backup_source_contains_no_device_mutation():
    import inspect
    import scheduler_engine

    source = inspect.getsource(scheduler_engine.execute_scheduled_job)
    assert "save_config" not in source
    assert "send_command_timing" not in source
    assert "VNMS_Last_Good" not in source
    assert "send_command(show_cmd)" in source


def test_phase3_endpoints_enforce_rbac_and_strict_bodies(db, tmp_path, monkeypatch):
    add_device(db)
    change = add_change(db)
    bind_artifact(db, tmp_path, change)
    app = FastAPI()
    app.include_router(configuration.router)
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(configuration, "log_event", lambda **kwargs: None)
    with TestClient(app) as client:
        auth_headers = {"Authorization": "Bearer x"}
        endpoint = f"/configuration/changes/{change.change_id}/authorize-rollback"
        assert client.post(endpoint, json={"reason": "Valid rollback reason."}).status_code == 401
        app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(
            username="viewer", role="viewer"
        )
        assert client.post(endpoint, json={"reason": "Valid rollback reason."}, headers=auth_headers).status_code == 403
        app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(
            username="admin", role="admin"
        )
        assert client.post(endpoint, json={"reason": "short"}, headers=auth_headers).status_code == 422
        assert client.post(endpoint, json={"reason": "x" * 1001}, headers=auth_headers).status_code == 422
        assert client.post(endpoint, json={"reason": "Valid rollback reason.", "targets": ["evil"]}, headers=auth_headers).status_code == 422
        assert client.post(
            f"/configuration/changes/{change.change_id}/rollback",
            json={"rollback_id": "x", "filename": "evil"}, headers=auth_headers,
        ).status_code == 422
        status = client.get(
            f"/configuration/changes/{change.change_id}", headers=auth_headers
        )
        assert status.status_code == 200
        assert status.json()["rollback"]["automated_restore"] is False
        assert "config_payload" not in status.json()
        assert "encrypted_password" not in status.text
