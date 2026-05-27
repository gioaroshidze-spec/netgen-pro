import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from database import get_db, SessionLocal
import models, schemas
from routers.auth import get_current_user, get_current_admin
from netmiko import ConnectHandler
from logger import log_event

router = APIRouter(tags=["Topology & Power"])

@router.get("/topology/edges", response_model=List[schemas.EdgeResponse])
def get_topology_edges(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Returns all discovered device connections for line drawings."""
    return db.query(models.TopologyEdge).all()

@router.post("/topology/update-coordinates")
def update_coordinates(nodes: List[schemas.CoordinateUpdate], db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Saves node layout coordinates when a user moves icons around Packet Tracer-style."""
    for node in nodes:
        device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == node.id).first()
        if device:
            device.pos_x = node.pos_x
            device.pos_y = node.pos_y
    db.commit()
    return {"status": "success", "message": "Layout coordinates saved configuration-wide."}

def background_reboot(device_id: int, username: str):
    """Background task that logs into a switch/router and issues a write mem + reload."""
    db = SessionLocal()
    try:
        device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
        if not device:
            return

        # Dynamically switch between Netmiko system driver profiles
        netmiko_os = 'hp_procurve' if device.os_type in ['aruba', 'hpe'] else 'cisco_ios'
        if device.os_type == 'mikrotik':
            netmiko_os = 'mikrotik_routeros'

        connection_params = {
            'device_type': netmiko_os,
            'host': device.ip_address,
            'username': device.username,
            'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
        }

        with ConnectHandler(**connection_params) as net_connect:
            net_connect.enable()
            
            if device.os_type in ['cisco', 'aruba', 'hpe']:
                print(f"[REBOOT ENGINE] Saving config changes on {device.hostname}...")
                net_connect.send_command("write memory")
                print(f"[REBOOT ENGINE] Sending reload sequence command to {device.hostname}...")
                net_connect.send_command_timing("reload\n")
                net_connect.send_command_timing("y\n") 
            
            elif device.os_type == 'mikrotik':
                print(f"[REBOOT ENGINE] Informing RouterOS {device.hostname} to restart...")
                net_connect.send_command_timing("/system reboot\n")
                net_connect.send_command_timing("y\n")

        log_event(
            db=db, event_type="Maintenance", severity="WARNING", author=username,
            target_devices=[device.hostname],
            details={"action": "Device Reboot Initiated", "status": "Reload command sent successfully via SSH"}
        )
    except Exception as e:
        print(f"[REBOOT ENGINE] Failed to reboot device {device_id}: {str(e)}")
        log_event(
            db=db, event_type="Maintenance", severity="ERROR", author=username,
            target_devices=[device.hostname if 'device' in locals() else f"ID: {device_id}"],
            details={"action": "Device Reboot Failed", "error": str(e)}
        )
    finally:
        db.close()

@router.post("/device/{device_id}/reboot")
def trigger_device_reboot(device_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    """RBAC secured endpoint to safely trigger background hardware restarts."""
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Target network device not found.")

    background_tasks.add_task(background_reboot, device.id, current_user.username)
    return {"message": f"Reboot instruction queued for {device.hostname}. Connection will drop momentarily."}