import tempfile
import subprocess
import json
import os
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

router = APIRouter(tags=["Configuration Engine"])

@router.post("/configuration/generate")
def generate_configuration(request: schemas.AIConfigGenerate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    target_hostnames = request.switches + request.routers
    devices = []
    if target_hostnames:
        devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()

    # --- NEW: Build the OS Mapping String for the AI ---
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
                # --- NEW: Dynamic Netmiko OS Mapping ---
                netmiko_os = 'cisco_ios'
                if dev.os_type == 'aruba': netmiko_os = 'aruba_os'
                elif dev.os_type == 'hpe': netmiko_os = 'hp_procurve'
                elif dev.os_type == 'mikrotik': netmiko_os = 'mikrotik_routeros'
                elif dev.os_type in ['alcatel', 'alcatel-lucent']: netmiko_os = 'alcatel_aos'
                
                connection_params = {
                    'device_type': netmiko_os, 'host': dev.ip_address,
                    'username': dev.username, 'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
                    'fast_cli': True
                }
                
                with ConnectHandler(**connection_params) as net_connect:
                    # MikroTik doesn't use the standard enable mode
                    if dev.os_type != 'mikrotik':
                        try: net_connect.enable()
                        except: pass
                    
                    # --- NEW: Vendor-Specific Show Commands ---
                    show_cmd = "show running-config"
                    if dev.os_type == 'mikrotik': show_cmd = "/export"
                    elif dev.os_type in ['alcatel', 'alcatel-lucent']: show_cmd = "show configuration snapshot"
                    
                    raw_config = net_connect.send_command(show_cmd)
                    
                    # Clean up standard Cisco/HPE headers
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
    try: ai_config_data = json.loads(request.config_text)
    except json.JSONDecodeError: raise HTTPException(status_code=400, detail="Configuration is not valid JSON.")

    target_hostnames = request.switches + request.routers
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()
    if not devices: raise HTTPException(status_code=404, detail="Selected devices not found in the database.")

    return StreamingResponse(run_ansible_playbook(ai_config_data, devices, db=db, prompt=request.prompt, is_check_mode=True, author=current_user.username), media_type="text/event-stream")

@router.post("/configuration/push")
def push_configuration(request: schemas.SimulateConfigRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not request.switches and not request.routers:
        raise HTTPException(status_code=400, detail="No target devices selected.")
    try: ai_config_data = json.loads(request.config_text)
    except json.JSONDecodeError: raise HTTPException(status_code=400, detail="Configuration is not valid JSON.")

    target_hostnames = request.switches + request.routers
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()
    if not devices: raise HTTPException(status_code=404, detail="Selected devices not found in the database.")

    return StreamingResponse(run_ansible_playbook(ai_config_data, devices, db=db, prompt=request.prompt, is_check_mode=False, author=current_user.username), media_type="text/event-stream")