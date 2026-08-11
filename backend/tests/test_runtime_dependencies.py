from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_pins_validated_ansible_runtime_and_collections():
    dockerfile = (REPOSITORY_ROOT / "Dockerfile.backend").read_text()

    assert "RUN pipx install --include-deps ansible==14.2.0" in dockerfile
    assert (
        "RUN pipx inject --force ansible ansible-core==2.21.2 paramiko==4.0.0 "
        "ansible-pylibssh==1.4.0 scp==0.16.1"
        in dockerfile
    )
    assert "metadata.version('ansible-core') == '2.21.2'" in dockerfile
    assert "paramiko.__version__ == '4.0.0'" in dockerfile
    assert "import scp" in dockerfile
    assert "metadata.version('scp') == '0.16.1'" in dockerfile
    assert "scp.__file__.startswith('/opt/pipx/venvs/ansible/')" in dockerfile
    assert "'diffie-hellman-group14-sha1' in paramiko.Transport._preferred_kex" in dockerfile
    assert "'ssh-rsa' in paramiko.Transport._preferred_keys" in dockerfile
    assert "'ansible.netcommon:==8.6.0'" in dockerfile
    assert "'cisco.ios:==11.4.2'" in dockerfile


def test_backend_network_libraries_are_pinned_to_validated_versions():
    requirements = (
        REPOSITORY_ROOT / "backend" / "requirements.txt"
    ).read_text().splitlines()

    assert "netmiko==4.6.0" in requirements
    assert "paramiko==4.0.0" in requirements
    assert not any(line.startswith("netmiko>") for line in requirements)
    assert not any(line.startswith("paramiko>") for line in requirements)
