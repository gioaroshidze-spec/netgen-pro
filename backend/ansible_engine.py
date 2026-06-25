import tempfile
import subprocess
import json
import os
from logger import log_event
from routers.auth import decrypt_secret

def run_ansible_playbook(ai_config_data, devices, db, prompt="Manual Execution", is_check_mode=True, author="System"):
    """
    Executes Ansible, dynamically builds OS-specific task blocks, streams output, and logs to DB.
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

        inventory_data = {"all": {"hosts": {}}}
        os_types_present = set()

        # 1. BUILD MULTI-VENDOR INVENTORY
        for dev in devices:
            os_type = (dev.os_type or "cisco").lower()
            os_types_present.add(os_type)
            
            # Map database OS string to the exact Ansible Network OS Collection
            if os_type == "aruba": ansible_os = "arubanetworks.aoscx.aoscx"
            elif os_type == "hpe": ansible_os = "community.network.aruba"
            elif os_type == "mikrotik": ansible_os = "community.routeros.routeros"
            elif os_type in ["alcatel", "alcatel-lucent"]: ansible_os = "community.network.alcatel_aos"
            else: ansible_os = "cisco.ios.ios"
            
            inventory_data["all"]["hosts"][dev.hostname] = {
                "ansible_host": dev.ip_address,
                "ansible_network_os": ansible_os,
                "ansible_connection": "network_cli",
                "ansible_user": dev.username or "admin",
                "ansible_password": decrypt_secret(dev.encrypted_password),
                # We tell Ansible to ignore the strict host key checking (the yes/no prompt), but we rely on modern RSA keys now!
                "ansible_ssh_common_args": "-o StrictHostKeyChecking=no"
            }
        
        with open(inventory_path, 'w') as f:
            f.write("all:\n  hosts:\n")
            for host, vars_dict in inventory_data["all"]["hosts"].items():
                f.write(f"    {host}:\n")
                for k, v in vars_dict.items():
                    f.write(f"      {k}: {v}\n")

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

        ansible_full_log = ""
        for line in process.stdout:
            clean_line = line.rstrip('\r\n')
            ansible_full_log += clean_line + "\n"
            yield f"data: {clean_line}\n\n"

        process.stdout.close()
        process.wait()

        # 4. AUDIT LOGGING
        severity = "SUCCESS" if process.returncode == 0 else "ERROR"
        action = "Configuration Simulation" if is_check_mode else "Live Configuration Push"
        
        log_event(
            db=db,
            event_type="Configuration",
            severity=severity,
            author=author,
            target_devices=[d.hostname for d in devices],
            details={
                "action": action,
                "prompt": prompt,
                "ai_model": ai_config_data,
                "ansible_logs": ansible_full_log
            }
        )

        yield "data: --------------------------------------------------\n\n"
        if process.returncode == 0:
            yield "data: PLAYBOOK COMPLETE: No errors detected.\n\n"
        else:
            yield "data: PLAYBOOK FINISHED WITH ERRORS.\n\n"