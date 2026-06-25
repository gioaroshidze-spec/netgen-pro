from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from netmiko import ConnectHandler
from datetime import datetime
from database import get_db
import models, schemas
import os, io, zipfile, json
from dotenv import load_dotenv
import tempfile
import asyncio
from typing import Optional
from logger import log_event

# --- IMPORT THE BOUNCERS ---
from routers.auth import get_current_admin
from routers.auth import decrypt_secret

load_dotenv()

router = APIRouter(tags=["Maintenance Operations"])
ARCHIVE_DIR = "archive"
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# 7. Single Backup (POST) - SECURED
@router.post("/backup-device/{device_id}")
def backup_device(device_id: int, options: schemas.BackupOptions, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    connection_params = {
        'device_type': 'cisco_ios', 'host': device.ip_address,
        'username': device.username, 'password': decrypt_secret(device.encrypted_password)
    }

    try:
        with ConnectHandler(**connection_params) as net_connect:
            net_connect.enable()
            config_data = ""

            if options.save_nvram: net_connect.save_config()
            if options.save_flash:
                net_connect.send_command_timing("copy running-config flash:VNMS_Last_Good.cfg")
                net_connect.send_command_timing("\n") 
            if options.download_local or options.save_archive:
                raw_config = net_connect.send_command("show running-config")
                clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                config_data = "\n".join(clean_lines)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os_type = device.os_type or "UnknownOS"
        dev_type = device.device_type or "UnknownDevice"
        custom_prefix = options.prefix.strip() if options.prefix else "Backup"
        strict_filename = f"{custom_prefix}_{os_type}_{dev_type}_{device.hostname}_{timestamp}.txt"
        
        if options.save_archive:
            archive_path = os.path.join(ARCHIVE_DIR, strict_filename)
            with open(archive_path, "w") as f:
                f.write(config_data)

        # Log with the exact admin user who did it
        log_event(
            db=db, event_type="Maintenance", severity="SUCCESS", author=current_user.username,
            target_devices=[device.hostname],
            details={"action": "Single Backup", "filename": strict_filename, "options": options.model_dump()}
        )
        return {"hostname": device.hostname, "config": config_data, "filename": strict_filename}
    
    except Exception as e:
        log_event(db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, target_devices=[device.hostname], details={"action": "Single Backup Failed", "error": str(e)})
        raise HTTPException(status_code=500, detail=f"SSH Connection Failed: {str(e)}")

# 8. Bulk Backup (POST) - SECURED
@router.post("/bulk-backup")
def bulk_backup(request: schemas.BulkBackupRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for dev_id in request.device_ids:
            device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == dev_id).first()
            if device:
                connection_params = {
                    'device_type': 'cisco_ios', "host": device.ip_address,
                    'username': device.username, 'password': decrypt_secret(device.encrypted_password)
                }
                try:
                    with ConnectHandler(**connection_params) as net_connect:
                        net_connect.enable()
                        if request.options.save_nvram: net_connect.save_config()
                        if request.options.save_flash:
                            net_connect.send_command_timing("copy running-config flash:VNMS_Last_Good.cfg")
                            net_connect.send_command_timing("\n")
                        
                        if request.options.download_local or request.options.save_archive:
                            raw_config = net_connect.send_command("show running-config")
                            clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                            config = "\n".join(clean_lines)
                            
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            os_type = device.os_type or "UnknownOS"
                            dev_type = device.device_type or "UnknownDevice"
                            custom_prefix = request.options.prefix.strip() if request.options.prefix else "Backup"
                            strict_filename = f"{custom_prefix}_{os_type}_{dev_type}_{device.hostname}_{timestamp}.txt"
                            
                            if request.options.save_archive:
                                archive_path = os.path.join(ARCHIVE_DIR, strict_filename)
                                with open(archive_path, "w") as f:
                                    f.write(config)
                            if request.options.download_local:
                                zip_file.writestr(strict_filename, config)
                except Exception as e:
                    if request.options.download_local:
                        zip_file.writestr(f"{device.hostname}_ERROR.txt", f"Failed: {str(e)}")

    zip_buffer.seek(0)
    target_hostnames = [d.hostname for d in db.query(models.NetworkDevice).filter(models.NetworkDevice.id.in_(request.device_ids)).all()]
    
    log_event(
        db=db, event_type="Maintenance", severity="INFO", author=current_user.username,
        target_devices=target_hostnames,
        details={"action": "Bulk Backup Executed", "saved_to_archive": request.options.save_archive}
    )

    if not request.options.download_local:
        return {"message": "Backup completed successfully on devices."}
    
    master_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=VNMS_Bulk_Backup_{master_timestamp}.zip"})

# 9. RESTORE BACKUPS TO DEVICES (POST) - SECURED
@router.post("/restore-devices/")
async def restore_devices(
    device_ids: str = Form(...),
    file: Optional[UploadFile] = File(None),
    archive_file: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
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
                import shutil
                shutil.copy2(source_path, file_path)
            else:
                raise HTTPException(status_code=400, detail="No configuration file provided.")
            
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
                            raise HTTPException(status_code=400, detail=f"Bluk Restore Aborted: Could not find '{dev.hostname}' in ZIP.")
            else:
                for dev in devices:
                    if f"_{dev.hostname}_" in actual_filename:
                        extracted_files[dev.hostname] = file_path
                    else:
                        raise HTTPException(status_code=400, detail=f"Safety Abort: '{actual_filename}' does not match target '{dev.hostname}'.")
                    
        inventory_path = os.path.join(tmpdir, "inventory.ini")
        with open(inventory_path, "w") as inv:
            inv.write("[targets]\n")
            for dev in devices:
                target_file = extracted_files.get(dev.hostname, "")
                if target_file:
                    inv.write(
                        f'{dev.hostname} ansible_host={dev.ip_address} ansible_user={dev.username} '
                        f'ansible_password={decrypt_secret(dev.encrypted_password)} ansible_become=yes '
                        f'ansible_become_method=enable ansible_network_os=cisco.ios.ios '
                        f'ansible_connection=network_cli restore_file="{target_file}"\n'
                    )

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

        env = os.environ.copy()
        env["ANSIBLE_HOST_KEY_CHECKING"] = "False"

        process = await asyncio.create_subprocess_exec(
            "ansible-playbook", "-i", inventory_path, playbook_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )

        stdout, stderr = await process.communicate()
        output = stdout.decode()

        if process.returncode != 0 and "unreachable" in output.lower():
            log_event(db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, target_devices=[d.hostname for d in devices], details={"action": "Configuration Restore Failed", "file": actual_filename, "logs": output})
            return {"message": "Ansible execution finished with errors", "logs": output}
        
        log_event(db=db, event_type="Maintenance", severity="SUCCESS", author=current_user.username, target_devices=[d.hostname for d in devices], details={"action": "Configuration Restore Successful", "file": actual_filename, "logs": output})
        return {"message": "Restore Operations Completed", "logs": output}