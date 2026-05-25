from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
import subprocess
from logger import log_event

# --- NEW: IMPORT THE BOUNCERS ---
from routers.auth import get_current_user, get_current_admin

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

    db_device = models.NetworkDevice(**device.model_dump())
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
    
    update_data = device_update.model_dump(exclude_unset=True)
    changes = {}
    for key, value in update_data.items():
        old_value = getattr(db_device, key)
        if old_value != value:
            changes[key] = {"old": old_value, "new": value}
        setattr(db_device, key, value)

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

# READING INVENTORY requires ANY LOGGED-IN USER
@router.get("/network-map/")
def get_network_map(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    devices = db.query(models.NetworkDevice).all()
    mapped_devices = []

    for device in devices:
        clean_ip = device.ip_address.strip()
        command = ["ping", "-c", "1", "-W", "1", clean_ip]
        response = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if response.returncode != 0:
            print(f"PING FAILED for {clean_ip}")
        
        status = "online" if response.returncode == 0 else "offline"

        mapped_devices.append({
            "id": device.id, "hostname": device.hostname, "ip_address": device.ip_address,
            "device_type": device.device_type, "os_type": device.os_type,
            "username": device.username, "status": status
        })
    return mapped_devices