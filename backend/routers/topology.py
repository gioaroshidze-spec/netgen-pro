import os
import re
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
    """Saves node layout coordinates."""
    for node in nodes:
        device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == node.id).first()
        if device:
            device.pos_x = node.pos_x
            device.pos_y = node.pos_y
    db.commit()
    return {"status": "success", "message": "Layout coordinates saved."}

# ==========================================
# --- NEW: AUTOMATED DISCOVERY ENGINE ---
# ==========================================
def background_discovery(username: str):
    """Logs into switches, reads CDP/LLDP tables, and builds the topology map."""
    db = SessionLocal()
    try:
        print("[DISCOVERY ENGINE] Starting Automated Network Discovery...")
        
        # 1. Wipe the old map edges clean so we don't get duplicates
        db.query(models.TopologyEdge).delete()
        db.commit()
        
        devices = db.query(models.NetworkDevice).all()
        managed_hostnames = {d.hostname for d in devices}
        discovered_edges = 0
        rogue_devices_found = []

        for device in devices:
            # For Phase 3, we focus on Cisco CDP parsing
            if device.os_type == 'cisco':
                connection_params = {
                    'device_type': 'cisco_ios',
                    'host': device.ip_address,
                    'username': device.username,
                    'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
                    'fast_cli': True
                }

                try:
                    with ConnectHandler(**connection_params) as net_connect:
                        net_connect.enable()
                        output = net_connect.send_command("show cdp neighbors")
                        
                        # --- THE PARSER ---
                        # Skip header lines and empty lines
                        lines = [line.strip() for line in output.splitlines() if line.strip() and not line.startswith("Capability") and not line.startswith("Device ID")]
                        
                        for line in lines:
                            # Typical Cisco CDP Line:
                            # cctv_sw2.local    Gig 1/0/1         120      S I      WS-C2960X Gig 1/0/24
                            parts = re.split(r'\s+', line)
                            
                            if len(parts) >= 6:
                                # Clean the target hostname (strip domain names if present)
                                raw_target = parts[0].split('.')[0]
                                
                                # Reconstruct port names (e.g. ['Gig', '1/0/1'] -> 'Gig1/0/1')
                                source_port = f"{parts[1]}{parts[2]}" 
                                target_port = f"{parts[-2]}{parts[-1]}"
                                
                                # Trunk detection logic (simplified for UI mapping)
                                link_type = "trunk" if "Gig" in source_port or "Ten" in source_port else "access"
                                
                                new_edge = models.TopologyEdge(
                                    source_hostname=device.hostname,
                                    source_port=source_port,
                                    target_hostname=raw_target,
                                    target_port=target_port,
                                    link_type=link_type,
                                    current_utilization=0.0
                                )
                                db.add(new_edge)
                                discovered_edges += 1
                                
                                if raw_target not in managed_hostnames:
                                    rogue_devices_found.append(raw_target)

                except Exception as e:
                    print(f"[DISCOVERY ENGINE] Failed to map {device.hostname}: {e}")

        db.commit()
        
        log_event(
            db=db, event_type="Inventory", severity="SUCCESS", author=username, target_devices=[],
            details={"action": "Automated Topology Discovery Completed", "edges_mapped": discovered_edges, "rogues_detected": rogue_devices_found}
        )
        print(f"[DISCOVERY ENGINE] Map Built! {discovered_edges} connections found.")

    except Exception as e:
        print(f"[DISCOVERY ENGINE] Fatal Error: {str(e)}")
        log_event(db=db, event_type="Inventory", severity="ERROR", author=username, details={"action": "Discovery Failed", "error": str(e)})
    finally:
        db.close()

@router.post("/topology/discover")
def trigger_discovery(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    """API Endpoint to trigger the discovery worker."""
    background_tasks.add_task(background_discovery, current_user.username)
    return {"message": "Automated Network Discovery initiated. The map will update shortly."}

# ==========================================
# --- KEEP REBOOT FUNCTION BELOW ---
# ==========================================
def background_reboot(device_id: int, username: str):
    # [KEEP YOUR EXISTING REBOOT FUNCTION EXACTLY AS IT WAS]
    db = SessionLocal()
    try:
        device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
        if not device: return

        netmiko_os = 'hp_procurve' if device.os_type in ['aruba', 'hpe'] else 'cisco_ios'
        if device.os_type == 'mikrotik': netmiko_os = 'mikrotik_routeros'

        connection_params = { 'device_type': netmiko_os, 'host': device.ip_address, 'username': device.username, 'password': os.getenv("DEVICE_PASSWORD", "Werfds123") }

        with ConnectHandler(**connection_params) as net_connect:
            net_connect.enable()
            if device.os_type in ['cisco', 'aruba', 'hpe']:
                net_connect.send_command("write memory")
                net_connect.send_command_timing("reload\n")
                net_connect.send_command_timing("y\n") 
            elif device.os_type == 'mikrotik':
                net_connect.send_command_timing("/system reboot\n")
                net_connect.send_command_timing("y\n")

        log_event(db=db, event_type="Maintenance", severity="WARNING", author=username, target_devices=[device.hostname], details={"action": "Device Reboot Initiated", "status": "Reload command sent"})
    except Exception as e:
        log_event(db=db, event_type="Maintenance", severity="ERROR", author=username, target_devices=[device.hostname if 'device' in locals() else f"ID: {device_id}"], details={"action": "Device Reboot Failed", "error": str(e)})
    finally:
        db.close()

@router.post("/device/{device_id}/reboot")
def trigger_device_reboot(device_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not device: raise HTTPException(status_code=404, detail="Target network device not found.")
    background_tasks.add_task(background_reboot, device.id, current_user.username)
    return {"message": f"Reboot instruction queued for {device.hostname}. Connection will drop momentarily."}