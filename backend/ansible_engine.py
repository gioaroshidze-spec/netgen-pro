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

def run_ansible_playbook(ai_config_data, devices, is_check_mode=True):
    """
    Executes Ansible, dynamically builds OS-specific task blocks, and streams output.
    All stdout/stderr is now silently trapped into ansible.log.
    """
    # Fix list-only AI outputs just in case
    for host, data in ai_config_data.items():
        if isinstance(data, list):
            ai_config_data[host] = {"config": data, "exec": []}

    with tempfile.TemporaryDirectory() as temp_dir:
        inventory_path = os.path.join(temp_dir, "inventory.yaml")
        playbook_path = os.path.join(temp_dir, "playbook.yaml")
        vars_path = os.path.join(temp_dir, "vars.json")

        with open(vars_path, 'w') as f:
            json.dump({"ai_config": ai_config_data}, f)

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
    - name: (CISCO) Apply Configuration
      cisco.ios.ios_config:
        lines: "{{ ai_config[inventory_hostname]['config'] | default([]) }}"
      when: inventory_hostname in ai_config and ansible_network_os == 'cisco.ios.ios'

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
        mode_text = "DRY-RUN SIMULATION (--check)" if is_check_mode else "LIVE PRODUCTION PUSH"
        
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
