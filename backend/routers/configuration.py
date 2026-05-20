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
from netmiko import ConnectHandler

# IMPORT OUR NEW ENGINE
from ansible_engine import run_ansible_playbook

router = APIRouter(tags=["Configuration Engine"])

@router.post("/configuration/generate")
def generate_configuration(request: schemas.AIConfigGenerate, db: Session = Depends(get_db)):
    """
    Receives an AI prompt and target lists, then generates the configuration logic
    as a strict JSON Data Model using the active LLM via LiteLLM.
    Uses Netmiko to pull LIVE running-config context before prompting the AI.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    # 1. Format the targets so that AI knows what devices it is configuring
    switches_str = ", ".join(request.switches) if request.switches else "None"
    routers_str = ", ".join(request.routers) if request.routers else "None"

    # 2. Define the System Prompt (The "Rules" for the AI)
    system_prompt = (
        "You are an expert Enterprise Network Automation API. "
        "Your job is to read the network requirement and the provided running configs, and output the desired state. "
        "CRITICAL RULES: "
        "1. You MUST respond ONLY with a raw, valid JSON object. No markdown, no code blocks, no conversational text. "
        "2. The JSON object must map exact hostnames to a dictionary containing TWO keys: 'config' and 'exec'. "
        "3. The JSON object must map the exact target device hostnames to a list of exact Cisco IOS configuration commands (or Aruba/HPE/Mikrotik if specified). "
        "4. The 'config' list is strictly for Global Configuration mode commands (VLANs, interfaces, routing). Do not include 'conf t' or 'exit'. "
        "5. The 'exec' list is strictly for Privileged EXEC mode commands (e.g., 'write memory', 'show vlan brief', 'copy run start'). "
        'Example format:\n'
        '{\n'
        '  "cctv_sw1": {\n'
        '    "config": ["vlan 10", " name servers", "interface range GigabitEthernet1/0/11 - 15", " switchport access vlan 10"],\n'
        '    "exec": ["write memory", "show vlan id 10"]\n'
        '  }\n'
        '}'
    )

    # 3. Define the User Prompt
    user_prompt = f"""
    Target Switches: {switches_str}
    Target Routers: {routers_str}
    
    Network Requirement: {request.prompt}
    """

    # --- NEW: LIVE RETRIEVAL-AUGMENTED GENERATION (RAG) ---
    device_context = ""
    target_hostnames = request.switches + request.routers
    
    if target_hostnames:
        # Fetch device IPs and credentials from the database
        devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()
        
        for dev in devices:
            try:
                # Map OS to Netmiko device types
                netmiko_os = 'cisco_ios'
                if dev.os_type == 'aruba' or dev.os_type == 'hpe':
                    netmiko_os = 'hp_procurve' # General fallback for standard switches, adjust if using aoscx
                
                connection_params = {
                    'device_type': netmiko_os,
                    'host': dev.ip_address,
                    'username': dev.username,
                    'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
                    'fast_cli': True # Speeds up execution
                }
                
                with ConnectHandler(**connection_params) as net_connect:
                    net_connect.enable()
                    raw_config = net_connect.send_command("show running-config")
                    
                    # Clean out the timestamp headers to save AI tokens
                    clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                    config_content = "\n".join(clean_lines)
                    
                    device_context += f"\n! --- LIVE RUNNING CONFIGURATION FOR {dev.hostname} ---\n{config_content}\n"
                    print(f"Successfully pulled live config for {dev.hostname} context.")
                    
            except Exception as e:
                print(f"Failed to fetch live config for {dev.hostname}: {e}")
                device_context += f"\n! --- ERROR: COULD NOT FETCH LIVE CONFIG FOR {dev.hostname}. Rely strictly on user prompt. ---\n"
    
    if device_context:
        user_prompt += f"\n\nHere is the LIVE running configuration for the target devices. Analyze this to determine exact current interface ranges, VLANs, or IP addresses required to fulfill the prompt:\n{device_context}"

    try:
        model_name = os.getenv("ACTIVE_AI_MODEL", "claude-opus-4-7") 
        response = completion(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 4. Extract and clean the JSON response
        raw_response = response.choices[0].message.content
        clean_text = raw_response.replace("```json", "").replace("```", "").strip()
        
        # 5. Validate and Pretty-Print the JSON
        try:
            parsed_json = json.loads(clean_text)
            beautiful_json = json.dumps(parsed_json, indent=2) 
            return {"status": "success", "config": beautiful_json}
            
        except json.JSONDecodeError:
            print(f"Failed to parse AI output as JSON: {clean_text}")
            raise HTTPException(status_code=500, detail="AI generated invalid JSON format. Please try generating again.")
    
    except Exception as e:
        print(f"LiteLLM Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Engine Error: Check console for details. {str(e)}")


@router.post("/configuration/simulate")
def simulate_configuration(request: schemas.SimulateConfigRequest, db: Session = Depends(get_db)):
    """Runs the configuration through Ansible in strict --check mode."""
    if not request.switches and not request.routers:
        raise HTTPException(status_code=400, detail="No target devices selected.")
    
    try:
        ai_config_data = json.loads(request.config_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Configuration is not valid JSON. Please generate logic or format as JSON.")

    target_hostnames = request.switches + request.routers
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()

    if not devices:
        raise HTTPException(status_code=404, detail="Selected devices not found in the database.")

    return StreamingResponse(run_ansible_playbook(ai_config_data, devices, db=db, prompt=request.prompt, is_check_mode=True), media_type="text/event-stream")

@router.post("/configuration/push")
def push_configuration(request: schemas.SimulateConfigRequest, db: Session = Depends(get_db)):
    """Pushes the configuration live to the hardware."""
    if not request.switches and not request.routers:
        raise HTTPException(status_code=400, detail="No target devices selected.")
    
    try:
        ai_config_data = json.loads(request.config_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Configuration is not valid JSON. Please generate logic or format as JSON.")

    target_hostnames = request.switches + request.routers
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()

    if not devices:
        raise HTTPException(status_code=404, detail="Selected devices not found in the database.")

    return StreamingResponse(run_ansible_playbook(ai_config_data, devices, db=db, prompt=request.prompt, is_check_mode=False), media_type="text/event-stream")