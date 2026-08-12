from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from datetime import datetime
from database import get_db
import models, schemas
import os, io, zipfile, json
from dotenv import load_dotenv
from typing import Optional
import concurrent.futures
from logger import log_event
from backup_service import build_backup_filename
from device_capabilities import (
    AUTOMATED_RESTORE_UNQUALIFIED_REASON, capabilities_by_hostname,
)

from routers.auth import get_current_admin
from connection_utils import get_netmiko_params

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

def _reject_mutating_backup_options(options):
    rejected = []
    if options.save_nvram:
        rejected.append("save_nvram")
    if options.save_flash:
        rejected.append("save_flash")
    if rejected:
        raise HTTPException(
            status_code=422,
            detail=(
                "Backup operations are controller/archive-only and read-only; "
                f"unsupported device mutation option(s): {', '.join(rejected)}."
            ),
        )


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
    _reject_mutating_backup_options(options)
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
    strict_filename = build_backup_filename(custom_prefix, result["os_type"], result["dev_type"], result["hostname"], timestamp)
    
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
    _reject_mutating_backup_options(request.options)
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
                strict_filename = build_backup_filename(custom_prefix, res["os_type"], res["dev_type"], res["hostname"], timestamp)
                
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


# 9. AUTOMATED RESTORE IS DISABLED UNTIL A PROFILE IS QUALIFIED
@router.post("/restore-devices/")
async def restore_devices(
    device_ids: str = Form(...),
    file: Optional[UploadFile] = File(None),
    archive_file: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    try:
        target_ids = json.loads(device_ids)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid device_ids format.")

    devices = db.query(models.NetworkDevice).filter(
        models.NetworkDevice.id.in_(target_ids)
    ).all()
    if not devices:
        raise HTTPException(status_code=404, detail="No valid devices found.")

    source_type = "Local Upload" if file else "Server Archive"
    attempted_file = getattr(file, "filename", None) or (
        os.path.basename(archive_file) if archive_file else None
    )
    details = {
        "action": "Automated Configuration Restore Rejected",
        "execution_status": "Unsupported",
        "source": source_type,
        "file": attempted_file,
        "automated_restore": False,
        "capability_reason": AUTOMATED_RESTORE_UNQUALIFIED_REASON,
        "device_capabilities": capabilities_by_hostname(devices),
        "device_contact_performed": False,
    }
    log_event(
        db=db,
        event_type="Maintenance",
        severity="WARNING",
        author=current_user.username,
        target_devices=[get_device_meta(device) for device in devices],
        details=details,
    )
    raise HTTPException(
        status_code=409,
        detail=(
            "Automated restore is unsupported for the selected platform profile. "
            + AUTOMATED_RESTORE_UNQUALIFIED_REASON
        ),
    )
