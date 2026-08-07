import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from database import get_db
from routers import auth, configuration


class FakeQuery:
    def __init__(self, results):
        self.results = results

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.results

    def first(self):
        return self.results[0] if self.results else None


class FakeDB:
    def __init__(self, devices=None):
        self.devices = devices or []

    def query(self, model):
        if model is models.NetworkDevice:
            return FakeQuery(self.devices)
        return FakeQuery([])


def make_user(role):
    return SimpleNamespace(id=1, username=f"{role}_user", role=role)


def make_device(hostname="sw1"):
    return SimpleNamespace(
        hostname=hostname,
        ip_address="192.0.2.10",
        device_type="switch",
        os_type="cisco",
    )


def request_payload():
    config = {"sw1": {"config": ["interface Gi1/0/1"], "exec": []}}
    return {
        "prompt": "configure test interface",
        "config_text": json.dumps(config),
        "switches": ["sw1"],
        "routers": [],
        "source_template": "approved-template",
    }


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(configuration.router)
    app.dependency_overrides[get_db] = lambda: FakeDB([make_device()])
    monkeypatch.setattr(configuration, "log_event", lambda **kwargs: None)

    with TestClient(app) as test_client:
        yield app, test_client

    app.dependency_overrides.clear()


def test_push_without_authentication_returns_401(client):
    _, test_client = client

    response = test_client.post("/configuration/push", json=request_payload())

    assert response.status_code == 401


def test_push_as_viewer_returns_403_before_ansible(client, monkeypatch):
    app, test_client = client
    app.dependency_overrides[auth.get_current_user] = lambda: make_user("viewer")
    calls = []

    def fake_run_ansible_playbook(*args, **kwargs):
        calls.append((args, kwargs))
        return iter(["data: should not run\n\n"])

    monkeypatch.setattr(configuration, "run_ansible_playbook", fake_run_ansible_playbook)

    response = test_client.post(
        "/configuration/push",
        json=request_payload(),
        headers={"Authorization": "Bearer viewer-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Administrator privileges required."
    assert calls == []


def test_push_as_admin_reaches_mocked_execution_boundary(client, monkeypatch):
    app, test_client = client
    app.dependency_overrides[auth.get_current_user] = lambda: make_user("admin")
    calls = []

    def fake_run_ansible_playbook(ai_config_data, devices, is_check_mode=True):
        calls.append({
            "ai_config_data": ai_config_data,
            "devices": devices,
            "is_check_mode": is_check_mode,
        })
        return iter(["data: PLAY RECAP\n", "data: sw1 : ok=1 failed=0 unreachable=0\n\n"])

    monkeypatch.setattr(configuration, "run_ansible_playbook", fake_run_ansible_playbook)

    response = test_client.post(
        "/configuration/push",
        json=request_payload(),
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert calls
    assert calls[0]["is_check_mode"] is False
    assert calls[0]["devices"][0].hostname == "sw1"


def test_simulate_remains_accessible_to_viewer(client, monkeypatch):
    app, test_client = client
    app.dependency_overrides[auth.get_current_user] = lambda: make_user("viewer")
    calls = []

    def fake_run_ansible_playbook(ai_config_data, devices, is_check_mode=True):
        calls.append({"is_check_mode": is_check_mode, "devices": devices})
        return iter(["data: simulation complete\n\n"])

    monkeypatch.setattr(configuration, "run_ansible_playbook", fake_run_ansible_playbook)

    response = test_client.post(
        "/configuration/simulate",
        json=request_payload(),
        headers={"Authorization": "Bearer viewer-token"},
    )

    assert response.status_code == 200
    assert calls
    assert calls[0]["is_check_mode"] is True


def test_generate_remains_protected_by_authentication(client, monkeypatch):
    _, test_client = client
    ai_calls = []

    def fake_completion(*args, **kwargs):
        ai_calls.append((args, kwargs))
        return None

    monkeypatch.setattr(configuration, "completion", fake_completion)

    response = test_client.post(
        "/configuration/generate",
        json={
            "prompt": "create vlan 10",
            "switches": [],
            "routers": [],
            "base_template": None,
        },
    )

    assert response.status_code == 401
    assert ai_calls == []
