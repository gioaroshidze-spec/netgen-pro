import tempfile
import subprocess
import json
import os
from logger import log_event  # <-- Import the universal logger

def run_ansible_playbook(ai_config_data, devices, db, prompt="Manual Execution", is_check_mode=True, author="System"):
    """
    Executes Ansible, streams output to the UI, and logs the entire transaction to the DB.
    """
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
        for dev in devices:
            ansible_os = "cisco.ios.ios"
            if dev.os_type == "aruba": ansible_os = "arubanetworks.aoscx.aoscx"
            elif dev.os_type == "hpe": ansible_os = "community.network.ce" 
            
            inventory_data["all"]["hosts"][dev.hostname] = {
                "ansible_host": dev.ip_address,
                "ansible_network_os": ansible_os,
                "ansible_connection": "network_cli",
                "ansible_network_cli_ssh_type": "paramiko", 
                "ansible_user": dev.username or "admin",
                "ansible_password": os.getenv("DEVICE_PASSWORD", "Werfds123"),
                "ansible_ssh_common_args": "-o MACs=+hmac-sha1 -o KexAlgorithms=+diffie-hellman-group14-sha1 -o HostKeyAlgorithms=+ssh-rsa"
            }
        
        with open(inventory_path, 'w') as f:
            f.write("all:\n  hosts:\n")
            for host, vars_dict in inventory_data["all"]["hosts"].items():
                f.write(f"    {host}:\n")
                for k, v in vars_dict.items():
                    f.write(f"      {k}: {v}\n")

        playbook_content = """
- name: VNMS JSON Data Model Deployment
  hosts: all
  gather_facts: no
  vars_files:
    - vars.json
  tasks:
    - name: PHASE 1 - Apply Configuration Commands
      cisco.ios.ios_config:
        lines: "{{ ai_config[inventory_hostname]['config'] | default([]) }}"
      when: 
        - inventory_hostname in ai_config 
        - ai_config[inventory_hostname]['config'] is defined
        - ai_config[inventory_hostname]['config'] | length > 0
      register: config_result

    - name: PHASE 2 - Run Exec Commands (Save / Show)
      cisco.ios.ios_command:
        commands: "{{ ai_config[inventory_hostname]['exec'] | default([]) }}"
      when: 
        - inventory_hostname in ai_config 
        - ai_config[inventory_hostname]['exec'] is defined
        - ai_config[inventory_hostname]['exec'] | length > 0
        - not ansible_check_mode
      register: exec_result

    - name: PRINT RESULTS
      debug:
        msg:
          config_changed: "{{ config_result.changed | default(false) }}"
          config_updates: "{{ config_result.updates | default([]) }}"
          exec_output: "{{ exec_result.stdout_lines | default(['Skipped in Simulation Mode']) }}"
"""
        with open(playbook_path, 'w') as f:
            f.write(playbook_content)

        mode_text = "DRY-RUN SIMULATION (--check)" if is_check_mode else "LIVE PRODUCTION PUSH"
        yield "data: --- INITIALIZING VNMS ANSIBLE ENGINE ---\n\n"
        yield f"data: Target Devices: {', '.join([d.hostname for d in devices])}\n\n"
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

        # --- NEW: Capture Output for Logging ---
        ansible_full_log = ""
        for line in process.stdout:
            clean_line = line.rstrip('\r\n')
            ansible_full_log += clean_line + "\n"
            yield f"data: {clean_line}\n\n"

        process.stdout.close()
        process.wait()

        # --- NEW: Inject the Audit Log ---
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