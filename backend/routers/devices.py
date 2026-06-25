from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
import subprocess
from logger import log_event
import re
import subprocess
import concurrent.futures

# --- NEW: IMPORT THE BOUNCERS ---
from routers.auth import get_current_user, get_current_admin, encrypt_secret

router = APIRouter(tags=["Inventory & Devices"])

# CREATE requires ADMIN
@router.post("/device/", response_model=schemas.DeviceResponse)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    existing_host = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname == device.hostname).first()
    if existing_host:
        raise HTTPException(status_code=400, detail=f"Error: Hostname '{device.hostname}' is already taken.")
        
    existing_ip = db.query(models.NetworkDevice).filter(models.NetworkDevice.ip_address == device.ip_address).first()
    if existing_ip:
        raise HTTPException(status_code=400, detail=f"Error: IP Address '{device.ip_address}' is already in use.")

    # 1. Safely load the data without the raw password
    device_data = device.model_dump(exclude={"password"})
    db_device = models.NetworkDevice(**device_data)

    # 2. Encrypt and attach the password
    if device.password:
        db_device.encrypted_password = encrypt_secret(device.password)

    # 3. Add to DB directly (Removed the buggy overwrite line!)
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    
    log_event(
        db=db, event_type="Inventory", severity="SUCCESS", author=current_user.username,
        target_devices=[db_device.hostname], 
        details={"action": "Created new device", "ip_address": db_device.ip_address}
    )
    return db_device

# UPDATE requires ADMIN
@router.put("/device/{device_id}", response_model=schemas.DeviceResponse)
def update_device(device_id: int, device_update: schemas.DeviceUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    db_device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
        
    if device_update.hostname and device_update.hostname != db_device.hostname:
        existing_host = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname == device_update.hostname).first()
        if existing_host:
            raise HTTPException(status_code=400, detail=f"Error: Hostname '{device_update.hostname}' is already taken.")

    if device_update.ip_address and device_update.ip_address != db_device.ip_address:
        existing_ip = db.query(models.NetworkDevice).filter(models.NetworkDevice.ip_address == device_update.ip_address).first()
        if existing_ip:
            raise HTTPException(status_code=400, detail=f"Error: IP Address '{device_update.ip_address}' is already in use.")
    
    # --- THE FIX: Initialize the changes dictionary ---
    changes = {}
    
    update_data = device_update.model_dump(exclude_unset=True, exclude={"password"})
    for key, value in update_data.items():
        if getattr(db_device, key) != value:
            changes[key] = value # Track what changed
        setattr(db_device, key, value)
        
    if device_update.password:
        db_device.encrypted_password = encrypt_secret(device_update.password)
        changes["password"] = "Updated (Encrypted)" # Keep the actual password out of the logs!

    db.commit()
    db.refresh(db_device)
    
    if changes:
        log_event(
            db=db, event_type="Inventory", severity="INFO", author=current_user.username,
            target_devices=[db_device.hostname], 
            details={"action": "Updated device parameters", "changes": changes}
        )
    return db_device

# DELETE requires ADMIN
@router.delete("/device/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    db_device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    hostname = db_device.hostname 
    db.delete(db_device)
    db.commit()
    
    log_event(
        db=db, event_type="Inventory", severity="WARNING", author=current_user.username,
        target_devices=[hostname], details={"action": "Deleted device from inventory"}
    )
    return {"message": "Device deleted"}

@router.get("/network-map/")
def get_network_map(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    devices = db.query(models.NetworkDevice).all()
    
    def ping_device(device):
        clean_ip = device.ip_address.strip()
        command = ["ping", "-c", "1", "-W", "1", clean_ip]
        response = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if response.returncode != 0:
            return {
                "id": device.id, "hostname": device.hostname, "ip_address": device.ip_address,
                "device_type": device.device_type, "os_type": device.os_type,
                "username": device.username, "status": "offline", "latency": "N/A",
                "pos_x": device.pos_x, "pos_y": device.pos_y, "zone_id": device.zone_id,
                "is_legacy": getattr(device, 'is_legacy', False) # <-- ADDED THIS
            }
        else:
            match = re.search(r'time=([\d.]+)\s*ms', response.stdout)
            latency = f"{match.group(1)}ms" if match else "<1ms"
            
            return {
                "id": device.id, "hostname": device.hostname, "ip_address": device.ip_address,
                "device_type": device.device_type, "os_type": device.os_type,
                "username": device.username, "status": "online", "latency": latency,
                "pos_x": device.pos_x, "pos_y": device.pos_y, "zone_id": device.zone_id,
                "is_legacy": getattr(device, 'is_legacy', False) # <-- ADDED THIS
            }

    # Blast out all pings simultaneously (Lightning fast)
    mapped_devices = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(ping_device, devices)
        for res in results:
            mapped_devices.append(res)

    return mapped_devices