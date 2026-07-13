from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from datetime import datetime
from database import get_db
import models, schemas
import os, io, zipfile, json
from dotenv import load_dotenv
import tempfile
import asyncio
from typing import Optional
import concurrent.futures
from logger import log_event

from routers.auth import get_current_admin
from routers.auth import decrypt_secret
from connection_utils import get_netmiko_params, get_ansible_inventory_vars

load_dotenv()

router = APIRouter(tags=["Maintenance Operations"])
ARCHIVE_DIR = "archive"
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# --- HELPER FOR RICH LOGGING ---
def get_device_meta(device: models.NetworkDevice):
    """Formats device data cleanly for the Event Logs UI."""
    return {
        "hostname": device.hostname,
        "ip_address": device.ip_address,
        "device_type": device.device_type,
        "os_type": device.os_type
    }

# --- THREAD WORKER FOR BACKUPS ---
def process_single_backup(device: models.NetworkDevice, options: schemas.BackupOptions) -> dict:
    """
    Isolated Netmiko worker function for ThreadPoolExecutor.
    Handles the SSH connection and returns the raw configuration string.
    """
    show_cmd = "show running-config"
    if device.os_type == 'mikrotik': show_cmd = "/export"
    elif device.os_type in ['alcatel', 'alcatel-lucent']: show_cmd = "show configuration snapshot"

    connection_params = get_netmiko_params(device)

    try:
        with ConnectHandler(**connection_params) as net_connect:
            if device.os_type != 'mikrotik':
                try: net_connect.enable()
                except: pass
                
            config_data = ""

            if options.save_nvram and device.os_type != 'mikrotik': 
                try: net_connect.save_config()
                except: pass
                
            if options.save_flash:
                if device.os_type == 'cisco':
                    net_connect.send_command_timing("copy running-config flash:VNMS_Last_Good.cfg\n")
                elif device.os_type == 'mikrotik':
                    net_connect.send_command("/export file=VNMS_Last_Good")
                    
            if options.download_local or options.save_archive:
                raw_config = net_connect.send_command(show_cmd)
                clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                config_data = "\n".join(clean_lines)

        return {
            "hostname": device.hostname,
            "os_type": device.os_type or "UnknownOS",
            "dev_type": device.device_type or "UnknownDevice",
            "success": True,
            "config": config_data
        }

    except (NetmikoTimeoutException, NetmikoAuthenticationException) as e:
        return {"hostname": device.hostname, "success": False, "error": "Connection Timeout or Auth Failed"}
    except Exception as e:
        return {"hostname": device.hostname, "success": False, "error": str(e)}


# 7. Single Backup (POST) - MULTI-VENDOR
@router.post("/backup-device/{device_id}")
def backup_device(device_id: int, options: schemas.BackupOptions, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not device: raise HTTPException(status_code=404, detail="Device not found")
    
    result = process_single_backup(device, options)
    
    if not result["success"]:
        log_event(
            db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, 
            target_devices=[get_device_meta(device)], 
            details={
                "action": "Configuration Backup", 
                "mode": "Single",
                "execution_status": "Failed",
                "error": result["error"],
                "options": options.model_dump()
            }
        )
        raise HTTPException(status_code=500, detail=f"SSH Connection Failed: {result['error']}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    custom_prefix = options.prefix.strip() if options.prefix else "Backup"
    strict_filename = f"{custom_prefix}_{result['os_type']}_{result['dev_type']}_{result['hostname']}_{timestamp}.txt"
    
    if options.save_archive:
        archive_path = os.path.join(ARCHIVE_DIR, strict_filename)
        with open(archive_path, "w") as f:
            f.write(result["config"])

    log_event(
        db=db, event_type="Maintenance", severity="SUCCESS", author=current_user.username,
        target_devices=[get_device_meta(device)],
        details={
            "action": "Configuration Backup", 
            "mode": "Single",
            "execution_status": "Success",
            "filename": strict_filename, 
            "options": options.model_dump()
        }
    )
    return {"message": "Backup completed successfully.", "hostname": device.hostname, "config": result["config"], "filename": strict_filename}


# 8. Bulk Backup (POST) - MULTI-VENDOR MULTITHREADED
@router.post("/bulk-backup")
def bulk_backup(request: schemas.BulkBackupRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.id.in_(request.device_ids)).all()
    if not devices:
        raise HTTPException(status_code=404, detail="No valid devices found.")

    results = []
    
    # Blast out SSH connections concurrently to prevent 504 Timeouts
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        future_to_device = {executor.submit(process_single_backup, dev, request.options): dev for dev in devices}
        
        for future in concurrent.futures.as_completed(future_to_device):
            device = future_to_device[future]
            try:
                res = future.result()
                results.append(res)
            except Exception as exc:
                results.append({"hostname": device.hostname, "success": False, "error": str(exc)})

    zip_buffer = io.BytesIO()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Compile the results into the zip buffer or archive folder
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for res in results:
            custom_prefix = request.options.prefix.strip() if request.options.prefix else "Backup"
            
            if res["success"]:
                strict_filename = f"{custom_prefix}_{res['os_type']}_{res['dev_type']}_{res['hostname']}_{timestamp}.txt"
                
                if request.options.save_archive:
                    archive_path = os.path.join(ARCHIVE_DIR, strict_filename)
                    with open(archive_path, "w") as f:
                        f.write(res["config"])
                        
                if request.options.download_local:
                    zip_file.writestr(strict_filename, res["config"])
            else:
                if request.options.download_local:
                    zip_file.writestr(f"{res['hostname']}_ERROR.txt", f"Failed: {res.get('error')}")

    # Determine dynamic statuses
    has_failures = any(not res["success"] for res in results)
    final_severity = "WARNING" if has_failures else "SUCCESS"
    final_status = "Partial Failure" if has_failures else "Success"

    log_event(
        db=db, event_type="Maintenance", severity=final_severity, author=current_user.username,
        target_devices=[get_device_meta(d) for d in devices],
        details={
            "action": "Configuration Backup",
            "mode": "Bulk",
            "execution_status": final_status,
            "saved_to_archive": request.options.save_archive,
            "options": request.options.model_dump(),
            "failures": [res["hostname"] for res in results if not res["success"]]
        }
    )

    if not request.options.download_local:
        if has_failures:
            return {"message": "Bulk backup finished with some errors. Please check the Event Logs.", "has_failures": True}
        return {"message": "Backup completed successfully on all devices.", "has_failures": False}
    
    zip_buffer.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename=VNMS_Bulk_Backup_{timestamp}.zip",
        "X-Backup-Status": "Partial-Failure" if has_failures else "Success"
    }
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)


# 9. RESTORE BACKUPS TO DEVICES (POST) - SECURED
@router.post("/restore-devices/")
async def restore_devices(
    device_ids: str = Form(...),
    file: Optional[UploadFile] = File(None),
    archive_file: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    source_type = "Local Upload" if file else "Server Archive"
    
    try:
        target_ids = json.loads(device_ids)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid device_ids format.")
    
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.id.in_(target_ids)).all()
    if not devices:
        raise HTTPException(status_code=404, detail="No valid devices found.")
    
    mode_type = "Bulk" if len(devices) > 1 else "Single"

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
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
                    raise ValueError("Archive file not found on server.")
                file_path = os.path.join(tmpdir, archive_file)
                import shutil
                shutil.copy2(source_path, file_path)
            else:
                raise ValueError("No configuration file provided.")
            
            extracted_files = {}
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
                            raise ValueError(f"Bulk Restore Aborted: Could not find '{dev.hostname}' config inside ZIP.")
            else:
                for dev in devices:
                    if f"_{dev.hostname}_" in actual_filename:
                        extracted_files[dev.hostname] = file_path
                    else:
                        raise ValueError(f"Safety Abort: '{actual_filename}' does not safely match target '{dev.hostname}'.")
                    
            # --- DYNAMIC MULTI-VENDOR INVENTORY ---
            inventory_path = os.path.join(tmpdir, "inventory.ini")
            with open(inventory_path, "w") as inv:
                inv.write("[targets]\n")
                for dev in devices:
                    target_file = extracted_files.get(dev.hostname, "")
                    if target_file:
                        vars_dict = get_ansible_inventory_vars(dev)
                        vars_string = " ".join([f'{k}="{v}"' if " " in str(v) else f'{k}={v}' for k, v in vars_dict.items()])
                        inv.write(f'{dev.hostname} {vars_string} restore_file="{target_file}"\n')

            # --- MULTI-VENDOR RESTORE PLAYBOOK ---
            playbook_path = os.path.join(tmpdir, "restore.yml")
            playbook_content = """
---
- name: VNMS Multi-Vendor Configuration Restore
  hosts: targets
  gather_facts: no
  tasks:
    - name: (CISCO) Transfer Backup File
      ansible.netcommon.net_put:
        src: "{{ restore_file }}"
        dest: "flash:vnms_restore.cfg"
        protocol: scp
      when: ansible_network_os == 'cisco.ios.ios'

    - name: (CISCO) Force Configuration Replace
      cisco.ios.ios_command:
        commands:
          - command: 'configure replace flash:vnms_restore.cfg force'
      when: ansible_network_os == 'cisco.ios.ios'

    - name: (MIKROTIK) Transfer Backup File
      ansible.netcommon.net_put:
        src: "{{ restore_file }}"
        dest: "vnms_restore.rsc"
        protocol: scp
      when: ansible_network_os == 'community.routeros.routeros'

    - name: (MIKROTIK) Execute Import Script
      community.routeros.command:
        commands:
          - "/import file-name=vnms_restore.rsc"
      when: ansible_network_os == 'community.routeros.routeros'

    - name: (HPE/ARUBA) Push Full Config via Src
      community.network.aruba_config:
        src: "{{ restore_file }}"
      when: ansible_network_os in ['community.network.aruba', 'arubanetworks.aoscx.aoscx']
      
    - name: (ALCATEL) Push Full Config
      ansible.netcommon.cli_config:
        config: "{{ lookup('file', restore_file) }}"
      when: ansible_network_os == 'community.network.alcatel_aos'
"""
            with open(playbook_path, "w") as pb:
                pb.write(playbook_content)

            env = os.environ.copy()
            env["ANSIBLE_HOST_KEY_CHECKING"] = "False"

            process = await asyncio.create_subprocess_exec(
                "ansible-playbook", "-i", inventory_path, playbook_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
            )

            stdout, stderr = await process.communicate()
            output = stdout.decode()

            if process.returncode != 0 or "unreachable" in output.lower() or "failed" in output.lower():
                log_event(
                    db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, 
                    target_devices=[get_device_meta(d) for d in devices], 
                    details={"action": "Configuration Restore", "mode": mode_type, "source": source_type, "file": actual_filename, "execution_status": "Failed", "ansible_logs": output[-2000:] if output else ""}
                )
                return {"message": "Restore finished with errors. Check Event Logs.", "logs": output, "success": False}
            
            log_event(
                db=db, event_type="Maintenance", severity="SUCCESS", author=current_user.username, 
                target_devices=[get_device_meta(d) for d in devices], 
                details={"action": "Configuration Restore", "mode": mode_type, "source": source_type, "file": actual_filename, "execution_status": "Success", "ansible_logs": output[-2000:] if output else ""}
            )
            return {"message": "Restore Operations Completed Successfully.", "logs": output, "success": True}

    except ValueError as ve:
        # Catch our custom safety validation errors and log them before returning the 400
        log_event(
            db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, 
            target_devices=[get_device_meta(d) for d in devices], 
            details={"action": "Configuration Restore Validation", "mode": mode_type, "source": source_type, "file": getattr(file, 'filename', archive_file), "execution_status": "Aborted", "error": str(ve)}
        )
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        log_event(
            db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, 
            target_devices=[get_device_meta(d) for d in devices], 
            details={"action": "Configuration Restore System Error", "mode": mode_type, "source": source_type, "execution_status": "Failed", "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Internal server error during restore execution.")