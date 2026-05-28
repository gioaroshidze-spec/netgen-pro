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
        
        # 1. Wipe the old map edges clean
        db.query(models.TopologyEdge).delete()
        db.commit()
        
        devices = db.query(models.NetworkDevice).all()
        managed_hostnames = {d.hostname for d in devices}
        discovered_edges = 0
        rogue_devices_found = []
        
        # --- NEW: Track unique node connections to prevent double-cables ---
        processed_pairs = set()

        for device in devices:
            if device.os_type == 'cisco':
                connection_params = {
                    'device_type': 'cisco_ios', 'host': device.ip_address,
                    'username': device.username, 'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
                    'fast_cli': True
                }

                try:
                    with ConnectHandler(**connection_params) as net_connect:
                        net_connect.enable()
                        output = net_connect.send_command("show cdp neighbors")
                        
                        # --- THE ADVANCED FSM PARSER ---
                        lines = [line.strip() for line in output.splitlines() if line.strip()]
                        current_target = None
                        
                        for line in lines:
                            if "Capability" in line or "Device ID" in line or "Total cdp" in line or "entries" in line:
                                continue

                            parts = re.split(r'\s+', line)

                            is_interface_col0 = parts[0].lower().startswith(('gig', 'fas', 'ten', 'eth', 'port'))
                            is_interface_col1 = len(parts) > 1 and parts[1].lower().startswith(('gig', 'fas', 'ten', 'eth', 'port'))
                            
                            if not is_interface_col0 and not is_interface_col1:
                                current_target = parts[0].split('.')[0]
                                continue
                                
                            if is_interface_col0:
                                if not current_target: continue
                                raw_target = current_target
                                source_port = f"{parts[0]}{parts[1]}"
                                target_port = f"{parts[-2]}{parts[-1]}"
                                current_target = None
                            elif is_interface_col1 and len(parts) >= 6:
                                raw_target = parts[0].split('.')[0]
                                source_port = f"{parts[1]}{parts[2]}"
                                target_port = f"{parts[-2]}{parts[-1]}"
                                current_target = None
                            else:
                                continue

                            # --- FUZZY MATCH LOGIC ---
                            clean_target = raw_target
                            for m_host in managed_hostnames:
                                if m_host.lower().replace('_', '').replace('-', '') == raw_target.lower().replace('_', '').replace('-', ''):
                                    clean_target = m_host
                                    break

                            # --- DE-DUPLICATION CHECK ---
                            # Sort hostnames alphabetically to make a bidirectional key
                            link_key = tuple(sorted([device.hostname, clean_target]))
                            if link_key in processed_pairs:
                                continue
                            processed_pairs.add(link_key)

                            link_type = "trunk" if "gig" in source_port.lower() or "ten" in source_port.lower() else "access"
                            
                            new_edge = models.TopologyEdge(
                                source_hostname=device.hostname,
                                source_port=source_port,
                                target_hostname=clean_target,
                                target_port=target_port,
                                link_type=link_type,
                                current_utilization=0.0
                            )
                            db.add(new_edge)
                            discovered_edges += 1
                            
                            if clean_target not in managed_hostnames:
                                rogue_devices_found.append(clean_target)

                except Exception as e:
                    print(f"[DISCOVERY ENGINE] Failed to map {device.hostname}: {e}")

        db.commit()
        log_event(db=db, event_type="Inventory", severity="SUCCESS", author=username, target_devices=[], details={"action": "Automated Topology Discovery Completed", "edges_mapped": discovered_edges})
        print(f"[DISCOVERY ENGINE] Map Built! {discovered_edges} unique connections found.")

    except Exception as e:
        print(f"[DISCOVERY ENGINE] Fatal Error: {str(e)}")
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