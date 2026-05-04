from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
import schemas
from netmiko import ConnectHandler
import io
import zipfile
import os
import tempfile
import subprocess
import json
import jinja2
import asyncio
from datetime import datetime
import difflib
import re
from typing import Optional

# --- GLOBAL VARIABLES & DIRECTORIES ---
ARCHIVE_DIR = "./archive"
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Create the database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NetGen Pro API",
    description="Backend engine for network Management System",
    version="1.0.0"
)

# --- CORS CONFIGURATION ---
# This allows your React frontend to securely talk to the FastAPI backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React's address
    allow_credentials=True,
    allow_methods=["*"],  # Allows all standard methods (GET, POST, etc.)
    allow_headers=["*"],
)


# --- DATABASE DEPENDENCY ---
# This function opens a connection to the DB for every request, the safely closes it
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- JINJA2 CONFIGURATION ---
template_loader = jinja2.FileSystemLoader(searchpath="./templates")
template_env = jinja2.Environment(loader=template_loader)

# --- API ENDPOINT ---

@app.get("/")
def read_root():
    return {"status": "online", "message": "NetGen Pro Backend is active!"}

# 1. Create a new device (POST)
@app.post("/device/", response_model=schemas.DeviceResponse)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db)):
    
    # GUARDRAIL: Check if Hostname or IP already exists
    existing_host = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname == device.hostname).first()
    if existing_host:
        raise HTTPException(status_code=400, detail=f"Error: Hostname '{device.hostname}' is already taken.")
        
    existing_ip = db.query(models.NetworkDevice).filter(models.NetworkDevice.ip_address == device.ip_address).first()
    if existing_ip:
        raise HTTPException(status_code=400, detail=f"Error: IP Address '{device.ip_address}' is already in use.")

    # Package the incoming data into a database model
    db_device = models.NetworkDevice(
        hostname=device.hostname,
        ip_address=device.ip_address,
        device_type=device.device_type,
        os_type=device.os_type,
        username=device.username
    )

    # Add to DB, commit the transaction, and refresh to get the new ID
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device

# 2. Get a list of all devices (GET)
@app.get("/device/", response_model=list[schemas.DeviceResponse])
def get_devices(db: Session = Depends(get_db)):
    #Query the database for all NetworkDevice records
    devices = db.query(models.NetworkDevice).all()
    return devices

# 3. Update an existing device (PUT)
@app.put("/device/{device_id}", response_model=schemas.DeviceResponse)
def update_device(device_id: int, device_update: schemas.DeviceUpdate, db: Session = Depends(get_db)):
    # Find the device in the database
    db_device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()

    # If it doesn't exist, throw a 404 error
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
        
    # GUARDRAIL: If they are changing the hostname, make sure the new one isn't taken by SOMEONE ELSE
    if device_update.hostname and device_update.hostname != db_device.hostname:
        existing_host = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname == device_update.hostname).first()
        if existing_host:
            raise HTTPException(status_code=400, detail=f"Error: Hostname '{device_update.hostname}' is already taken.")

    # GUARDRAIL: If they are changing the IP, make sure the new one isn't taken
    if device_update.ip_address and device_update.ip_address != db_device.ip_address:
        existing_ip = db.query(models.NetworkDevice).filter(models.NetworkDevice.ip_address == device_update.ip_address).first()
        if existing_ip:
            raise HTTPException(status_code=400, detail=f"Error: IP Address '{device_update.ip_address}' is already in use.")
    
    # Update only the fields the user actually sent us
    update_data = device_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_device, key, value)

    db.commit()
    db.refresh(db_device)
    return db_device

# 4. Delete a device (DELETE)
@app.delete("/device/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    # Find the device in the database
    db_device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()

    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    
    db.delete(db_device)
    db.commit()
    return {"message": f"Device {device_id} successfully deleted"}

# 5. Network Mapper (GET)
@app.get("/network-map/")
def get_network_map(db: Session = Depends(get_db)):
    # Grab all devices from our database "inventory"
    devices = db.query(models.NetworkDevice).all()
    mapped_devices = []

    for device in devices:
        
        # Clean the IP of any invisible space or newlines
        clean_ip = device.ip_address.strip()

        # We run the native Ubuntu ping command:
        # -c 1 (send exactly 1 packet)
        # -W 1 (wait a maximum of 1 second for a reply)
        command = ["ping", "-c", "1", "-W", "1", clean_ip]

        # Execute the command in the background
        response = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # If it fails, print the EXACT Ubuntu error to your VS Code terminal
        if response.returncode != 0:
            print(f"PING FAILED for {clean_ip}")
            print(f"Error output: {response.stderr.strip()}")
            print(f"Standard output: {response.stdout.strip()}")
            print("-" * 30)


        # If returncode is 0, the ping was successful
        status = "online" if response.returncode == 0 else "offline"

        mapped_devices.append({
            "id": device.id,
            "hostname": device.hostname,
            "ip_address": device.ip_address,
            "device_type": device.device_type,
            "os_type": device.os_type,
            "username": device.username,
            "status": status
            
        })
    return mapped_devices

# 6. Switch Configuration Generator (POST)
@app.post("/generate-config/")
def generate_config(request: schemas.SwitchConfigRequest):
    try:
        template = template_env.get_template("cisco_switch.j2")
        rendered_config = template.render(
            hostname=request.hostname,
            management_ip=request.management_ip,
            default_gateway=request.default_gateway,
            vlans=[vlan.model_dump() for vlan in request.vlans]
        )
        return {"status": "success", "config": rendered_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# 7. Netmiko SSH connection  single backup(POST)
@app.post("/backup-device/{device_id}")
def backup_device(device_id: int, options: schemas.BackupOptions, db: Session = Depends(get_db)):
    
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    connection_params = {
        'device_type': 'cisco_ios',
        'host': device.ip_address,
        'username': device.username,
        'password': 'Werfds123'
    }

    try:
        with ConnectHandler(**connection_params) as net_connect:
            net_connect.enable()
            config_data = ""

            # Action 1: Write to NVRAM
            if options.save_nvram:
                net_connect.save_config()

            # Action 2: Save to Flash Overwriting the old one
            if options.save_flash:
                net_connect.send_command_timing("copy running-config flash:VNMS_Last_Good.cfg")
                net_connect.send_command_timing("\n") 

            # Action 3: Pull config if we are downloading OR archiving
            if options.download_local or options.save_archive:
                raw_config = net_connect.send_command("show running-config")
                clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                config_data = "\n".join(clean_lines)

        # --- OUTSIDE THE SSH CONNECTION: Process the files ---
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os_type = device.os_type or "UnknownOS"
        dev_type = device.device_type or "UnknownDevice"
        
        custom_prefix = options.prefix.strip() if options.prefix else "Backup"
        strict_filename = f"{custom_prefix}_{os_type}_{dev_type}_{device.hostname}_{timestamp}.txt"
        
        # Save to Server Archive explicitly
        if options.save_archive:
            archive_path = os.path.join(ARCHIVE_DIR, strict_filename)
            with open(archive_path, "w") as f:
                f.write(config_data)

        return {
            "hostname": device.hostname, 
            "config": config_data, 
            "filename": strict_filename
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SSH Connection Failed: {str(e)}")

# 8. Bulk Backup (POST)
@app.post("/bulk-backup")
def bulk_backup(request: schemas.BulkBackupRequest, db: Session = Depends(get_db)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for dev_id in request.device_ids:
            device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == dev_id).first()
            if device:
                connection_params = {
                    'device_type': 'cisco_ios',
                    "host": device.ip_address,
                    'username': device.username,
                    'password': 'Werfds123'
                }
                try:
                    with ConnectHandler(**connection_params) as net_connect:
                        net_connect.enable()

                        if request.options.save_nvram:
                            net_connect.save_config()
                        
                        if request.options.save_flash:
                            net_connect.send_command_timing("copy running-config flash:VNMS_Last_Good.cfg")
                            net_connect.send_command_timing("\n")
                        
                        # Pull config if downloading OR archiving
                        if request.options.download_local or request.options.save_archive:
                            raw_config = net_connect.send_command("show running-config")
                            clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                            config = "\n".join(clean_lines)
                            
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            os_type = device.os_type or "UnknownOS"
                            dev_type = device.device_type or "UnknownDevice"
                            
                            custom_prefix = request.options.prefix.strip() if request.options.prefix else "Backup"
                            strict_filename = f"{custom_prefix}_{os_type}_{dev_type}_{device.hostname}_{timestamp}.txt"
                            
                            # Save to Archive
                            if request.options.save_archive:
                                archive_path = os.path.join(ARCHIVE_DIR, strict_filename)
                                with open(archive_path, "w") as f:
                                    f.write(config)

                            # Save to ZIP
                            if request.options.download_local:
                                zip_file.writestr(strict_filename, config)

                except Exception as e:
                    if request.options.download_local:
                        zip_file.writestr(f"{device.hostname}_ERROR.txt", f"Failed: {str(e)}")

    zip_buffer.seek(0)

    if not request.options.download_local:
        return {"message": "Backup completed successfully on devices."}
    
    master_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=VNMS_Bulk_Backup_{master_timestamp}.zip"}
    )
# 9. RESTORE BACKUPS TO DEVICES (POST)
@app.post("/restore-devices/")
async def restore_devices(
    device_ids: str = Form(...),
    file: Optional[UploadFile] = File(None),
    archive_file: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
        import shutil
        try:
            target_ids = json.loads(device_ids)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid device_ids format.")
        
        devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.id.in_(target_ids)).all()
        if not devices:
            raise HTTPException(status_code=404, detail=("No valid devices found."))
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Determine where the file is coming from
            if file and file.filename:
                actual_filename = file.filename
                file_path = os.path.join(tmpdir, actual_filename)
                content = await file.read()
                with open(file_path, "wb") as f:
                    f.write(content)
            
            elif archive_file:
                actual_filename = archive_file
                source_path = os.path.join(ARCHIVE_DIR, archive_file)
                if not os.path.exists(source_path):
                    raise HTTPException(status_code=404, detail="Archive file not found.")
                file_path = os.path.join(tmpdir, archive_file)
            else:
                raise HTTPException(status_code=400, detail="No configuration file provided.")
            
            extracted_files = {}
        


# --- PHASE 1: FILE MAPPING (STRICT ENFORCEMENT) ---
            if actual_filename.endswith(".zip"):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                    for dev in devices:
                        match_found = False
                        for extracted_name in zip_ref.namelist():
                            if f"_{dev.hostname}_" in extracted_name:
                                extracted_files[dev.hostname] = os.path.join(tmpdir, extracted_name)
                                match_found = True
                                break
                        if not match_found:
                            raise HTTPException(status_code=400, detail=f"Bluk Restore Aborted: Could not find '{dev.hostname}' in ZIP.")
                        
            else:
                for dev in devices:
                    if f"_{dev.hostname}_" in actual_filename:
                        extracted_files[dev.hostname] = file_path
                    else:
                        raise HTTPException(status_code=400, detail=f"Safety Abort: '{actual_filename} does not match target '{dev.hostname}'.'")
                    

# --- PHASE 2: GENERATE ANSIBLE INVENTORY ---
        inventory_path = os.path.join(tmpdir, "inventory.ini")
        with open(inventory_path, "w") as inv:
            inv.write("[targets]\n")
            for dev in devices:
                target_file = extracted_files.get(dev.hostname, "")
                if target_file:
                    # FIX: Added Privilege Escalation (become) so Ansible can enter config mode
                    inv.write(
                        f'{dev.hostname} '
                        f'ansible_host={dev.ip_address} '
                        f'ansible_user={dev.username} '
                        f'ansible_password=Werfds123 '
                        f'ansible_become=yes '
                        f'ansible_become_method=enable '
                        f'ansible_network_os=cisco.ios.ios '
                        f'ansible_connection=network_cli '
                        f'restore_file="{target_file}"\n'
                    )

# --- PHASE 3: GENERATE ANSIBLE PLAYBOOK ---
        playbook_path = os.path.join(tmpdir, "restore.yml")
        playbook_content = """
---
- name: VNMS Full Configuration Restore via SCP
  hosts: targets
  gather_facts: no
  tasks:
    - name: 1. Securely Transfer Backup File to Switch Flash
      ansible.netcommon.net_put:
        src: "{{ restore_file }}"
        dest: "flash:vnms_restore.cfg"
        protocol: scp

    - name: 2. Force Configuration Replace (Wipe and Mirror)
      cisco.ios.ios_command:
        commands:
          - command: 'configure replace flash:vnms_restore.cfg force'
"""
        with open(playbook_path, "w") as pb:
            pb.write(playbook_content)

        # --- PHASE 4: EXECUTE ANSIBLE ---
        # Temporarily disable host key checking so Ansible doesn't hang on new switches
        env = os.environ.copy()
        env["ANSIBLE_HOST_KEY_CHECKING"] = "Flase"

        # Launch the Ansible process without the old capture_output/text kwargs
        process = await asyncio.create_subprocess_exec(
            "ansible-playbook", "-i", inventory_path, playbook_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        # Wait for Ansible to finish and grab the outputs
        stdout, stderr = await process.communicate()

        # Decode the raw bytes into readable text
        output = stdout.decode()

        if process. returncode != 0 and "unreachable" in output.lower():
            return {"message": "Ansible execution finished with errors", "logs": output}
        
        return {"message": "Restore Operations Completed", "logs": output}
    

# 10. --- SERVER ARCHIVE & COMPARE ENDPOINTS (GET) ---
@app.get("/archive/files")
def get_archive_files(db: Session = Depends(get_db)): # <-- NEW: Brought the Database in!
    """Scans the archive folder and intelligently groups files using the Database Inventory."""
    if not os.path.exists(ARCHIVE_DIR):
        return {}
    
    files = os.listdir(ARCHIVE_DIR)
    
    # Grab all known devices from our inventory
    devices = db.query(models.NetworkDevice).all()
    grouped_files = {}

    for f in files:
        if not f.endswith(".txt"):
            continue
            
        # Figure out which device this file belongs to
        matched_device = None
        for dev in devices:
            if f"_{dev.hostname}_" in f:
                matched_device = dev
                break
        
        # If we found it in the DB, use the official DB attributes!
        if matched_device:
            os_t = matched_device.os_type or "UnknownOS"
            dev_t = matched_device.device_type or "UnknownDevice"
            host = matched_device.hostname
        else:
            # If it's an old test file that doesn't match the DB anymore, quarantine it
            os_t = "Unassigned"
            dev_t = "Unknown"
            host = "Orphaned_Files"

        # Build the dictionary
        if os_t not in grouped_files:
            grouped_files[os_t] = {}
        if dev_t not in grouped_files[os_t]:
            grouped_files[os_t][dev_t] = {}
        if host not in grouped_files[os_t][dev_t]:
            grouped_files[os_t][dev_t][host] = []

        grouped_files[os_t][dev_t][host].append(f)
    
    # Sort files so newest is first
    for os_t in grouped_files:
        for dev_t in grouped_files[os_t]:
            for host in grouped_files[os_t][dev_t]:
                grouped_files[os_t][dev_t][host].sort(reverse=True)

    return grouped_files

@app.post("/compare/")
async def compare_configs(
    upload_file1: Optional[UploadFile] = File(None),
    archive_file1: Optional[str] = Form(None),
    upload_file2: Optional[UploadFile] = File(None),
    archive_file2: Optional[str] = Form(None)
):
    config1 = ""
    config2 = ""

    # --- RESOLVE FILE 1 (Left Side) ---
    if upload_file1:
        config1 = (await upload_file1.read()).decode('utf-8', errors='ignore')
        desc1 = upload_file1.filename
    elif archive_file1:
        path1 = os.path.join(ARCHIVE_DIR, archive_file1)
        if not os.path.exists(path1):
            raise HTTPException(status_code=404, detail="File 1 not found in archive.")
        with open(path1, "r", encoding="utf-8", errors="ignore") as f1:
            config1 = f1.read()
        desc1 = archive_file1
    else:
        raise HTTPException(status_code=400, detail="Missing File 1")

    # --- RESOLVE FILE 2 (Right Side) ---
    if upload_file2:
        config2 = (await upload_file2.read()).decode('utf-8', errors='ignore')
        desc2 = upload_file2.filename
    elif archive_file2:
        path2 = os.path.join(ARCHIVE_DIR, archive_file2)
        if not os.path.exists(path2):
            raise HTTPException(status_code=404, detail="File 2 not found in archive.")
        with open(path2, "r", encoding="utf-8", errors="ignore") as f2:
            config2 = f2.read()
        desc2 = archive_file2
    else:
        raise HTTPException(status_code=400, detail="Missing File 2")

    # --- SMART SCRUBBER ---
    config1 = re.sub(r'^! Last configuration change.*$\n?', '', config1, flags=re.MULTILINE)
    config2 = re.sub(r'^! Last configuration change.*$\n?', '', config2, flags=re.MULTILINE)
    config1 = re.sub(r'^! NVRAM config last updated.*$\n?', '', config1, flags=re.MULTILINE)
    config2 = re.sub(r'^! NVRAM config last updated.*$\n?', '', config2, flags=re.MULTILINE)

    if config1 == config2:
        return {"match": True, "html": "<div style='padding: 20px; color: #4caf50; font-weight: bold; text-align: center;'>✅ Configurations are a 100% perfect match. Zero drift detected.</div>"}
    
    # Generate highlighted HTML diff
    diff_lines = list(difflib.unified_diff(
        config1.splitlines(),
        config2.splitlines(),
        fromfile=desc1,
        tofile=desc2,
        n=3
    ))

    html_output = "<pre style='font-family: monospace; font-size: 14px; line-height: 1.4;'>"
    for line in diff_lines:
        safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if safe_line.startswith("---") or safe_line.startswith("+++"):
            html_output += f"<strong style='color: #fff;'>{safe_line}</strong>\n"
        elif safe_line.startswith("@@"):
            html_output += f"<span style='color: #aaa;'>{safe_line}</span>\n"
        elif safe_line.startswith("-"):
            html_output += f"<span style='color: #4caf50;'>{safe_line}</span>\n"  # Baseline = Green
        elif safe_line.startswith("+"):
            html_output += f"<span style='color: #007acc;'>{safe_line}</span>\n"  # Target = Blue
        else:
            html_output += f"<span style='color: #d4d4d4;'>{safe_line}</span>\n"
    html_output += "</pre>"

    return {"match": False, "html": html_output}