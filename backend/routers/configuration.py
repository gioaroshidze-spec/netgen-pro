import json
import os
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
from litellm import completion
from netmiko import ConnectHandler

# --- IMPORT THE BOUNCERS ---
from routers.auth import get_current_user
from ansible_engine import run_ansible_playbook
from routers.auth import decrypt_secret
from logger import log_event

router = APIRouter(tags=["Configuration Engine"])

# ==========================================
# --- STRICT ANSIBLE PAYLOAD SANITIZER ---
# ==========================================
def validate_ansible_payload(payload: dict):
    """
    Strictly enforces the JSON schema expected by the Ansible engine.
    Prevents nested object injection, type mismatch crashes, and payload corruption.
    """
    if not isinstance(payload, dict):
        raise ValueError("Root payload must be a JSON object mapping hostnames to commands.")
    
    for host, data in payload.items():
        if not isinstance(data, dict):
            raise ValueError(f"Data for host '{host}' must be a JSON object.")
        
        # Check for required keys and strict list types
        if "config" not in data or not isinstance(data["config"], list):
            raise ValueError(f"Host '{host}' is missing a valid 'config' list.")
        if "exec" not in data or not isinstance(data["exec"], list):
            raise ValueError(f"Host '{host}' is missing a valid 'exec' list.")
        
        # Ensure every element inside the lists is strictly a string
        if not all(isinstance(cmd, str) for cmd in data["config"]):
            raise ValueError(f"All 'config' commands for '{host}' must be strictly strings.")
        if not all(isinstance(cmd, str) for cmd in data["exec"]):
            raise ValueError(f"All 'exec' commands for '{host}' must be strictly strings.")

# ==========================================
# --- STREAM INTERCEPTOR & LOGGER ---
# ==========================================
def stream_ansible_and_log(ansible_stream, db: Session, prompt: str, ai_config_data: dict, devices: list, mode: str, author: str, source_template: str = None):
    """
    Wraps the Ansible output generator. Streams data to the frontend in real-time,
    and once finished, parses the recap, skips, and errors to save a rich audit log.
    """
    full_output = ""
    
    # 1. Yield chunks to the frontend exactly as they arrive
    for chunk in ansible_stream:
        full_output += chunk
        yield chunk

    # 2. Once the stream finishes, clean the SSE formatting for parsing
    clean_output = full_output.replace("data: ", "").replace("\n\n", "\n")

    # 3. Surgically extract ONLY the relevant blocks (Failures, Skips & Recap)
    parts = re.split(r'(?=TASK \[|PLAY RECAP)', clean_output)
    
    important_blocks = []
    for i, part in enumerate(parts):
        if "PLAY RECAP" in part:
            important_blocks.append(part.strip())
        elif re.search(r'^[ \t]*(fatal|failed|skipping|\[ERROR\])', part, re.MULTILINE | re.IGNORECASE):
            important_blocks.append(part.strip())
        elif i == 0 and re.search(r'(error|fatal)', part, re.IGNORECASE):
            important_blocks.append(part.strip())
            
    final_ansible_log = "\n\n".join(important_blocks)

    if not final_ansible_log.strip():
        final_ansible_log = "--- NO ERRORS OR SKIPS DETECTED ---\n\n"
        recap_idx = clean_output.rfind("PLAY RECAP")
        if recap_idx != -1:
            final_ansible_log += clean_output[recap_idx:].strip()
        else:
            final_ansible_log += clean_output[-1000:] if len(clean_output) > 1000 else clean_output

    final_ansible_log = final_ansible_log.strip()

    # 4. Determine strict Success/Fail status
    has_failures = bool(re.search(r'failed=[1-9]\d*|unreachable=[1-9]\d*', final_ansible_log)) or bool(re.search(r'^[ \t]*(fatal|failed|\[ERROR\])', final_ansible_log, re.MULTILINE | re.IGNORECASE))
    final_severity = "ERROR" if has_failures else "SUCCESS"
    execution_status = "Failed" if has_failures else "Success"

    # 5. Build the rich target device payload
    target_devices_payload = [
        {
            "hostname": dev.hostname,
            "ip_address": dev.ip_address,
            "device_type": dev.device_type,
            "os_type": dev.os_type
        } for dev in devices
    ]

    # 6. Build the UI Details mapping
    details = {
        "action": "AI Configuration Deployment",
        "mode": mode,
        "prompt": prompt,
        "generated_commands": json.dumps(ai_config_data, indent=2),
        "execution_status": execution_status,
        "ansible_logs": final_ansible_log
    }

    # INJECT TEMPLATE TRACKING IF PRESENT
    if source_template:
        details["source_template"] = source_template

    # 7. Commit to database
    log_event(
        db=db,
        event_type="Configuration",
        severity=final_severity,
        details=details,
        target_devices=target_devices_payload,
        author=author
    )


# ==========================================
# --- ROUTES ---
# ==========================================
@router.post("/configuration/generate")
def generate_configuration(request: schemas.AIConfigGenerate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    target_hostnames = request.switches + request.routers
    devices = []
    if target_hostnames:
        devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()

    os_mapping_text = ""
    for dev in devices:
        os_mapping_text += f"- Hostname: {dev.hostname} | OS Type: {dev.os_type.upper()}\n"

    system_prompt = (
        "You are an expert Enterprise Network Automation API. "
        "Your job is to read the network requirement and the provided running configs, and output the desired state. "
        "CRITICAL RULES: "
        "1. You MUST respond ONLY with a raw, valid JSON object. No markdown, no conversational text. "
        "2. The JSON object must map exact hostnames to a dictionary containing TWO keys: 'config' and 'exec'. "
        "3. VENDOR SYNTAX STRICTNESS: You must generate the exact, vendor-specific syntax for each device based on its operating system.\n"
        "   - Cisco (cisco): Standard Cisco IOS commands.\n"
        "   - Aruba/HPE (aruba/hpe): Use Aruba AOS-CX or ProVision syntax as appropriate.\n"
        "   - MikroTik (mikrotik): Use MikroTik RouterOS syntax (e.g., '/ip address add...').\n"
        "   - Alcatel-Lucent (alcatel): Use Alcatel AOS syntax.\n"
        "4. The 'config' list is strictly for configuration mode commands (VLANs, interfaces). Do not include 'conf t' or 'exit'. "
        "5. The 'exec' list is strictly for Privileged EXEC mode commands (e.g., 'write memory', 'copy run start'). "
        "6. TEMPLATE OVERRIDE: If a base template is provided, preserve its architectural logic but translate the syntax to match the target device's OS. "
    )

    user_prompt = f"Target Devices & Operating Systems:\n{os_mapping_text if os_mapping_text else 'None'}\n\nNetwork Requirement: {request.prompt}"

    if request.base_template:
        user_prompt += f"\n\n--- BASE TEMPLATE PROVIDED ---\nAdapt the following configuration structure for the new targets, translating to their specific OS syntax:\n{json.dumps(request.base_template, indent=2)}"

    device_context = ""
    
    if devices:
        for dev in devices:
            try:
                netmiko_os = 'cisco_ios'
                if dev.os_type == 'aruba': netmiko_os = 'aruba_os'
                elif dev.os_type == 'hpe': netmiko_os = 'hp_procurve'
                elif dev.os_type == 'mikrotik': netmiko_os = 'mikrotik_routeros'
                elif dev.os_type in ['alcatel', 'alcatel-lucent']: netmiko_os = 'alcatel_aos'
                
                connection_params = {
                    'device_type': netmiko_os, 'host': dev.ip_address,
                    'username': dev.username, 'password': decrypt_secret(dev.encrypted_password),
                    'fast_cli': True
                }
                
                with ConnectHandler(**connection_params) as net_connect:
                    if dev.os_type != 'mikrotik':
                        try: net_connect.enable()
                        except: pass
                    
                    show_cmd = "show running-config"
                    if dev.os_type == 'mikrotik': show_cmd = "/export"
                    elif dev.os_type in ['alcatel', 'alcatel-lucent']: show_cmd = "show configuration snapshot"
                    
                    raw_config = net_connect.send_command(show_cmd)
                    clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                    config_content = "\n".join(clean_lines)
                    
                    device_context += f"\n! --- LIVE RUNNING CONFIGURATION FOR {dev.hostname} ({dev.os_type.upper()}) ---\n{config_content}\n"
                    
            except Exception as e:
                print(f"Failed to fetch live config for {dev.hostname}: {e}")
                device_context += f"\n! --- ERROR: COULD NOT FETCH LIVE CONFIG FOR {dev.hostname}. Rely strictly on user prompt. ---\n"
    
    if device_context:
        user_prompt += f"\n\nHere is the LIVE running configuration for the target devices. Analyze this to ensure your generated commands don't conflict with existing setups:\n{device_context}"

    try:
        model_name = os.getenv("ACTIVE_AI_MODEL", "claude-opus-4-7") 
        response = completion(
            model=model_name,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )
        
        raw_response = response.choices[0].message.content
        clean_text = raw_response.replace("```json", "").replace("```", "").strip()
        
        try:
            parsed_json = json.loads(clean_text)
            beautiful_json = json.dumps(parsed_json, indent=2) 
            return {"status": "success", "config": beautiful_json}
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="AI generated invalid JSON format. Please try generating again.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Engine Error: Check console for details. {str(e)}")


@router.post("/configuration/simulate")
def simulate_configuration(request: schemas.SimulateConfigRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not request.switches and not request.routers:
        raise HTTPException(status_code=400, detail="No target devices selected.")
    try: 
        ai_config_data = json.loads(request.config_text)
        validate_ansible_payload(ai_config_data) # <-- SANITIZED
    except json.JSONDecodeError: 
        raise HTTPException(status_code=400, detail="Configuration is not valid JSON.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    target_hostnames = request.switches + request.routers
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()
    if not devices: raise HTTPException(status_code=404, detail="Selected devices not found in the database.")

    source_template = request.source_template
    ansible_stream = run_ansible_playbook(ai_config_data, devices, is_check_mode=True)

    return StreamingResponse(
        stream_ansible_and_log(ansible_stream, db, request.prompt, ai_config_data, devices, "Simulate (--check)", current_user.username, source_template), 
        media_type="text/event-stream"
    )

@router.post("/configuration/push")
def push_configuration(request: schemas.SimulateConfigRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not request.switches and not request.routers:
        raise HTTPException(status_code=400, detail="No target devices selected.")
    try: 
        ai_config_data = json.loads(request.config_text)
        validate_ansible_payload(ai_config_data) # <-- SANITIZED
    except json.JSONDecodeError: 
        raise HTTPException(status_code=400, detail="Configuration is not valid JSON.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    target_hostnames = request.switches + request.routers
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()
    if not devices: raise HTTPException(status_code=404, detail="Selected devices not found in the database.")

    source_template = request.source_template
    ansible_stream = run_ansible_playbook(ai_config_data, devices, is_check_mode=False)

    return StreamingResponse(
        stream_ansible_and_log(ansible_stream, db, request.prompt, ai_config_data, devices, "Production Push", current_user.username, source_template), 
        media_type="text/event-stream"
    )