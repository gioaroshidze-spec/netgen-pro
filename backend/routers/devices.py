from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
import subprocess

# We define the router here. 
router = APIRouter(tags=["Inventory & Devices"])

@router.post("/device/", response_model=schemas.DeviceResponse)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db)):
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
    return db_device

@router.put("/device/{device_id}", response_model=schemas.DeviceResponse)
def update_device(device_id: int, device_update: schemas.DeviceUpdate, db: Session = Depends(get_db)):
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
    for key, value in update_data.items():
        setattr(db_device, key, value)

    db.commit()
    db.refresh(db_device)
    return db_device

@router.delete("/device/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    db_device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(db_device)
    db.commit()
    return {"message": "Device deleted"}


# 5. Network Mapper (GET)
@router.get("/network-map/")
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