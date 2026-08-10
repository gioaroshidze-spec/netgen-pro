import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import ansible_engine
from routers import configuration


def device(hostname="sw1", os_type="cisco"):
    return SimpleNamespace(hostname=hostname, os_type=os_type)


def host_payload(config, exec_commands=None):
    return {"config": config, "exec": exec_commands or []}


def validate(config, os_type="cisco", exec_commands=None):
    payload = {"sw1": host_payload(config, exec_commands)}
    configuration.validate_ansible_payload(payload, [device(os_type=os_type)])
    return payload


def test_global_cisco_strings_and_explicit_blocks_are_accepted():
    payload = validate([
        "hostname NEW-SW1",
        "vlan 123",
        {
            "parents": ["interface GigabitEthernet0/1"],
            "lines": ["description VNMS_PHASE2_TRANSPORT_TEST"],
        },
        {
            "parents": ["vlan 123"],
            "lines": ["name USERS"],
        },
    ])
    assert payload["sw1"]["config"][0] == "hostname NEW-SW1"


@pytest.mark.parametrize(
    ("block", "message"),
    [
        ({"parents": [], "lines": ["description TEST"]}, "parents"),
        ({"parents": ["interface GigabitEthernet0/1"], "lines": []}, "lines"),
        ({"parents": ["   "], "lines": ["description TEST"]}, "must not be blank"),
        ({"parents": ["interface GigabitEthernet0/1"], "lines": [""]}, "must not be blank"),
        (
            {
                "parents": ["interface GigabitEthernet0/1"],
                "lines": ["description TEST"],
                "before": ["show run"],
            },
            "exactly 'parents' and 'lines'",
        ),
        (
            {"parents": ["interface GigabitEthernet0/1"], "lines": [{"raw": "x"}]},
            "must be a string",
        ),
    ],
)
def test_invalid_cisco_blocks_are_rejected(block, message):
    with pytest.raises(ValueError, match=message):
        validate([block])


@pytest.mark.parametrize(
    "command",
    [
        "hostname SW1\nend",
        "conf t",
        "configure terminal",
        "exit",
        "end",
    ],
)
def test_injected_or_context_changing_config_commands_are_rejected(command):
    with pytest.raises(ValueError):
        validate([command])


@pytest.mark.parametrize("command", ["description OLD", "name USERS", "network 10.0.0.0 0.0.0.255 area 0"])
def test_flat_cisco_hierarchical_commands_fail_closed(command):
    with pytest.raises(ValueError, match="requires explicit hierarchy"):
        validate(["interface GigabitEthernet0/1", command])


@pytest.mark.parametrize(
    "exec_commands",
    [
        ["show run", {"raw": "show clock"}],
        ["show run\nreload"],
        ["conf t"],
        ["exit"],
    ],
)
def test_exec_commands_remain_strict_strings(exec_commands):
    with pytest.raises(ValueError):
        validate([], exec_commands=exec_commands)


def test_structured_blocks_are_rejected_for_flat_only_vendors():
    with pytest.raises(ValueError, match="only supported for Cisco IOS"):
        validate(
            [{
                "parents": ["interface 1/1/1"],
                "lines": ["description TEST"],
            }],
            os_type="aruba",
        )


def test_legacy_flat_template_fails_before_ansible_process_starts(monkeypatch):
    proposal = {"sw1": host_payload([
        "interface GigabitEthernet0/1",
        "description OLD",
    ])}
    process_started = []
    monkeypatch.setattr(
        ansible_engine.subprocess,
        "Popen",
        lambda *args, **kwargs: process_started.append(True),
    )

    with pytest.raises(ValueError, match="requires explicit hierarchy"):
        list(ansible_engine.run_ansible_playbook(proposal, [device()]))
    assert process_started == []


def test_cisco_normalization_is_deterministic_and_non_mutating():
    payload = host_payload([
        "hostname NEW-SW1",
        {
            "parents": ["interface GigabitEthernet0/1"],
            "lines": ["description CAMERA"],
        },
        {
            "parents": ["router ospf 10", "address-family ipv4"],
            "lines": ["network 10.0.0.0 0.0.0.255 area 0"],
        },
        {
            "parents": ["interface GigabitEthernet0/2"],
            "lines": ["description USERS"],
        },
    ], ["write memory"])
    original = copy.deepcopy(payload)

    normalized = ansible_engine.normalize_device_config_for_ansible(
        device(), payload
    )

    assert normalized["cisco_global_lines"] == ["hostname NEW-SW1"]
    assert normalized["cisco_config_blocks"] == [
        {
            "parents": ["interface GigabitEthernet0/1"],
            "lines": ["description CAMERA"],
        },
        {
            "parents": ["router ospf 10", "address-family ipv4"],
            "lines": ["network 10.0.0.0 0.0.0.255 area 0"],
        },
        {
            "parents": ["interface GigabitEthernet0/2"],
            "lines": ["description USERS"],
        },
    ]
    assert normalized["exec"] == ["write memory"]
    assert payload == original
    assert normalized["cisco_config_blocks"][0] is not payload["config"][1]


class _FakeStdout:
    def __iter__(self):
        return iter(())

    def close(self):
        pass


class _FakeProcess:
    def __init__(self):
        self.stdout = _FakeStdout()
        self.returncode = 0

    def wait(self):
        return self.returncode


def test_check_and_live_runs_share_identical_normalization_and_tasks(monkeypatch):
    proposal = {"sw1": host_payload([
        "hostname NEW-SW1",
        {
            "parents": ["interface GigabitEthernet0/1"],
            "lines": ["description TEST"],
        },
    ])}
    original = copy.deepcopy(proposal)
    target = device()
    normalization_calls = []
    executions = []
    real_normalize = ansible_engine.normalize_ansible_payload

    def record_normalization(payload, devices):
        normalization_calls.append(copy.deepcopy(payload))
        return real_normalize(payload, devices)

    def fake_popen(command, **kwargs):
        playbook_path = Path(command[3])
        executions.append({
            "command": list(command),
            "vars": json.loads(playbook_path.with_name("vars.json").read_text()),
            "playbook": playbook_path.read_text(),
        })
        return _FakeProcess()

    monkeypatch.setattr(ansible_engine, "normalize_ansible_payload", record_normalization)
    monkeypatch.setattr(ansible_engine, "write_ansible_inventory", lambda *args: {})
    monkeypatch.setattr(ansible_engine.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ansible_engine.ansible_logger, "info", lambda *args: None)
    monkeypatch.setattr(ansible_engine.ansible_logger, "error", lambda *args: None)

    list(ansible_engine.run_ansible_playbook(proposal, [target], is_check_mode=True))
    list(ansible_engine.run_ansible_playbook(proposal, [target], is_check_mode=False))
    list(ansible_engine.run_ansible_playbook(
        proposal, [target], execution_mode="verification"
    ))

    assert normalization_calls == [original, original, original]
    assert executions[0]["vars"] == executions[1]["vars"] == executions[2]["vars"]
    assert executions[0]["playbook"] == executions[1]["playbook"] == executions[2]["playbook"]
    assert yaml.safe_load(executions[0]["playbook"])[0]["tasks"]
    assert "--check" in executions[0]["command"]
    assert "--check" not in executions[1]["command"]
    assert "--check" in executions[2]["command"]
    assert executions[0]["command"][:2] == executions[1]["command"][:2]
    assert executions[0]["command"][4:-1] == executions[1]["command"][4:]
    assert Path(executions[0]["command"][2]).name == "inventory.yaml"
    assert Path(executions[1]["command"][2]).name == "inventory.yaml"
    assert Path(executions[0]["command"][3]).name == "playbook.yaml"
    assert Path(executions[1]["command"][3]).name == "playbook.yaml"
    assert "parents: \"{{ item.parents }}\"" in executions[0]["playbook"]
    assert "cisco_global_lines" in executions[0]["playbook"]
    assert "not ansible_check_mode" in executions[2]["playbook"]
    assert proposal == original


def test_ai_prompt_requires_explicit_cisco_hierarchy(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        message = SimpleNamespace(content='{"sw1": {"config": [], "exec": []}}')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(configuration, "completion", fake_completion)
    request = SimpleNamespace(
        prompt="Describe interface GigabitEthernet0/1",
        switches=[],
        routers=[],
        base_template=None,
    )
    result = configuration.generate_configuration(
        request, db=None, current_user=SimpleNamespace(username="viewer")
    )
    system_prompt = captured["messages"][0]["content"]

    assert result["status"] == "success"
    assert '"parents": ["interface GigabitEthernet0/1"]' in system_prompt
    assert '"lines": ["description VNMS_PHASE2_TRANSPORT_TEST"]' in system_prompt
    assert '"config": ["vlan 123"]' in system_prompt
    assert '"parents": ["vlan 123"]' in system_prompt
    assert "never put 'write memory' in 'config'" in system_prompt
