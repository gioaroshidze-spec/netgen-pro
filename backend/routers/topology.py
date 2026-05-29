import os
import re
import time
import uuid
import tempfile
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from database import get_db, SessionLocal
import models, schemas
from routers.auth import get_current_user, get_current_admin
from netmiko import ConnectHandler, file_transfer
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
# --- AUTOMATED DISCOVERY ENGINE ---
# ==========================================
def background_discovery(username: str):
    """Logs into switches, reads CDP/LLDP & STP tables, and builds the topology map via Transactional Merge."""
    db = SessionLocal()
    try:
        print("[DISCOVERY ENGINE] Starting Automated Network Discovery...")
        
        devices = db.query(models.NetworkDevice).all()
        managed_hostnames = {d.hostname for d in devices}
        
        processed_pairs = set()
        new_edges_list = []
        rogue_devices_found = []

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
                        
                        # --- GRAB STP BLOCKED PORTS ---
                        stp_output = net_connect.send_command("show spanning-tree")
                        blocked_ports = []
                        for stp_line in stp_output.splitlines():
                            if "BLK" in stp_line or "ALT" in stp_line:
                                parts = stp_line.split()
                                if parts:
                                    port_name = parts[0].replace("GigabitEthernet", "Gig").replace("FastEthernet", "Fas").replace("TenGigabitEthernet", "Ten")
                                    blocked_ports.append(port_name)
                        
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
                            link_key = tuple(sorted([device.hostname, clean_target]))
                            if link_key in processed_pairs:
                                continue
                            processed_pairs.add(link_key)

                            link_type = "trunk" if "gig" in source_port.lower() or "ten" in source_port.lower() else "access"
                            
                            if source_port in blocked_ports:
                                link_type += "_blocked"
                                
                            new_edges_list.append(models.TopologyEdge(
                                source_hostname=device.hostname,
                                source_port=source_port,
                                target_hostname=clean_target,
                                target_port=target_port,
                                link_type=link_type,
                                current_utilization=0.0
                            ))
                            
                            if clean_target not in managed_hostnames:
                                rogue_devices_found.append(clean_target)

                except Exception as e:
                    print(f"[DISCOVERY ENGINE] Failed to map {device.hostname}: {e}")

        # --- THE TRANSACTIONAL MERGE ---
        existing_edges = db.query(models.TopologyEdge).all()
        
        def make_key(e): 
            return f"{e.source_hostname}-{e.source_port}-{e.target_hostname}-{e.target_port}"
            
        existing_map = {make_key(e): e for e in existing_edges}
        new_map = {make_key(e): e for e in new_edges_list}
        
        for key, edge in existing_map.items():
            if key not in new_map:
                db.delete(edge)
                
        for key, edge in new_map.items():
            if key not in existing_map:
                db.add(edge)

        db.commit()
        log_event(db=db, event_type="Inventory", severity="SUCCESS", author=username, target_devices=[], details={"action": "Automated Topology Discovery Completed", "edges_mapped": len(new_edges_list)})
        print(f"[DISCOVERY ENGINE] Map Built! {len(new_edges_list)} connections mapped safely.")

    except Exception as e:
        db.rollback()
        print(f"[DISCOVERY ENGINE] Fatal Error: {str(e)}")
    finally:
        db.close()

@router.post("/topology/discover")
def trigger_discovery(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    """API Endpoint to trigger the discovery worker."""
    background_tasks.add_task(background_discovery, current_user.username)
    return {"message": "Automated Network Discovery initiated. The map will update shortly."}

# ==========================================
# --- LIVE TELEMETRY ENGINE ---
# ==========================================
@router.get("/topology/telemetry/{device_id}")
def get_device_telemetry(device_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """JIT (Just-in-Time) polling endpoint for live map tooltips."""
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    if device.os_type != "cisco":
        return {"cpu": "N/A (Cisco Only)", "memory": "N/A", "uptime": "N/A"}
        
    try:
        connection_params = {
            'device_type': 'cisco_ios', 'host': device.ip_address,
            'username': device.username, 'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
            'fast_cli': True, 'auth_timeout': 5, 'banner_timeout': 5
        }
        
        with ConnectHandler(**connection_params) as net_connect:
            cpu_out = net_connect.send_command("show processes cpu | include CPU utilization")
            cpu = "Nominal"
            if "five minutes:" in cpu_out:
                cpu = cpu_out.split("five minutes:")[-1].strip()

            mem_out = net_connect.send_command("show memory statistics | include Processor")
            if not mem_out.strip():
                mem_out = net_connect.send_command("show memory | include Processor")
            
            mem = "Unknown"
            if "Processor" in mem_out:
                parts = mem_out.strip().split()
                if len(parts) >= 4:
                    try:
                        total = float(parts[2].replace(',', ''))
                        used = float(parts[3].replace(',', ''))
                        mem = f"{int((used/total)*100)}% Used"
                    except Exception:
                        mem = "Data unreadable"

            ver_out = net_connect.send_command("show version | include uptime")
            uptime = "Active"
            if "uptime is" in ver_out:
                uptime = ver_out.split("uptime is")[-1].strip()

            return {"cpu": cpu, "memory": mem, "uptime": uptime}

    except Exception as e:
        print(f"Telemetry failed for {device.hostname}: {e}")
        return {"cpu": "Timeout", "memory": "Timeout", "uptime": "Timeout"}

# ==========================================
# --- EPC PACKET CAPTURE ENGINE ---
# ==========================================
@router.get("/topology/pcap")
def generate_and_download_pcap(device_id: int, port: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    """Triggers Embedded Packet Capture (EPC), downloads via SCP, and serves to frontend."""
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Target device not found.")

    try:
        connection_params = {
            'device_type': 'cisco_ios', 'host': device.ip_address,
            'username': device.username, 'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
            'fast_cli': True
        }
        
        capture_name = "VNMS_CAP"
        pcap_filename = f"vnms_{uuid.uuid4().hex[:8]}.pcap"
        local_filepath = os.path.join(tempfile.gettempdir(), pcap_filename)

        with ConnectHandler(**connection_params) as net_connect:
            net_connect.enable()
            net_connect.send_config_set([f"no monitor capture {capture_name}"])
            
            setup_cmds = [
                f"monitor capture {capture_name} interface {port} both",
                f"monitor capture {capture_name} match any",
                f"monitor capture {capture_name} file location flash:{pcap_filename}",
            ]
            net_connect.send_config_set(setup_cmds)
            net_connect.send_command_timing(f"monitor capture {capture_name} start")
            
            print(f"[EPC] Capturing traffic on {device.hostname} port {port} for 10 seconds...")
            time.sleep(10)
            
            net_connect.send_command_timing(f"monitor capture {capture_name} stop")
            
            print(f"[EPC] Downloading {pcap_filename} from {device.hostname} via SCP...")
            scp_transfer = file_transfer(
                net_connect, source_file=pcap_filename, dest_file=local_filepath,
                file_system="flash:", direction="get"
            )
            
            net_connect.send_config_set([f"no monitor capture {capture_name}"])
            net_connect.send_command_timing(f"delete flash:{pcap_filename}\n\n")

        log_event(db=db, event_type="Maintenance", severity="INFO", author=current_user.username, target_devices=[device.hostname], details={"action": "Packet Trace Executed", "port": port, "file": pcap_filename})
        return FileResponse(path=local_filepath, media_type="application/vnd.tcpdump.pcap", filename=f"{device.hostname}_{port.replace('/', '-')}_trace.pcap")

    except Exception as e:
        log_event(db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, target_devices=[device.hostname], details={"action": "Packet Trace Failed", "port": port, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"EPC Capture failed: {str(e)}")

# ==========================================
# --- REBOOT ENGINE ---
# ==========================================
def background_reboot(device_id: int, username: str):
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

# ==========================================
# --- PORT OPERATIONS ENGINE ---
# ==========================================
class PortOperationRequest(BaseModel):
    hostname: str
    port: str
    action: str  

@router.post("/topology/port-action")
def execute_port_action(request: PortOperationRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    """Executes granular interface state changes."""
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname == request.hostname).first()
    
    if not device:
        raise HTTPException(status_code=404, detail=f"Target device {request.hostname} not found.")

    try:
        connection_params = {
            'device_type': 'cisco_ios', 'host': device.ip_address,
            'username': device.username, 'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
            'fast_cli': True
        }
        
        with ConnectHandler(**connection_params) as net_connect:
            net_connect.enable()
            
            commands = [f"interface {request.port}"]
            if request.action == 'bounce':
                commands.extend(["shutdown", "no shutdown"])
            elif request.action == 'shutdown':
                commands.append("shutdown")
            elif request.action == 'no_shutdown':
                commands.append("no shutdown")
                
            output = net_connect.send_config_set(commands)
            
        log_event(db=db, event_type="Maintenance", severity="WARNING", author=current_user.username, target_devices=[device.hostname], details={"action": f"Port {request.action.upper()}", "port": request.port, "output": output})
        return {"message": f"Successfully executed {request.action} on {request.port}."}

    except Exception as e:
        log_event(db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, target_devices=[device.hostname], details={"action": "Port Action Failed", "port": request.port, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"Port action failed: {str(e)}")