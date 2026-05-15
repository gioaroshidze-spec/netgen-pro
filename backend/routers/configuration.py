import tempfile
import subprocess
import json
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from litellm import completion

router = APIRouter(tags=["Configuration Engine"])

@router.post("/configuration/generate")
def generate_configuration(request: schemas.AIConfigGenerate):
    """
    Receives an AI prompt and target lists, then generates the configuration logic
    as a strict JSON Data Model using the active LLM via LiteLLM.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    # 1. Format the targets so that AI knows what devices it is configuring
    switches_str = ", ".join(request.switches) if request.switches else "None"
    routers_str = ", ".join(request.routers) if request.routers else "None"

    # 2. Define the System Prompt (The "Rules" for the AI)
    system_prompt = (
        "You are an expert Enterprise Network Automation API. "
        "Your job is to read the network requirement and the provided running configs, and output the desired configuration state. "
        "CRITICAL RULES: "
        "1. You MUST respond ONLY with a raw, valid JSON object. Do not include markdown formatting (like ```json), code blocks, or conversational text. "
        "2. The JSON object must map the exact target device hostnames to a list of exact Cisco IOS configuration commands (or Aruba/HPE/Mikrotik if specified). "
        "3. Only generate commands that strictly fulfill the user's explicit request. Do NOT add unprompted cleanup commands. "
        'Example format:\n'
        '{\n'
        '  "cctv_sw1": ["vlan 10", " name servers", "interface range GigabitEthernet1/0/11 - 15", " switchport mode access", " switchport access vlan 10"],\n'
        '  "cctv_sw2": ["no vlan 10", "interface range GigabitEthernet1/0/11 - 20", " no switchport access vlan"]\n'
        '}'
    )

    # 3. Define the User Prompt
    user_prompt = f"""
    Target Switches: {switches_str}
    Target Routers: {routers_str}
    
    Network Requirement: {request.prompt}
    """

    # --- RETRIEVAL-AUGMENTED GENERATION (RAG) ---
    device_context = ""
    ARCHIVE_DIR = "archive"
    if os.path.exists(ARCHIVE_DIR):
        for target in (request.switches + request.routers):
            target_files = [f for f in os.listdir(ARCHIVE_DIR) if f"_{target}_" in f and f.endswith(".txt")]
            if target_files:
                target_files.sort(reverse=True)
                latest_file = target_files[0]
                try:
                    with open(os.path.join(ARCHIVE_DIR, latest_file), 'r') as f:
                        config_content = f.read()
                        device_context += f"\n! --- CURRENT RUNNING CONFIGURATION FOR {target} ---\n{config_content}\n"
                except Exception:
                    pass
    
    if device_context:
        user_prompt += f"\n\nHere is the current running configuration for the target devices. Analyze this to determine exact interface ranges, VLANs, or IP addresses required to fulfill the prompt:\n{device_context}"

    try:
        model_name = os.getenv("ACTIVE_AI_MODEL", "claude-opus-4-7") 
        # Using LiteLLM's completion wrapper
        response = completion(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1 
        )
        
        # 4. Extract and clean the JSON response
        raw_response = response.choices[0].message.content
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        
        # Return pure JSON text to the React UI
        return {"status": "success", "config": clean_json}
    
    except Exception as e:
        print(f"LiteLLM Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Engine Error: Check console for details. {str(e)}")


@router.post("/configuration/simulate")
def simulate_configuration(request: schemas.SimulateConfigRequest, db: Session = Depends(get_db)):
    """
    Parses the JSON data model, dynamically generates an Ansible playbook and inventory, 
    runs it in --check mode, and streams the raw terminal output back to the client.    
    """
    if not request.switches and not request.routers:
        raise HTTPException(status_code=400, detail="No target devices selected.")
    if not request.config_text.strip():
        raise HTTPException(status_code=400, detail="No configuration text provided.")
    
    # 1. Validate and Parse the JSON Data Model
    try:
        ai_config_data = json.loads(request.config_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Configuration is not valid JSON. Please generate logic or format as JSON.")

    # 2. Fetch the target devices from the database
    target_hostnames = request.switches + request.routers
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()

    if not devices:
        raise HTTPException(status_code=404, detail="Selected devices not found in the database.")

    def generate_ansible_stream():
        with tempfile.TemporaryDirectory() as temp_dir:
            inventory_path = os.path.join(temp_dir, "inventory.yaml")
            playbook_path = os.path.join(temp_dir, "playbook.yaml")
            vars_path = os.path.join(temp_dir, "vars.json")

            # --- WRITE THE AI DATA MODEL TO A VARS FILE ---
            with open(vars_path, 'w') as f:
                json.dump({"ai_config": ai_config_data}, f)

            # --- BUILD DYNAMIC INVENTORY ---
            inventory_data = {"all": {"hosts": {}}}
            for dev in devices:
                ansible_os = "cisco.ios.ios"
                if dev.os_type == "aruba": ansible_os = "arubanetworks.aoscx.aoscx"
                elif dev.os_type == "hpe": ansible_os = "community.network.ce" 
                
                inventory_data["all"]["hosts"][dev.hostname] = {
                    "ansible_host": dev.ip_address,
                    "ansible_network_os": ansible_os,
                    "ansible_connection": "network_cli",
                    "ansible_network_cli_ssh_type": "paramiko", # Supports legacy Cisco crypto
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

            # --- BUILD DATA-DRIVEN PLAYBOOK ---
            playbook_content = """
- name: VNMS JSON Data Model Deployment
  hosts: all
  gather_facts: no
  vars_files:
    - vars.json
  tasks:
    - name: Apply Config from AI JSON Model
      cisco.ios.ios_config:
        lines: "{{ ai_config[inventory_hostname] }}"
      when: inventory_hostname in ai_config and ai_config[inventory_hostname] | length > 0
      register: config_result

    - name: PRINT SIMULATION DIFF AND COMMANDS
      debug:
        msg:
          changed: "{{ config_result.changed | default(false) }}"
          commands: "{{ config_result.commands | default([]) }}"
          updates: "{{ config_result.updates | default([]) }}"
      when: inventory_hostname in ai_config and ai_config[inventory_hostname] | length > 0
"""
            with open(playbook_path, 'w') as f:
                f.write(playbook_content)

            yield "data: --- INITIALIZING VNMS SIMULATION ENGINE ---\n\n"
            yield "data: Compiling JSON data model, inventory, and playbook...\n\n"
            yield f"data: Target Devices: {', '.join([d.hostname for d in devices])}\n\n"
            yield "data: Executing Ansible Data-Driven dry-run (--check)...\n\n"
            yield "data: --------------------------------------------------\n\n"

            # --- RUN ANSIBLE AND STREAM OUTPUT ---
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["ANSIBLE_FORCE_COLOR"] = "0" 

            cmd = [
                "ansible-playbook", 
                "-i", inventory_path, 
                playbook_path, 
                "--check", 
                "--diff"
            ]

            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                bufsize=1, 
                universal_newlines=True,
                env=env
            )

            for line in process.stdout:
                clean_line = line.rstrip('\r\n')
                yield f"data: {clean_line}\n\n"

            process.stdout.close()
            process.wait()

            yield "data: --------------------------------------------------\n\n"
            if process.returncode == 0:
                yield "data: SIMULATION COMPLETE: No syntax errors detected in Data Model.\n\n"
            else:
                yield "data: SIMULATION FINISHED WITH ERRORS. Review the logs above.\n\n"

    return StreamingResponse(generate_ansible_stream(), media_type="text/event-stream")