import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
from routers import auth, configuration
import backup_service


def user(role):
    return SimpleNamespace(id=1, username=f"{role}_user", role=role)


def payload(hosts=("sw1",)):
    config = {host: {"config": [f"hostname {host}"], "exec": []} for host in hosts}
    return {"prompt": "configure test ports", "config_text": json.dumps(config),
            "switches": list(hosts), "routers": [], "source_template": "approved-template"}


def successful_stream(*args, **kwargs):
    return iter(["data: PLAY RECAP\n\n", "data: sw1 : ok=1 changed=0 unreachable=0 failed=0\n\n",
                 "data: PLAYBOOK COMPLETE: No errors detected.\n\n"])


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    db.add_all([
        models.NetworkDevice(hostname="sw1", ip_address="192.0.2.1", device_type="switch",
                             os_type="cisco", username="u", encrypted_password="x"),
        models.NetworkDevice(hostname="r1", ip_address="192.0.2.2", device_type="router",
                             os_type="mikrotik", username="u", encrypted_password="x"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(configuration.router)
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(configuration, "run_ansible_playbook", successful_stream)
    monkeypatch.setattr(configuration, "log_event", lambda **kwargs: None)
    with TestClient(app) as client:
        yield app, client, db
    db.close()


def simulate(app, client, role="viewer", body=None):
    app.dependency_overrides[auth.get_current_user] = lambda: user(role)
    return client.post("/configuration/simulate", json=body or payload(),
                       headers={"Authorization": "Bearer token"})


def test_viewer_simulation_creates_hashed_passed_record(env):
    app, client, db = env
    response = simulate(app, client)
    assert response.status_code == 200
    change_id = response.headers["x-vnms-change-id"]
    change = db.query(models.ConfigurationChange).filter_by(change_id=change_id).one()
    assert change.created_by == "viewer_user"
    assert change.status == "simulation_passed"
    assert change.simulation_success is True
    assert len(change.proposal_hash) == 64
    assert change.target_devices == ["sw1"]


def test_failed_simulation_is_persisted(env, monkeypatch):
    app, client, db = env
    monkeypatch.setattr(configuration, "run_ansible_playbook", lambda *a, **k: iter([
        "data: PLAY RECAP\n\n", "data: sw1 : unreachable=0 failed=1\n\n",
        "data: PLAYBOOK FINISHED WITH ERRORS.\n\n"]))
    response = simulate(app, client)
    change = db.query(models.ConfigurationChange).filter_by(
        change_id=response.headers["x-vnms-change-id"]).one()
    assert change.status == "simulation_failed"
    assert change.simulation_success is False


@pytest.mark.parametrize("body", [
    payload(("sw1", "sw1")),
    {**payload(), "config_text": json.dumps({"other": {"config": [], "exec": []}})},
])
def test_duplicate_or_divergent_targets_rejected(env, body):
    app, client, _ = env
    assert simulate(app, client, body=body).status_code == 400


def test_hash_is_deterministic_and_binds_deployment_data():
    config = {"sw1": {"config": ["a"], "exec": []}}
    first = configuration.proposal_hash(config, ["sw1"], "t")
    assert first == configuration.proposal_hash(config, ["sw1"], "t")
    assert first != configuration.proposal_hash({"sw1": {"config": ["b"], "exec": []}}, ["sw1"], "t")
    assert first != configuration.proposal_hash(config, ["sw1"], "other")

    hierarchy = {"sw1": {"config": [{
        "parents": ["interface GigabitEthernet0/1"],
        "lines": ["description ORIGINAL"],
    }], "exec": []}}
    hierarchy_hash = configuration.proposal_hash(hierarchy, ["sw1"], "t")
    changed_parent = {"sw1": {"config": [{
        "parents": ["interface GigabitEthernet0/2"],
        "lines": ["description ORIGINAL"],
    }], "exec": []}}
    changed_line = {"sw1": {"config": [{
        "parents": ["interface GigabitEthernet0/1"],
        "lines": ["description UPDATED"],
    }], "exec": []}}
    assert hierarchy_hash != configuration.proposal_hash(changed_parent, ["sw1"], "t")
    assert hierarchy_hash != configuration.proposal_hash(changed_line, ["sw1"], "t")


def test_push_authentication_and_viewer_rbac_precede_side_effects(env, monkeypatch):
    app, client, _ = env
    calls = []
    monkeypatch.setattr(configuration, "create_preconfiguration_backups", lambda d: calls.append(d))
    assert client.post("/configuration/push", json={"change_id": "x"}).status_code == 401
    app.dependency_overrides[auth.get_current_user] = lambda: user("viewer")
    assert client.post("/configuration/push", json={"change_id": "x"},
                       headers={"Authorization": "Bearer x"}).status_code == 403
    assert calls == []


def test_unknown_change_is_404(env):
    app, client, _ = env
    app.dependency_overrides[auth.get_current_user] = lambda: user("admin")
    assert client.post("/configuration/push", json={"change_id": "missing"},
                       headers={"Authorization": "Bearer x"}).status_code == 404


def test_admin_deploys_exact_stored_proposal_after_all_backups(env, monkeypatch):
    app, client, db = env
    response = simulate(app, client, role="admin")
    change_id = response.headers["x-vnms-change-id"]
    order, ansible_calls = [], []
    def backups(devices):
        order.append("backup")
        return ({"sw1": "Pre_Config_cisco_switch_sw1_20260807_153500.txt"},
                [{"hostname": "sw1", "success": True}])
    def ansible(config, devices, is_check_mode=True):
        order.append("ansible")
        ansible_calls.append((config, [d.hostname for d in devices], is_check_mode))
        return successful_stream()
    monkeypatch.setattr(configuration, "create_preconfiguration_backups", backups)
    monkeypatch.setattr(configuration, "run_ansible_playbook", ansible)
    result = client.post("/configuration/push", json={"change_id": change_id},
                         headers={"Authorization": "Bearer x"})
    assert result.status_code == 200
    assert order == ["backup", "ansible"]
    change = db.query(models.ConfigurationChange).filter_by(change_id=change_id).one()
    assert change.status == "deployed"
    assert change.pre_backup_files["sw1"].startswith("Pre_Config_cisco_switch_sw1_")
    assert ansible_calls == [(change.config_payload, ["sw1"], False)]
    replay = client.post("/configuration/push", json={"change_id": change_id},
                         headers={"Authorization": "Bearer x"})
    assert replay.status_code == 409


def test_push_schema_rejects_replacement_payload(env):
    app, client, _ = env
    app.dependency_overrides[auth.get_current_user] = lambda: user("admin")
    response = client.post("/configuration/push", json=payload(),
                           headers={"Authorization": "Bearer x"})
    assert response.status_code == 422
    assert client.post("/configuration/push", json={"change_id": "x", "config_text": "{}"},
                       headers={"Authorization": "Bearer x"}).status_code == 422


def test_preconfiguration_backup_uses_existing_filename_format(tmp_path, monkeypatch):
    device = SimpleNamespace(hostname="SW1", os_type="cisco", device_type="switch")
    monkeypatch.setattr(backup_service, "capture_running_configuration",
                        lambda d: {"hostname": d.hostname, "success": True, "config": "version 1"})
    files, results = backup_service.create_preconfiguration_backups(
        [device], str(tmp_path), now=SimpleNamespace(strftime=lambda fmt: "20260807_153500"))
    assert results[0]["success"] is True
    assert files == {"SW1": "Pre_Config_cisco_switch_SW1_20260807_153500.txt"}
    assert (tmp_path / files["SW1"]).read_text() == "version 1"


def test_hash_mismatch_blocks_backup_and_ansible(env, monkeypatch):
    app, client, db = env
    response = simulate(app, client, role="admin")
    change = db.query(models.ConfigurationChange).filter_by(
        change_id=response.headers["x-vnms-change-id"]).one()
    change.config_payload = {"sw1": {"config": ["tampered"], "exec": []}}
    db.commit()
    calls = []
    monkeypatch.setattr(configuration, "create_preconfiguration_backups", lambda d: calls.append("backup"))
    monkeypatch.setattr(configuration, "run_ansible_playbook", lambda *a, **k: calls.append("ansible"))
    result = client.post("/configuration/push", json={"change_id": change.change_id},
                         headers={"Authorization": "Bearer x"})
    assert result.status_code == 409
    assert calls == []


def test_failed_simulation_override_validation_and_success(env, monkeypatch):
    app, client, db = env
    monkeypatch.setattr(configuration, "run_ansible_playbook", lambda *a, **k: iter([
        "data: PLAY RECAP\n\n", "data: sw1 : failed=1 unreachable=0\n\n"]))
    response = simulate(app, client, role="admin")
    change_id = response.headers["x-vnms-change-id"]
    app.dependency_overrides[auth.get_current_user] = lambda: user("admin")
    headers = {"Authorization": "Bearer x"}
    assert client.post("/configuration/push", json={"change_id": change_id}, headers=headers).status_code == 409
    endpoint = f"/configuration/changes/{change_id}/override-simulation"
    assert client.post(endpoint, json={"override_reason": "short"}, headers=headers).status_code == 422
    side_effects, audit_events = [], []
    monkeypatch.setattr(configuration, "create_preconfiguration_backups", lambda d: side_effects.append("backup"))
    monkeypatch.setattr(configuration, "run_ansible_playbook", lambda *a, **k: side_effects.append("ansible"))
    monkeypatch.setattr(configuration, "log_event", lambda **kwargs: audit_events.append(kwargs))
    result = client.post(endpoint, json={
        "override_reason": "Check mode unsupported in validated lab."}, headers=headers)
    assert result.status_code == 200
    assert result.json()["status"] == "admin_override_authorized"
    assert side_effects == []
    assert audit_events[-1]["severity"] == "WARNING"
    change = db.query(models.ConfigurationChange).filter_by(change_id=change_id).one()
    assert change.status == "admin_override_authorized"
    assert change.simulation_override is True
    assert change.simulation_override_by == "admin_user"

    monkeypatch.setattr(configuration, "create_preconfiguration_backups", lambda d: (
        {"sw1": "Pre_Config_cisco_switch_sw1_20260807_153500.txt"},
        [{"hostname": "sw1", "success": True}]))
    monkeypatch.setattr(configuration, "run_ansible_playbook", successful_stream)
    result = client.post("/configuration/push", json={"change_id": change_id}, headers=headers)
    assert result.status_code == 200


def test_viewer_cannot_authorize_override_and_nonfailed_cannot_be_overridden(env, monkeypatch):
    app, client, _ = env
    passed = simulate(app, client, role="admin")
    passed_id = passed.headers["x-vnms-change-id"]
    app.dependency_overrides[auth.get_current_user] = lambda: user("admin")
    headers = {"Authorization": "Bearer x"}
    endpoint = f"/configuration/changes/{passed_id}/override-simulation"
    assert client.post(endpoint, json={"override_reason": "A sufficiently long reason."}, headers=headers).status_code == 409

    monkeypatch.setattr(configuration, "run_ansible_playbook", lambda *a, **k: iter([
        "data: PLAY RECAP\n\n", "data: sw1 : failed=1 unreachable=0\n\n"]))
    failed = simulate(app, client, role="admin")
    app.dependency_overrides[auth.get_current_user] = lambda: user("viewer")
    endpoint = f"/configuration/changes/{failed.headers['x-vnms-change-id']}/override-simulation"
    assert client.post(endpoint, json={"override_reason": "A sufficiently long reason."}, headers=headers).status_code == 403


def test_any_backup_failure_blocks_live_ansible_and_preserves_mapping(env, monkeypatch):
    app, client, db = env
    response = simulate(app, client, role="admin", body=payload(("sw1", "r1")))
    change_id = response.headers["x-vnms-change-id"]
    app.dependency_overrides[auth.get_current_user] = lambda: user("admin")
    live_calls = []
    monkeypatch.setattr(configuration, "create_preconfiguration_backups", lambda d: (
        {"sw1": "Pre_Config_cisco_switch_sw1_20260807_153500.txt"},
        [{"hostname": "sw1", "success": True}, {"hostname": "r1", "success": False, "error": "timeout"}]))
    monkeypatch.setattr(configuration, "run_ansible_playbook", lambda *a, **k: live_calls.append(True))
    result = client.post("/configuration/push", json={"change_id": change_id},
                         headers={"Authorization": "Bearer x"})
    assert result.status_code == 502
    change = db.query(models.ConfigurationChange).filter_by(change_id=change_id).one()
    assert change.status == "pre_backup_failed"
    assert change.pre_backup_files["sw1"].startswith("Pre_Config_")
    assert live_calls == []


def test_failed_production_is_persisted_and_cannot_be_replayed(env, monkeypatch):
    app, client, db = env
    response = simulate(app, client, role="admin")
    change_id = response.headers["x-vnms-change-id"]
    app.dependency_overrides[auth.get_current_user] = lambda: user("admin")
    monkeypatch.setattr(configuration, "create_preconfiguration_backups", lambda d: (
        {"sw1": "Pre_Config_cisco_switch_sw1_20260807_153500.txt"},
        [{"hostname": "sw1", "success": True}],
    ))
    monkeypatch.setattr(configuration, "run_ansible_playbook", lambda *a, **k: iter([
        "data: PLAY RECAP\n\n",
        "data: sw1 : ok=0 changed=0 unreachable=0 failed=1\n\n",
        "data: PLAYBOOK FINISHED WITH ERRORS.\n\n",
    ]))

    result = client.post(
        "/configuration/push",
        json={"change_id": change_id},
        headers={"Authorization": "Bearer x"},
    )
    assert result.status_code == 200
    change = db.query(models.ConfigurationChange).filter_by(change_id=change_id).one()
    assert change.status == "deployment_failed"

    replay = client.post(
        "/configuration/push",
        json={"change_id": change_id},
        headers={"Authorization": "Bearer x"},
    )
    assert replay.status_code == 409
