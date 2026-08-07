from types import SimpleNamespace

import yaml

import connection_utils
from ansible_engine import write_ansible_inventory


def device(is_legacy):
    return SimpleNamespace(
        hostname="SW1", ip_address="192.0.2.10", username="operator",
        encrypted_password="encrypted", os_type="cisco",
        device_type="switch", is_legacy=is_legacy,
    )


def test_modern_device_does_not_enable_sha1(monkeypatch):
    monkeypatch.setattr(connection_utils, "decrypt_secret", lambda value: "password")
    variables = connection_utils.get_ansible_inventory_vars(device(False))
    assert "ansible_network_cli_ssh_type" not in variables
    assert "ansible_libssh_key_exchange_algorithms" not in variables
    assert "ansible_libssh_hostkeys" not in variables


def test_legacy_device_gets_minimal_group14_libssh_compatibility(monkeypatch):
    monkeypatch.setattr(connection_utils, "decrypt_secret", lambda value: "password")
    variables = connection_utils.get_ansible_inventory_vars(device(True))
    assert variables["ansible_network_cli_ssh_type"] == "libssh"
    assert variables["ansible_libssh_key_exchange_algorithms"] == "+diffie-hellman-group14-sha1"
    assert variables["ansible_libssh_hostkeys"] == "ssh-rsa"
    assert "diffie-hellman-group1-sha1" not in variables["ansible_libssh_key_exchange_algorithms"]
    assert "ssh-dss" not in variables["ansible_libssh_hostkeys"]


def test_inventory_serialization_preserves_legacy_values(tmp_path, monkeypatch):
    monkeypatch.setattr(connection_utils, "decrypt_secret", lambda value: "password")
    path = tmp_path / "inventory.yaml"
    write_ansible_inventory(path, [device(True)])
    loaded = yaml.safe_load(path.read_text())
    variables = loaded["all"]["hosts"]["SW1"]
    assert variables["ansible_network_cli_ssh_type"] == "libssh"
    assert variables["ansible_libssh_key_exchange_algorithms"] == "+diffie-hellman-group14-sha1"
    assert variables["ansible_libssh_hostkeys"] == "ssh-rsa"
    assert "ssh-dss" not in variables["ansible_libssh_hostkeys"]
    assert "diffie-hellman-group1-sha1" not in variables["ansible_libssh_key_exchange_algorithms"]
