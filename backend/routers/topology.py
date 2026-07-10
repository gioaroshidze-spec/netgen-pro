import os
import re
import time
import uuid
import tempfile
import threading
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
from routers.auth import decrypt_secret

# --- THE SURGICAL INCISION: Import our central connection wrapper ---
from connection_utils import get_netmiko_params

# --- NEW: Global Discovery Lock ---
DISCOVERY_LOCK = threading.Lock()
IS_DISCOVERING = False

class ManualEdgeCreate(BaseModel):
    source_hostname: str
    target_hostname: str
    source_port: str
    target_port: str

router = APIRouter(tags=["Topology & Power"])

@router.get("/topology/edges", response_model=List[schemas.EdgeResponse])
def get_topology_edges(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.TopologyEdge).all()

@router.post("/topology/edges/manual")
def create_manual_edge(edge: ManualEdgeCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    db_edge = models.TopologyEdge(
        source_hostname=edge.source_hostname,
        source_port=edge.source_port,
        target_hostname=edge.target_hostname,
        target_port=edge.target_port,
        link_type="manual",
        current_utilization=0.0
    )
    db.add(db_edge)
    db.commit()
    return {"message": "Manual link added."}

@router.delete("/topology/edges/{edge_id}")
def delete_edge(edge_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    edge = db.query(models.TopologyEdge).filter(models.TopologyEdge.id == edge_id).first()
    if not edge: raise HTTPException(status_code=404)
    db.delete(edge)
    db.commit()
    return {"message": "Edge deleted."}

@router.post("/topology/update-coordinates")
def update_coordinates(nodes: List[schemas.CoordinateUpdate], db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    for node in nodes:
        device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == node.id).first()
        if device:
            device.pos_x = node.pos_x
            device.pos_y = node.pos_y
    db.commit()
    return {"status": "success", "message": "Layout coordinates saved."}

# ==========================================
# --- ENTERPRISE MULTI-VENDOR DISCOVERY ---
# ==========================================
def background_discovery(username: str):
    global IS_DISCOVERING
    db = SessionLocal()
    
    try:
        # Check and set the lock
        with DISCOVERY_LOCK:
            if IS_DISCOVERING:
                print("[DISCOVERY ENGINE] Aborting: Discovery already in progress.")
                return
            IS_DISCOVERING = True
            
        print("[DISCOVERY ENGINE] Starting Automated Enterprise Network Discovery...")
        devices = db.query(models.NetworkDevice).all()
        managed_hostnames = {d.hostname for d in devices}
        
        # Aggressive Normalization (strips hyphens, underscores, spaces)
        def normalize_host(name: str):
            if not name: return ""
            return re.sub(r'[^a-z0-9]', '', name.lower())
            
        managed_hostnames_map = {normalize_host(d.hostname): d.hostname for d in devices}
        
        processed_pairs = set()
        new_edges_list = []

        for device in devices:
            # Fetch standardized, safe connection parameters
            connection_params = get_netmiko_params(device)

            try:
                with ConnectHandler(**connection_params) as net_connect:
                    # MIKROTIK DISCOVERY LOGIC
                    if device.os_type == 'mikrotik':
                        output = net_connect.send_command("/ip neighbor print detail")
                        blocks = output.split("-------------------")
                        if len(blocks) < 2: blocks = output.split("\r\n\r\n")
                        
                        for block in blocks:
                            if not block.strip(): continue
                            intf_match = re.search(r'interface=([^\s]+)', block)
                            id_match = re.search(r'identity="?([^"\r\n]+)"?', block)
                            sys_match = re.search(r'sys-name="?([^"\r\n]+)"?', block)
                            
                            remote_host = sys_match.group(1) if sys_match else (id_match.group(1) if id_match else None)
                            local_intf = intf_match.group(1) if intf_match else None
                            
                            if remote_host and local_intf:
                                remote_host = remote_host.split('.')[0]
                                # Snap casing to database using normalized name
                                remote_host = managed_hostnames_map.get(normalize_host(remote_host), remote_host)
                                
                                link_key = tuple(sorted([device.hostname, remote_host]))
                                if link_key in processed_pairs: continue
                                processed_pairs.add(link_key)
                                
                                new_edges_list.append(models.TopologyEdge(
                                    source_hostname=device.hostname, source_port=local_intf,
                                    target_hostname=remote_host, target_port="Unknown",
                                    link_type="ethernet", current_utilization=0.0
                                ))
                    
                    # ENTERPRISE OS DISCOVERY (Cisco, HPE, Aruba) -> LLDP & CDP
                    else:
                        try: net_connect.enable()
                        except: pass
                        output = net_connect.send_command("show lldp neighbors")
                        if "Invalid input" in output or "LLDP is not enabled" in output:
                            output = net_connect.send_command("show cdp neighbors")
                        
                        lines = [line.strip() for line in output.splitlines() if line.strip()]
                        current_target = None
                        
                        skip_keywords = [
                            "Capability", "Device ID", "Total", "entries", "Local Intf", "Port ID",
                            "S - Switch", "R - Router", "P - Phone", "H - Host", "I - IGMP", "D - Remote"
                        ]
                        
                        for line in lines:
                            if line.startswith("%") or any(k in line for k in skip_keywords):
                                continue

                            parts = re.split(r'\s+', line)
                            
                            if len(parts) == 1:
                                current_target = parts[0]
                                continue
                            
                            if len(parts) >= 4:
                                if current_target:
                                    raw_target = current_target
                                    idx_local = 0
                                else:
                                    raw_target = parts[0]
                                    idx_local = 1
                                
                                source_port = parts[idx_local]
                                if source_port.lower() in ["gig", "fas", "ten", "eth"] and len(parts) > idx_local + 1:
                                    source_port = f"{parts[idx_local]}{parts[idx_local+1]}"
                                    
                                target_port = parts[-1]
                                if len(parts) >= 2 and parts[-2].lower() in ["gig", "fas", "ten", "eth"]:
                                    target_port = f"{parts[-2]}{parts[-1]}"
                                    
                                current_target = None

                                clean_target = raw_target.split('.')[0]
                                # Snap casing to database using normalized name
                                clean_target = managed_hostnames_map.get(normalize_host(clean_target), clean_target)
                                
                                link_key = tuple(sorted([device.hostname, clean_target]))
                                if link_key in processed_pairs: continue
                                processed_pairs.add(link_key)

                                link_type = "trunk" if "gig" in source_port.lower() or "ten" in source_port.lower() else "access"
                                
                                new_edges_list.append(models.TopologyEdge(
                                    source_hostname=device.hostname, source_port=source_port,
                                    target_hostname=clean_target, target_port=target_port,
                                    link_type=link_type, current_utilization=0.0
                                ))

            except Exception as e:
                print(f"[DISCOVERY ENGINE] Failed to map {device.hostname} ({device.os_type}): {e}")

        # TRANSACTIONAL MERGE
        existing_edges = db.query(models.TopologyEdge).all()
        def make_key(e): return f"{e.source_hostname}-{e.target_hostname}"
            
        existing_map = {make_key(e): e for e in existing_edges}
        new_map = {make_key(e): e for e in new_edges_list}
        
        for key, edge in existing_map.items():
            if edge.link_type != "manual" and key not in new_map: 
                db.delete(edge)
                
        for key, edge in new_map.items():
            if key not in existing_map: db.add(edge)

        db.commit()
        log_event(db=db, event_type="Inventory", severity="SUCCESS", author=username, target_devices=[], details={"action": "Automated Topology Discovery Completed", "edges_mapped": len(new_edges_list)})

    except Exception as e:
        db.rollback()
        print(f"[DISCOVERY ENGINE] Fatal Error: {str(e)}")
    finally:
        # Release the lock when finished or if it crashes
        with DISCOVERY_LOCK:
            IS_DISCOVERING = False
        db.close()

@router.post("/topology/discover")
def trigger_discovery(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    global IS_DISCOVERING
    if IS_DISCOVERING:
        raise HTTPException(status_code=429, detail="A network discovery scan is already running. Please wait.")
        
    background_tasks.add_task(background_discovery, current_user.username)
    return {"message": "Automated Network Discovery initiated. The map will update shortly."}

# ==========================================
# --- ENTERPRISE TELEMETRY ENGINE ---
# ==========================================
@router.get("/topology/telemetry/{device_id}")
def get_device_telemetry(device_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not device: raise HTTPException(status_code=404, detail="Device not found")

    try:
        connection_params = get_netmiko_params(device)
        connection_params['auth_timeout'] = 5
        connection_params['banner_timeout'] = 5
        
        with ConnectHandler(**connection_params) as net_connect:
            if device.os_type == 'mikrotik':
                res = net_connect.send_command("/system resource print")
                cpu = re.search(r'cpu-load:\s+(\d+%)', res)
                mem = re.search(r'free-memory:\s+(.*)', res)
                uptime = re.search(r'uptime:\s+(.*)', res)
                return {
                    "cpu": cpu.group(1) if cpu else "Unknown",
                    "memory": f"{mem.group(1).strip()} Free" if mem else "Unknown",
                    "uptime": uptime.group(1).strip() if uptime else "Active"
                }
            
            elif device.os_type == 'cisco':
                cpu_out = net_connect.send_command("show processes cpu | include CPU utilization")
                cpu_match = re.search(r'five minutes:\s*([0-9]+%)', cpu_out)
                cpu = cpu_match.group(1) if cpu_match else "Unknown"

                mem_out = net_connect.send_command("show processes memory | include Processor")
                mem_match = re.search(r'Total:\s+(\d+)\s+Used:\s+(\d+)', mem_out)
                if mem_match:
                    total_mem = int(mem_match.group(1))
                    used_mem = int(mem_match.group(2))
                    mem_pct = round((used_mem / total_mem) * 100)
                    memory = f"{mem_pct}% Used"
                else:
                    memory = "Unknown"

                up_out = net_connect.send_command("show version | include uptime")
                up_match = re.search(r'uptime is (.*)', up_out)
                uptime = up_match.group(1).strip() if up_match else "Active"

                return {"cpu": cpu, "memory": memory, "uptime": uptime}
            
            else:
                return {"cpu": "SNMP Req", "memory": "SNMP Req", "uptime": "Active"}

    except Exception as e:
        return {"cpu": "Timeout", "memory": "Timeout", "uptime": "Timeout"}
    

# ==========================================
# --- EPC PACKET CAPTURE ENGINE ---
# ==========================================
@router.get("/topology/pcap")
def generate_and_download_pcap(device_id: int, port: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not device: raise HTTPException(status_code=404)
    if device.os_type != 'cisco': raise HTTPException(status_code=400, detail="Packet trace via SSH is only supported on Cisco IOS-XE.")

    try:
        connection_params = get_netmiko_params(device)
        
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
            time.sleep(10)
            net_connect.send_command_timing(f"monitor capture {capture_name} stop")
            
            scp_transfer = file_transfer(net_connect, source_file=pcap_filename, dest_file=local_filepath, file_system="flash:", direction="get")
            
            net_connect.send_config_set([f"no monitor capture {capture_name}"])
            net_connect.send_command_timing(f"delete flash:{pcap_filename}\n\n")

        log_event(db=db, event_type="Maintenance", severity="INFO", author=current_user.username, target_devices=[device.hostname], details={"action": "Packet Trace", "port": port})
        return FileResponse(path=local_filepath, media_type="application/vnd.tcpdump.pcap", filename=f"{device.hostname}_trace.pcap")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# --- REBOOT ENGINE ---
# ==========================================
def background_reboot(device_id: int, username: str):
    db = SessionLocal()
    try:
        device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
        if not device: return

        connection_params = get_netmiko_params(device)

        with ConnectHandler(**connection_params) as net_connect:
            if device.os_type in ['cisco', 'aruba', 'hpe']:
                net_connect.enable()
                net_connect.send_command("write memory")
                net_connect.send_command_timing("reload\n")
                net_connect.send_command_timing("y\n") 
            elif device.os_type == 'mikrotik':
                net_connect.send_command_timing("/system reboot\n")
                net_connect.send_command_timing("y\n")

        log_event(db=db, event_type="Maintenance", severity="WARNING", author=username, target_devices=[device.hostname], details={"action": "Device Reboot"})
    except Exception:
        pass
    finally:
        db.close()

@router.post("/device/{device_id}/reboot")
def trigger_device_reboot(device_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    if not device: raise HTTPException(status_code=404)
    background_tasks.add_task(background_reboot, device.id, current_user.username)
    return {"message": "Reboot queued."}

# ==========================================
# --- ENTERPRISE PORT OPS ENGINE ---
# ==========================================
class PortOperationRequest(BaseModel):
    hostname: str
    port: str
    action: str  

@router.post("/topology/port-action")
def execute_port_action(request: PortOperationRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname == request.hostname).first()
    if not device: raise HTTPException(status_code=404)

    try:
        connection_params = get_netmiko_params(device)
        
        with ConnectHandler(**connection_params) as net_connect:
            if device.os_type == 'mikrotik':
                if request.action == 'shutdown': net_connect.send_command(f"/interface disable [find name=\"{request.port}\"]")
                elif request.action == 'no_shutdown': net_connect.send_command(f"/interface enable [find name=\"{request.port}\"]")
                elif request.action == 'bounce':
                    net_connect.send_command(f"/interface disable [find name=\"{request.port}\"]")
                    time.sleep(2)
                    net_connect.send_command(f"/interface enable [find name=\"{request.port}\"]")
            else:
                net_connect.enable()
                commands = [f"interface {request.port}"]
                if request.action == 'bounce': commands.extend(["shutdown", "no shutdown"])
                elif request.action == 'shutdown': commands.append("shutdown")
                elif request.action == 'no_shutdown': commands.append("no shutdown")
                net_connect.send_config_set(commands)
            
        log_event(db=db, event_type="Maintenance", severity="WARNING", author=current_user.username, target_devices=[device.hostname], details={"action": f"Port {request.action.upper()}", "port": request.port})
        return {"message": f"Successfully executed {request.action} on {request.port}."}

    except Exception as e:
        log_event(db=db, event_type="Maintenance", severity="ERROR", author=current_user.username, target_devices=[device.hostname], details={"action": "Port Action Failed", "error": str(e)})
        raise HTTPException(status_code=500, detail=f"Port action failed: {str(e)}")

# ==========================================
# --- SAVED VIEWS API ---
# ==========================================
@router.get("/topology/views", response_model=List[schemas.SavedViewResponse])
def get_saved_views(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.SavedTopologyView).filter(models.SavedTopologyView.user_id == current_user.id).all()

@router.post("/topology/views", response_model=schemas.SavedViewResponse)
def save_topology_view(view: schemas.SavedViewCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_view = models.SavedTopologyView(name=view.name, user_id=current_user.id, zone_ids=view.zone_ids, coordinates=view.coordinates)
    db.add(db_view)
    db.commit()
    db.refresh(db_view)
    return db_view

@router.delete("/topology/views/{view_id}")
def delete_topology_view(view_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_view = db.query(models.SavedTopologyView).filter(models.SavedTopologyView.id == view_id, models.SavedTopologyView.user_id == current_user.id).first()
    if not db_view: raise HTTPException(status_code=404)
    db.delete(db_view)
    db.commit()
    return {"message": "View deleted successfully."}