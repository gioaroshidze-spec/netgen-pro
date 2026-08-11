import hashlib
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import yaml
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
    validate_preconfig_artifacts,
)
from routers import auth, configuration
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
    assert rollback.status == "authorized" and len(rollback.rollback_id) == 36
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
    assert active.status == "authorized"

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
    assert allowed.status == "authorized"


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
    assert authorized.status == "authorized"
    authorized.status = "rollback_failed"
    db.commit()
    add_change(db, ("sw1",), started=datetime.now(timezone.utc))
    with pytest.raises(RollbackRejected, match="Newer VNMS"):
        authorize_rollback(db, old, "admin", "Stale rollback should be rejected.", tmp_path, audit_logger=lambda **kwargs: None)


def test_unsupported_vendor_and_verified_without_authorization_fail_closed(db, tmp_path):
    add_device(db, os_type="mikrotik")
    change = add_change(db)
    bind_artifact(db, tmp_path, change)
    with pytest.raises(RollbackRejected, match="Cisco IOS"):
        authorize_rollback(db, change, "admin", "Unsupported vendor recovery.", tmp_path, audit_logger=lambda **kwargs: None)
    fake = SimpleNamespace(change_id=change.change_id, status="authorized")
    with pytest.raises(RollbackRejected):
        execute_rollback(db, change, fake, "admin", tmp_path, audit_logger=lambda **kwargs: None)


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


def test_cisco_adapter_uses_only_bounded_file_preflight_and_separate_replace(tmp_path, monkeypatch):
    source = tmp_path / "Pre_Config_cisco_switch_sw1_20260810_120000.txt"
    source.write_text("hostname sw1\n")
    artifact = SimpleNamespace(filename=source.name)
    captured = []

    def subprocess_runner(command, **kwargs):
        inventory = yaml.safe_load(open(command[2], encoding="utf-8"))
        playbook = yaml.safe_load(open(command[3], encoding="utf-8"))
        captured.append({"inventory": inventory, "playbook": playbook, "command": command})
        return SimpleNamespace(returncode=0, stdout=recap())

    monkeypatch.setattr(rollback_service, "get_ansible_inventory_vars", lambda device: {"ansible_host": "192.0.2.10"})
    success, results, _ = rollback_service.run_cisco_restore(
        [SimpleNamespace(hostname="sw1")], {"sw1": (artifact, source)},
        "12345678-1234-1234-1234-123456789abc", subprocess_runner,
    )
    assert len(captured) == 2
    host_vars = captured[0]["inventory"]["all"]["hosts"]["sw1"]
    prepare_tasks = captured[0]["playbook"][0]["tasks"]
    replace_tasks = captured[1]["playbook"][0]["tasks"]
    assert success is True and results["sw1"]["status"] == "restored"
    assert host_vars["restore_file"] == str(source)
    assert host_vars["restore_file_size"] == source.stat().st_size
    transfer = next(
        task for task in prepare_tasks
        if "ansible.netcommon.net_put" in task
    )
    assert transfer["ansible.netcommon.net_put"] == {
        "src": "{{ restore_file }}", "dest": "flash:vnms_rollback.cfg",
        "protocol": "scp", "mode": "binary",
    }
    assert replace_tasks[0]["cisco.ios.ios_command"]["commands"] == [
        {"command": "configure replace flash:vnms_rollback.cfg force"}
    ]
    prepare_text = yaml.safe_dump(captured[0]["playbook"])
    replace_text = yaml.safe_dump(captured[1]["playbook"])
    assert "configure replace" not in prepare_text
    assert "net_put" not in replace_text
    assert "vnms_rollback_12345678" not in prepare_text + replace_text

    commands = [
        item["command"]
        for task in prepare_tasks
        for item in task.get("cisco.ios.ios_command", {}).get("commands", [])
    ]
    delete_commands = [command for command in commands if command.startswith("delete ")]
    assert delete_commands == ["delete /force flash:vnms_rollback.cfg"]
    assert commands.count("dir flash:vnms_rollback.cfg") == 3
    assert "dir flash:" in commands
    assert next(task for task in prepare_tasks if task["name"] == "Remove only the existing VNMS-owned rollback file")["when"] == "vnms_temp_exists | bool"
    assert any("bytes free" in str(task) for task in prepare_tasks)
    assert any("determinably insufficient" in task["name"] for task in prepare_tasks)
    size_extract = next(
        task for task in prepare_tasks
        if task["name"] == "Extract the exact transferred VNMS rollback file size"
    )
    assert rollback_service._CISCO_ROLLBACK_DIR_ENTRY_PATTERN in (
        size_extract["ansible.builtin.set_fact"]["vnms_transferred_size_matches"]
    )
    unique_size = next(
        task for task in prepare_tasks
        if task["name"] == "Require a uniquely parseable transferred file size"
    )
    assert unique_size["ansible.builtin.assert"]["that"] == [
        "vnms_transferred_size_matches | length == 1"
    ]
    matching_size = next(
        task for task in prepare_tasks
        if task["name"] == "Require the transferred file size to match the validated artifact"
    )
    assert matching_size["ansible.builtin.assert"]["that"] == [
        "(vnms_transferred_size_matches | first | int) == (restore_file_size | int)"
    ]
    forbidden = ("startup-config", "config.text", "vlan.dat", "/recursive", "*.cfg")
    assert all(value not in prepare_text + replace_text for value in forbidden)


def test_missing_transferred_file_prevents_configure_replace(tmp_path, monkeypatch):
    source = tmp_path / "Pre_Config_cisco_switch_sw1_20260810_120000.txt"
    source.write_text("hostname sw1\n")
    artifact = SimpleNamespace(filename=source.name)
    playbooks = []

    def subprocess_runner(command, **kwargs):
        playbooks.append(yaml.safe_load(open(command[3], encoding="utf-8")))
        return SimpleNamespace(
            returncode=2,
            stdout=recap(failed=1, complete=False)
            + "The exact transferred VNMS rollback file is not present.\n",
        )

    monkeypatch.setattr(
        rollback_service, "get_ansible_inventory_vars",
        lambda device: {"ansible_host": "192.0.2.10"},
    )
    success, results, summary = rollback_service.run_cisco_restore(
        [SimpleNamespace(hostname="sw1")], {"sw1": (artifact, source)},
        "ignored-rollback-id", subprocess_runner,
    )
    assert success is False
    assert results["sw1"]["status"] == "prepare_failed"
    assert "exact transferred VNMS rollback file" in summary
    assert len(playbooks) == 1
    assert "configure replace" not in yaml.safe_dump(playbooks[0])


@pytest.mark.parametrize(
    ("size_case", "size_delta", "replace_expected"),
    [
        pytest.param("matching", 0, True, id="matching-remote-size"),
        pytest.param("smaller", -1, False, id="smaller-truncated-remote-size"),
        pytest.param("larger", 1, False, id="larger-remote-size"),
        pytest.param("unparseable", None, False, id="unparseable-remote-size"),
    ],
)
def test_transferred_file_size_gate_controls_configure_replace(
    tmp_path, monkeypatch, size_case, size_delta, replace_expected,
):
    source = tmp_path / "Pre_Config_cisco_switch_sw1_20260810_120000.txt"
    source.write_text("hostname sw1\n")
    artifact = SimpleNamespace(filename=source.name)
    playbooks = []

    size_text = (
        "unknown"
        if size_delta is None
        else str(source.stat().st_size + size_delta)
    )
    remote_listing = (
        "Directory of flash:/vnms_rollback.cfg\n"
        f"  17  -rw-  {size_text}  Aug 11 2026 12:00:00 +00:00  vnms_rollback.cfg\n"
        "15998976 bytes total (12000000 bytes free)\n"
    )

    def subprocess_runner(command, **kwargs):
        inventory = yaml.safe_load(open(command[2], encoding="utf-8"))
        playbook = yaml.safe_load(open(command[3], encoding="utf-8"))
        playbooks.append(playbook)
        if len(playbooks) == 1:
            prepare_tasks = playbook[0]["tasks"]
            size_fact = next(
                task for task in prepare_tasks
                if task["name"] == "Extract the exact transferred VNMS rollback file size"
            )
            assert rollback_service._CISCO_ROLLBACK_DIR_ENTRY_PATTERN in (
                size_fact["ansible.builtin.set_fact"]["vnms_transferred_size_matches"]
            )
            remote_matches = re.findall(
                rollback_service._CISCO_ROLLBACK_DIR_ENTRY_PATTERN,
                remote_listing,
            )
            local_size = inventory["all"]["hosts"]["sw1"]["restore_file_size"]
            size_is_valid = (
                len(remote_matches) == 1
                and int(remote_matches[0]) == local_size
            )
            return SimpleNamespace(
                returncode=0 if size_is_valid else 2,
                stdout=(
                    recap()
                    if size_is_valid
                    else recap(failed=1, complete=False)
                    + f"Transferred file size validation failed: {size_case}.\n"
                ),
            )
        return SimpleNamespace(returncode=0, stdout=recap())

    monkeypatch.setattr(
        rollback_service, "get_ansible_inventory_vars",
        lambda device: {"ansible_host": "192.0.2.10"},
    )
    success, results, _ = rollback_service.run_cisco_restore(
        [SimpleNamespace(hostname="sw1")], {"sw1": (artifact, source)},
        "ignored-rollback-id", subprocess_runner,
    )

    assert success is replace_expected
    assert results["sw1"]["status"] == (
        "restored" if replace_expected else "prepare_failed"
    )
    assert len(playbooks) == (2 if replace_expected else 1)
    if replace_expected:
        assert "configure replace flash:vnms_rollback.cfg force" in yaml.safe_dump(
            playbooks[1]
        )
    else:
        assert all(
            "configure replace" not in yaml.safe_dump(playbook)
            for playbook in playbooks
        )


def test_cleanup_adapter_deletes_only_exact_vnms_owned_file(tmp_path, monkeypatch):
    captured = {}

    def subprocess_runner(command, **kwargs):
        captured["playbook"] = yaml.safe_load(open(command[3], encoding="utf-8"))
        return SimpleNamespace(returncode=0, stdout=recap())

    monkeypatch.setattr(
        rollback_service, "get_ansible_inventory_vars",
        lambda device: {"ansible_host": "192.0.2.10"},
    )
    success, results, _ = rollback_service.cleanup_cisco_rollback_temp(
        [SimpleNamespace(hostname="sw1")], subprocess_runner,
    )
    assert success is True and results["sw1"]["status"] == "cleaned"
    cleanup_text = yaml.safe_dump(captured["playbook"])
    commands = [
        item["command"]
        for task in captured["playbook"][0]["tasks"]
        for item in task.get("cisco.ios.ios_command", {}).get("commands", [])
    ]
    assert [command for command in commands if command.startswith("delete ")] == [
        "delete /force flash:vnms_rollback.cfg"
    ]
    assert commands.count("dir flash:vnms_rollback.cfg") == 2
    assert all(value not in cleanup_text for value in (
        "startup-config", "config.text", "vlan.dat", "/recursive", "*.cfg"
    ))


def test_prerollback_precedes_exact_restore_and_match_is_rolled_back(db, tmp_path):
    _, change, rollback = authorized_change(db, tmp_path)
    order = []
    def pre(*args, **kwargs):
        order.append("pre")
        return backup_result(tmp_path, "Pre_Rollback", "current state\n")
    def restore(devices, artifacts, rollback_id):
        order.append("restore")
        assert artifacts["sw1"][1].read_text() == "hostname sw1\n"
        return True, {"sw1": {"status": "restored"}}, "ok"
    def post(*args, **kwargs):
        order.append("post")
        return backup_result(tmp_path, "Post_Rollback", "hostname sw1\r\n! Last configuration change at 12:00 UTC\n")
    def cleanup(devices):
        order.append("cleanup")
        return True, {"sw1": {"status": "cleaned"}}, "ok"
    result = execute_rollback(
        db, change, rollback, "admin", tmp_path, pre, post, restore, cleanup,
        audit_logger=lambda **kwargs: None,
    )
    assert order == ["pre", "restore", "post", "cleanup"]
    assert result.status == "rolled_back"
    assert result.verification_results["sw1"]["matches_pre_config"] is True
    assert result.per_device_results["sw1"]["temporary_file_cleanup"]["status"] == "cleaned"
    with pytest.raises(RollbackRejected):
        execute_rollback(
            db, change, rollback, "admin", tmp_path, pre, post, restore, cleanup,
            audit_logger=lambda **kwargs: None,
        )


def test_any_prerollback_failure_prevents_all_restore(db, tmp_path):
    _, change, rollback = authorized_change(db, tmp_path)
    restore_calls = []
    result = execute_rollback(
        db, change, rollback, "admin", tmp_path,
        lambda *a, **k: backup_result(tmp_path, "Pre_Rollback", success=False),
        lambda *a, **k: None,
        lambda *a, **k: restore_calls.append(True),
        audit_logger=lambda **kwargs: None,
    )
    assert result.status == "pre_rollback_failed"
    assert restore_calls == []


@pytest.mark.parametrize(("restore_success", "post_content", "post_success", "expected"), [
    (True, "different config\n", True, "rollback_verification_failed"),
    (False, "hostname sw1\n", True, "rollback_failed"),
    (True, "hostname sw1\n", False, "rollback_verification_failed"),
])
def test_restore_and_post_verification_failures_never_report_success(db, tmp_path, restore_success, post_content, post_success, expected):
    _, change, rollback = authorized_change(db, tmp_path)
    cleanup_calls = []
    restore = lambda *a: (restore_success, {"sw1": {"status": "restored" if restore_success else "restore_failed"}}, "restore error")
    post = lambda *a, **k: backup_result(tmp_path, "Post_Rollback", post_content, post_success)
    result = execute_rollback(
        db, change, rollback, "admin", tmp_path,
        lambda *a, **k: backup_result(tmp_path, "Pre_Rollback", "current\n"),
        post, restore,
        lambda *a, **k: cleanup_calls.append(True),
        audit_logger=lambda **kwargs: None,
    )
    assert result.status == expected
    assert cleanup_calls == []


def test_restore_failure_persists_and_audits_bounded_sanitized_ansible_summary(db, tmp_path):
    _, change, rollback = authorized_change(db, tmp_path)
    events = []
    sensitive_summary = (
        ("old output\n" * 600)
        + "TASK [Transfer integrity-validated Pre_Config artifact]\n"
        + "fatal: [sw1]: FAILED! => scp package missing "
        + "ansible_password='plain-password' token=api-token "
        + "encrypted_password=ciphertext\n"
        + "Authorization: Bearer bearer-token\n"
        + "-----BEGIN PRIVATE KEY-----\nprivate-material\n"
        + "-----END PRIVATE KEY-----\n"
    )

    result = execute_rollback(
        db, change, rollback, "admin", tmp_path,
        lambda *a, **k: backup_result(tmp_path, "Pre_Rollback", "current\n"),
        lambda *a, **k: None,
        lambda *a: (
            False, {"sw1": {"status": "restore_failed"}}, sensitive_summary
        ),
        audit_logger=lambda **kwargs: events.append(kwargs),
    )

    failure_event = events[-1]
    assert result.status == "rollback_failed"
    assert result.error == failure_event["details"]["restore_summary"]
    assert len(result.error) <= 4000
    assert "TASK [Transfer integrity-validated Pre_Config artifact]" in result.error
    assert "scp package missing" in result.error
    assert "[REDACTED]" in result.error
    assert "plain-password" not in result.error
    assert "api-token" not in result.error
    assert "ciphertext" not in result.error
    assert "bearer-token" not in result.error
    assert "private-material" not in result.error
    assert "network-user" not in str(failure_event)


def test_artifact_revalidated_before_restore_and_audit_has_ids_actor_no_secrets(db, tmp_path):
    _, change, rollback = authorized_change(db, tmp_path)
    (tmp_path / change.pre_backup_files["sw1"]).write_text("tampered")
    calls = []
    with pytest.raises(RollbackRejected, match="integrity"):
        execute_rollback(db, change, rollback, "admin", tmp_path,
                         lambda *a, **k: calls.append("backup"),
                         lambda *a, **k: calls.append("post"),
                         lambda *a, **k: calls.append("restore"),
                         audit_logger=lambda **kwargs: None)
    assert calls == []

    db.delete(rollback)
    db.commit()
    bind = db.query(models.ConfigurationBackupArtifact).filter_by(change_id=change.change_id).one()
    data = b"hostname sw1\n"
    (tmp_path / bind.filename).write_bytes(data)
    bind.sha256, bind.size_bytes = hashlib.sha256(data).hexdigest(), len(data)
    db.commit()
    events = []
    new_rollback = authorize_rollback(db, change, "admin", "Audited rollback reason.", tmp_path, audit_logger=lambda **kwargs: events.append(kwargs))
    event_text = str(events[-1])
    assert change.change_id in event_text and new_rollback.rollback_id in event_text
    assert events[-1]["author"] == "admin"
    assert "ciphertext" not in event_text and "network-user" not in event_text


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
        assert client.post(f"/configuration/changes/{change.change_id}/authorize-rollback", json={"reason": "Valid rollback reason."}).status_code == 401
        app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(username="viewer", role="viewer")
        assert client.post(f"/configuration/changes/{change.change_id}/authorize-rollback", json={"reason": "Valid rollback reason."}, headers=auth_headers).status_code == 403
        assert client.post(f"/configuration/changes/{change.change_id}/verify", json={}, headers=auth_headers).status_code == 403
        app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(username="admin", role="admin")
        endpoint = f"/configuration/changes/{change.change_id}/authorize-rollback"
        assert client.post(endpoint, json={"reason": "short"}, headers=auth_headers).status_code == 422
        assert client.post(endpoint, json={"reason": "x" * 1001}, headers=auth_headers).status_code == 422
        assert client.post(endpoint, json={"reason": "Valid rollback reason.", "targets": ["evil"]}, headers=auth_headers).status_code == 422
        assert client.post(f"/configuration/changes/{change.change_id}/rollback",
                           json={"rollback_id": "x", "filename": "evil"}, headers=auth_headers).status_code == 422
        status = client.get(f"/configuration/changes/{change.change_id}", headers=auth_headers)
        assert status.status_code == 200
        assert "config_payload" not in status.json() and "encrypted_password" not in status.text
