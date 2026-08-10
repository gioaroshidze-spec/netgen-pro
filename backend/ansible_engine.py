import tempfile
import subprocess
import json
import os
import logging
import yaml

# --- INITIALIZE DEDICATED ANSIBLE LOGGER ---
# We create a specific logger for Ansible and stop it from leaking into backend.log
ansible_logger = logging.getLogger("ansible_execution")
ansible_logger.setLevel(logging.INFO)
ansible_logger.propagate = False 

# Ensure we don't attach duplicate handlers if the module reloads
if not ansible_logger.handlers:
    ansible_handler = logging.FileHandler("ansible.log")
    ansible_formatter = logging.Formatter('%(asctime)s - [ANSIBLE] - %(message)s')
    ansible_handler.setFormatter(ansible_formatter)
    ansible_logger.addHandler(ansible_handler)

# --- THE SURGICAL INCISION: Import our central connection wrapper ---
from connection_utils import get_ansible_inventory_vars

_HOST_PAYLOAD_KEYS = {"config", "exec"}
_CONFIG_BLOCK_KEYS = {"parents", "lines"}
_CONTEXT_CONTROL_COMMANDS = {"conf t", "configure terminal", "exit", "end"}
_CISCO_HIERARCHICAL_ONLY_PREFIXES = (
    "address-family",
    "area",
    "channel-group",
    "class",
    "deny",
    "description",
    "duplex",
    "encapsulation",
    "ip address",
    "ipv6 address",
    "login",
    "name",
    "neighbor",
    "network",
    "no shutdown",
    "passive-interface",
    "password",
    "permit",
    "redistribute",
    "remark",
    "service-policy",
    "shutdown",
    "speed",
    "switchport",
    "transport input",
)


def _validate_command(command, location, reject_context_control=False):
    if not isinstance(command, str):
        raise ValueError(f"{location} must be a string.")
    if not command.strip():
        raise ValueError(f"{location} must not be blank.")
    if "\n" in command or "\r" in command:
        raise ValueError(f"{location} must not contain newline characters.")

    normalized = " ".join(command.casefold().split())
    if reject_context_control and normalized in _CONTEXT_CONTROL_COMMANDS:
        raise ValueError(
            f"{location} must not manipulate configuration context with '{command.strip()}'."
        )
    return command


def _requires_cisco_hierarchy(command):
    normalized = " ".join(command.casefold().split())
    return any(
        normalized == prefix or normalized.startswith(f"{prefix} ")
        for prefix in _CISCO_HIERARCHICAL_ONLY_PREFIXES
    )


def normalize_device_config_for_ansible(device, host_payload):
    """
    Validate and copy one host payload into the exact structure consumed by
    Ansible. Cisco hierarchy is explicit; other vendors remain flat-string only.
    """
    hostname = device.hostname
    if not isinstance(host_payload, dict):
        raise ValueError(f"Data for host '{hostname}' must be a JSON object.")
    if set(host_payload) != _HOST_PAYLOAD_KEYS:
        raise ValueError(
            f"Host '{hostname}' must contain exactly 'config' and 'exec'."
        )

    config_items = host_payload["config"]
    exec_items = host_payload["exec"]
    if not isinstance(config_items, list):
        raise ValueError(f"Host '{hostname}' is missing a valid 'config' list.")
    if not isinstance(exec_items, list):
        raise ValueError(f"Host '{hostname}' is missing a valid 'exec' list.")

    normalized_exec = [
        _validate_command(
            command,
            f"Exec command {index} for host '{hostname}'",
            reject_context_control=True,
        )
        for index, command in enumerate(exec_items)
    ]
    os_type = (device.os_type or "cisco").lower()

    if os_type != "cisco":
        normalized_config = []
        for index, item in enumerate(config_items):
            if not isinstance(item, str):
                raise ValueError(
                    f"Structured config blocks are only supported for Cisco IOS; "
                    f"config item {index} for host '{hostname}' must be a string."
                )
            normalized_config.append(
                _validate_command(
                    item,
                    f"Config command {index} for host '{hostname}'",
                    reject_context_control=True,
                )
            )
        return {"config": normalized_config, "exec": normalized_exec}

    global_lines = []
    config_blocks = []
    for index, item in enumerate(config_items):
        location = f"Cisco config item {index} for host '{hostname}'"
        if isinstance(item, str):
            command = _validate_command(
                item, location, reject_context_control=True
            )
            if _requires_cisco_hierarchy(command):
                raise ValueError(
                    f"{location} requires explicit hierarchy; use a "
                    "{'parents': [...], 'lines': [...]} block."
                )
            global_lines.append(command)
            continue

        if not isinstance(item, dict):
            raise ValueError(
                f"{location} must be a global command string or a hierarchy block."
            )
        if set(item) != _CONFIG_BLOCK_KEYS:
            raise ValueError(
                f"{location} must contain exactly 'parents' and 'lines'."
            )

        parents = item["parents"]
        lines = item["lines"]
        if not isinstance(parents, list) or not parents:
            raise ValueError(f"{location} has an invalid or empty 'parents' list.")
        if not isinstance(lines, list) or not lines:
            raise ValueError(f"{location} has an invalid or empty 'lines' list.")

        normalized_parents = [
            _validate_command(
                parent,
                f"Parent {parent_index} in {location}",
                reject_context_control=True,
            )
            for parent_index, parent in enumerate(parents)
        ]
        normalized_lines = [
            _validate_command(
                line,
                f"Line {line_index} in {location}",
                reject_context_control=True,
            )
            for line_index, line in enumerate(lines)
        ]
        config_blocks.append({
            "parents": normalized_parents,
            "lines": normalized_lines,
        })

    return {
        "cisco_global_lines": global_lines,
        "cisco_config_blocks": config_blocks,
        "exec": normalized_exec,
    }


def normalize_ansible_payload(ai_config_data, devices):
    if not isinstance(ai_config_data, dict):
        raise ValueError(
            "Root payload must be a JSON object mapping hostnames to commands."
        )

    devices_by_hostname = {device.hostname: device for device in devices}
    if set(ai_config_data) != set(devices_by_hostname):
        raise ValueError("Configuration hostnames must exactly match target devices.")

    return {
        hostname: normalize_device_config_for_ansible(
            device, ai_config_data[hostname]
        )
        for hostname, device in devices_by_hostname.items()
    }


def build_ansible_inventory(devices):
    return {
        "all": {
            "hosts": {
                device.hostname: get_ansible_inventory_vars(device)
                for device in devices
            }
        }
    }

def write_ansible_inventory(path, devices):
    inventory = build_ansible_inventory(devices)
    with open(path, "w", encoding="utf-8") as inventory_file:
        yaml.safe_dump(inventory, inventory_file, sort_keys=False)
    return inventory

def run_ansible_playbook(ai_config_data, devices, is_check_mode=True, execution_mode=None):
    """
    Executes Ansible, dynamically builds OS-specific task blocks, and streams output.
    All stdout/stderr is now silently trapped into ansible.log.
    """
    execution_mode = execution_mode or ("simulation" if is_check_mode else "production")
    if execution_mode not in {"simulation", "production", "verification"}:
        raise ValueError(f"Unsupported Ansible execution mode: {execution_mode}")
    is_check_mode = execution_mode in {"simulation", "verification"}
    normalized_config_data = normalize_ansible_payload(ai_config_data, devices)

    with tempfile.TemporaryDirectory() as temp_dir:
        inventory_path = os.path.join(temp_dir, "inventory.yaml")
        playbook_path = os.path.join(temp_dir, "playbook.yaml")
        vars_path = os.path.join(temp_dir, "vars.json")

        with open(vars_path, 'w') as f:
            json.dump({"ai_config": normalized_config_data}, f)

        os_types_present = set()

        # 1. BUILD MULTI-VENDOR INVENTORY USING CENTRAL WRAPPER
        for dev in devices:
            os_type = (dev.os_type or "cisco").lower()
            os_types_present.add(os_type)
            
            # The wrapper handles the MikroTik +cte1024w trick and privilege escalation
        write_ansible_inventory(inventory_path, devices)

        # 2. DYNAMICALLY GENERATE PLAYBOOK TASKS
        tasks_yaml = ""
        
        if "cisco" in os_types_present:
            tasks_yaml += """
    - name: (CISCO) Apply Global Configuration
      cisco.ios.ios_config:
        lines: "{{ ai_config[inventory_hostname]['cisco_global_lines'] }}"
      when:
        - inventory_hostname in ai_config
        - ansible_network_os == 'cisco.ios.ios'
        - ai_config[inventory_hostname]['cisco_global_lines'] | length > 0

    - name: (CISCO) Apply Hierarchical Configuration
      cisco.ios.ios_config:
        parents: "{{ item.parents }}"
        lines: "{{ item.lines }}"
      loop: "{{ ai_config[inventory_hostname]['cisco_config_blocks'] }}"
      when:
        - inventory_hostname in ai_config
        - ansible_network_os == 'cisco.ios.ios'

    - name: (CISCO) Run Exec Commands
      cisco.ios.ios_command:
        commands: "{{ ai_config[inventory_hostname]['exec'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'cisco.ios.ios' and not ansible_check_mode
"""

        if "aruba" in os_types_present:
            tasks_yaml += """
    - name: (ARUBA AOS-CX) Apply Configuration
      arubanetworks.aoscx.aoscx_config:
        lines: "{{ ai_config[inventory_hostname]['config'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'arubanetworks.aoscx.aoscx'

    - name: (ARUBA AOS-CX) Run Exec Commands
      arubanetworks.aoscx.aoscx_command:
        commands: "{{ ai_config[inventory_hostname]['exec'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'arubanetworks.aoscx.aoscx' and not ansible_check_mode
"""

        if "hpe" in os_types_present:
            tasks_yaml += """
    - name: (HPE PROVISION) Apply Configuration
      community.network.aruba_config:
        lines: "{{ ai_config[inventory_hostname]['config'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'community.network.aruba'

    - name: (HPE PROVISION) Run Exec Commands
      community.network.aruba_command:
        commands: "{{ ai_config[inventory_hostname]['exec'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'community.network.aruba' and not ansible_check_mode
"""

        if "mikrotik" in os_types_present:
            tasks_yaml += """
    - name: (MIKROTIK) Apply Configuration Commands
      community.routeros.command:
        commands: "{{ ai_config[inventory_hostname]['config'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'community.routeros.routeros' and not ansible_check_mode

    - name: (MIKROTIK) Run Exec Commands
      community.routeros.command:
        commands: "{{ ai_config[inventory_hostname]['exec'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'community.routeros.routeros' and not ansible_check_mode
"""

        if "alcatel" in os_types_present or "alcatel-lucent" in os_types_present:
            tasks_yaml += """
    - name: (ALCATEL) Apply Configuration
      ansible.netcommon.cli_config:
        config: "{{ ai_config[inventory_hostname]['config'] | join('\\n') }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'community.network.alcatel_aos'

    - name: (ALCATEL) Run Exec Commands
      ansible.netcommon.cli_command:
        command: "{{ item }}"
      loop: "{{ ai_config[inventory_hostname]['exec'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'community.network.alcatel_aos' and not ansible_check_mode
"""

        playbook_content = f"""
- name: VNMS Multi-Vendor Configuration Deployment
  hosts: all
  gather_facts: no
  vars_files:
    - vars.json
  tasks:
{tasks_yaml}
"""
        with open(playbook_path, 'w') as f:
            f.write(playbook_content)

        # 3. EXECUTE PLAYBOOK
        mode_text = {
            "simulation": "DRY-RUN SIMULATION (--check)",
            "production": "LIVE PRODUCTION PUSH",
            "verification": "POST-CHANGE VERIFICATION (--check; EXEC EXCLUDED)",
        }[execution_mode]
        
        ansible_logger.info(f"Starting Ansible Playbook Execution. Mode: {mode_text}")
        
        yield "data: --- INITIALIZING VNMS MULTI-VENDOR ANSIBLE ENGINE ---\n\n"
        yield f"data: Target Devices: {', '.join([d.hostname for d in devices])}\n\n"
        yield f"data: OS Types Detected: {', '.join([os.upper() for os in os_types_present])}\n\n"
        yield f"data: Executing {mode_text}...\n\n"
        yield "data: --------------------------------------------------\n\n"

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["ANSIBLE_FORCE_COLOR"] = "0" 

        cmd = ["ansible-playbook", "-i", inventory_path, playbook_path, "--diff"]
        if is_check_mode:
            cmd.append("--check")

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
            text=True, bufsize=1, universal_newlines=True, env=env
        )

        for line in process.stdout:
            clean_line = line.rstrip('\r\n')
            ansible_logger.info(clean_line) # <-- TRAPPED IN ANSIBLE.LOG
            yield f"data: {clean_line}\n\n"

        process.stdout.close()
        process.wait()

        yield "data: --------------------------------------------------\n\n"
        if process.returncode == 0:
            ansible_logger.info("Ansible Playbook completed successfully with no errors.")
            yield "data: PLAYBOOK COMPLETE: No errors detected.\n\n"
        else:
            ansible_logger.error(f"Ansible Playbook failed with return code: {process.returncode}")
            yield "data: PLAYBOOK FINISHED WITH ERRORS.\n\n"
