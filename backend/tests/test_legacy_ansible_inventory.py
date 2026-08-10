from types import SimpleNamespace

import yaml

import connection_utils
from ansible_engine import build_ansible_inventory, write_ansible_inventory


FORBIDDEN_LEGACY_ALGORITHMS = (
    "hmac-sha1",
    "hmac-sha1-96",
    "diffie-hellman-group1-sha1",
    "ssh-dss",
)


def device(is_legacy, hostname="SW1"):
    return SimpleNamespace(
        hostname=hostname, ip_address="192.0.2.10", username="operator",
        encrypted_password="encrypted", os_type="cisco",
        device_type="switch", is_legacy=is_legacy,
    )


def assert_no_explicit_weak_algorithms(variables):
    serialized_values = " ".join(str(value) for value in variables.values())
    for algorithm in FORBIDDEN_LEGACY_ALGORITHMS:
        assert algorithm not in serialized_values


def test_modern_device_uses_default_transport_without_legacy_overrides(monkeypatch):
    monkeypatch.setattr(connection_utils, "decrypt_secret", lambda value: "password")
    variables = connection_utils.get_ansible_inventory_vars(device(False))
    assert "ansible_network_cli_ssh_type" not in variables
    assert "ansible_libssh_key_exchange_algorithms" not in variables
    assert "ansible_libssh_hostkeys" not in variables
    assert_no_explicit_weak_algorithms(variables)


def test_legacy_device_uses_paramiko_without_libssh_or_weak_algorithm_overrides(monkeypatch):
    monkeypatch.setattr(connection_utils, "decrypt_secret", lambda value: "password")
    variables = connection_utils.get_ansible_inventory_vars(device(True))
    assert variables["ansible_network_cli_ssh_type"] == "paramiko"
    assert "ansible_libssh_key_exchange_algorithms" not in variables
    assert "ansible_libssh_hostkeys" not in variables
    assert_no_explicit_weak_algorithms(variables)


def test_inventory_serialization_preserves_legacy_values(tmp_path, monkeypatch):
    monkeypatch.setattr(connection_utils, "decrypt_secret", lambda value: "password")
    path = tmp_path / "inventory.yaml"
    write_ansible_inventory(path, [device(True)])
    loaded = yaml.safe_load(path.read_text())
    variables = loaded["all"]["hosts"]["SW1"]
    assert variables["ansible_network_cli_ssh_type"] == "paramiko"
    assert "ansible_libssh_key_exchange_algorithms" not in variables
    assert "ansible_libssh_hostkeys" not in variables
    assert variables["ansible_host"] == "192.0.2.10"
    assert variables["ansible_user"] == "operator"
    assert variables["ansible_network_os"] == "cisco.ios.ios"
    assert variables["ansible_connection"] == "network_cli"
    assert variables["ansible_become"] == "yes"
    assert variables["ansible_become_method"] == "enable"
    assert_no_explicit_weak_algorithms(variables)


def test_mixed_inventory_applies_compatibility_transport_per_device(monkeypatch):
    monkeypatch.setattr(connection_utils, "decrypt_secret", lambda value: "password")
    inventory = build_ansible_inventory([
        device(False, hostname="modern_sw"),
        device(True, hostname="legacy_sw"),
    ])

    modern_variables = inventory["all"]["hosts"]["modern_sw"]
    legacy_variables = inventory["all"]["hosts"]["legacy_sw"]
    assert "ansible_network_cli_ssh_type" not in modern_variables
    assert legacy_variables["ansible_network_cli_ssh_type"] == "paramiko"
    assert "ansible_libssh_key_exchange_algorithms" not in modern_variables
    assert "ansible_libssh_key_exchange_algorithms" not in legacy_variables
    assert "ansible_libssh_hostkeys" not in modern_variables
    assert "ansible_libssh_hostkeys" not in legacy_variables
