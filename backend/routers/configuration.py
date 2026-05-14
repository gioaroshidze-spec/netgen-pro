import tempfile
import subprocess
import json
import os
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
import models
from fastapi import APIRouter, Depends, HTTPException
import schemas
import os
from litellm import completion

router = APIRouter(tags=["Configuration Engine"])

@router.post("/configuration/generate")
def generate_configuration(request: schemas.AIConfigGenerate):
    """
    Receives an AI prompt and target lists, then generates the configuration logic
    using the active LLM via LiteLLM.
    """

    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    # 1. Format the targets so that AI knows what devices it is configuring
    switches_str = ", ".join(request.switches) if request.switches else "None"
    routers_str = ", ".join(request.routers) if request.routers else "None"

    # 2. Define the System Prompt (The "Rules" for the AI)
    system_prompt = (
        "You are an expert, senior Enterprise Network Engineer. "
        "Your job is to generate strict, production-ready configuration commands (Cisco IOS by default unless specified(specification might be Aruba, HPE, Mikrotik)). "
        "CRITICAL RULE: Only generate commands that strictly fulfill the user's explicit request. "
        "Do NOT add unprompted cleanup commands (e.g., deleting SVIs like 'no interface VlanX' unless explicitly asked). "
        "Use provided running configurations ONLY to find required target interfaces, names, or IP addresses. "
        "Do not include conversational filler, markdown formatting blocks like ```bash, or explanations. "
        "ONLY output the raw configuration lines and necessary comments starting with '!'. "
    )

    # 3. Define the User Prompt (What you typed in the UI)
    # 3. Define the User Prompt
    user_prompt = f"""
    Target Switches: {switches_str}
    Target Routers: {routers_str}
    
    Network Requirement: {request.prompt}
    """

    # --- NEW: RETRIEVAL-AUGMENTED GENERATION (RAG) ---
    # Fetch the latest backup config for the target devices to give the AI context
    device_context = ""
    ARCHIVE_DIR = "archive"
    if os.path.exists(ARCHIVE_DIR):
        for target in (request.switches + request.routers):
            # Find all text files in the archive that belong to this target
            target_files = [f for f in os.listdir(ARCHIVE_DIR) if f"_{target}_" in f and f.endswith(".txt")]
            if target_files:
                # Sort descending so the newest backup is index [0]
                target_files.sort(reverse=True)
                latest_file = target_files[0]
                try:
                    with open(os.path.join(ARCHIVE_DIR, latest_file), 'r') as f:
                        config_content = f.read()
                        device_context += f"\n! --- CURRENT RUNNING CONFIGURATION FOR {target} ---\n{config_content}\n"
                except Exception:
                    pass
    
    # If we found backups, staple them to the prompt!
    if device_context:
        user_prompt += f"\n\nHere is the current running configuration for the target devices. Analyze this to determine exact interface ranges, VLANs, or IP addresses required to fulfill the prompt:\n{device_context}"

    try:
        # Fetch the model from .env (defautls to Claude 3 Opus if not found)
        model_name = os.getenv("ACTIVE_AI_MODEL", "claude-opus-4-7")

        # 4. Make the call to the AI Provider using LiteLLM
        response = completion(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],

        )

        # 5. Extract the text and return it to React
        generated_config = response.choices[0].message.content

        # Add a nice header for the UI
        final_output = f"! --- VNMS AI Generated Configuration ---\n"
        final_output += f"! Model: {model_name}\n!\n"
        final_output += generated_config

        return {"status": "success", "config": final_output}
    
    except Exception as e:
        # If your API key is missing or ivalid, it will safely throw an error here
        print(f"LiteLLM Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Engine Error: Check console for details. ")
    

@router.post("/configuration/simulate")
def simulate_configuration(request: schemas.SimulateConfigRequest, db: Session = Depends(get_db)):
    """
    Dynamically generates an Ansible playbook and inventory, runs it in --check -- diff mode,
    and streams the raw terminal output back to the client.    
    """
    if not request.switches and not request.routers:
        raise HTTPException(status_code=400, detail="No target devices selected.")
    if not request.config_text.strip():
        raise HTTPException(status_code=400, detail="No configuration text provided.")
    
    # 1. Fetch the target devices from the database
    target_hostnames = request.switches + request.routers
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()

    if not devices:
        raise HTTPException(status_code=404, detail="Selected devices not found in the database.")
    
    # 2. Extract just the raw commands (strip out the blue '!' comments)
    ignored_cmds = ["configure terminal", "conf t", "end", "exit", "write memory", "wr mem"]
    raw_commands = [
        line.strip() for line in request.config_text.split('\n') 
        if line.strip() 
        and not line.strip().startswith('!') 
        and line.strip().lower() not in ignored_cmds
    ]
    def generate_ansible_stream():
        # Create a temporary directory to hold our dynamic files
        with tempfile.TemporaryDirectory() as temp_dir:
            inventory_path = os.path.join(temp_dir, "inventory.yaml")
            playbook_path = os.path.join(temp_dir, "playbook.yaml")

            # --- BUILD DYNAMIC INVENTORY ---
            inventory_data = {"all": {"hosts": {}}}
            for dev in devices:
                # Maq our db OS types to Ansible network OS types
                ansible_os = "cisco.ios.ios"
                if dev.os_type == "aruba": ansible_os = "arubanetworks.aoscx.aoscx"
                elif dev.os_type == "hpe": ansible_os = "community.network.ce" # Approximation for HPE
                elif dev.os_type == "mikrotik": ansible_os = "routeros"

                inventory_data["all"]["hosts"][dev.hostname] = {
                    "ansible_host": dev.ip_address,
                    "ansible_network_os": ansible_os,
                    "ansible_connection": "network_cli",
                    "ansible_user": dev.username or "admin",
                    "ansible_password": os.getenv("DEVICE_PASSWORD", "Werfds123")
                }
            # Write inventory file
            with open(inventory_path, 'w') as f:
                # Quick manual YAML generation to avoid requiring PyYAML dependency
                f.write("all:\n hosts:\n")
                for host, vars_dict in inventory_data["all"]["hosts"].items():
                    f.write(f"    {host}:\n")
                    for k, v in vars_dict.items():
                        f.write(f"      {k}: {v}\n")

            # --- BUILD DYNAMIC PLAYBOOK ---
            # We use cisco.ios.ios_config as the default module for pushing commands
            playbook_content = f"""
- name: VNMS AI Configuration Simulation
  hosts: all
  gather_facts: no
  tasks:
    - name: Simulate Configuration Changes
      cisco.ios.ios_config:
        lines:
"""
            for cmd in raw_commands:
                playbook_content += f"          - {cmd}\n"
            
            # --- NEW: EXPLICITLY CAPTURE AND PRINT THE RESULTS ---
            playbook_content += """
      register: config_result

    - name: PRINT SIMULATION DIFF AND COMMANDS
      debug:
        var: config_result
"""

            # ... (keep your existing playbook generation code here) ...
            with open(playbook_path, 'w') as f:
                f.write(playbook_content)

            yield "data: --- INITIALIZING VNMS SIMULATION ENGINE ---\n\n"
            yield "data: Compiling dynamic inventory and playbook...\n\n"
            yield f"data: Target Devices: {', '.join([d.hostname for d in devices])}\n\n"
            yield "data: Executing Ansible dry-run (--check --diff)...\n\n"
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
                "--diff"  # We can even drop the -v flag now!
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

            # Yield each line as it prints to the terminal
            for line in process.stdout:
                clean_line = line.rstrip('\r\n')
                yield f"data: {clean_line}\n\n"

            process.stdout.close()
            process.wait()

            yield "data: --------------------------------------------------\n\n"
            if process.returncode == 0:
                yield "data: SIMULATION COMPLETE: No syntax errors detected.\n\n"
            else:
                yield "data: SIMULATION FINISHED WITH ERRORS. Review the logs above.\n\n"

    # Return the stream to React using Server-Sent Events (SSE)
    return StreamingResponse(generate_ansible_stream(), media_type="text/event-stream")