import asyncio
import paramiko
import os
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from database import SessionLocal
import models

# Re-import variables to decode the token manually
from routers.auth import SECRET_KEY, ALGORITHM
from routers.auth import decrypt_secret
from logger import log_event

router = APIRouter(tags=["CLI"])

def log_cli_access(username: str, target_meta: dict, status: str, error_msg: str = None):
    """
    Briefly opens a DB session to log the CLI access event. 
    This prevents holding a DB connection open for the duration of a 2-hour SSH session.
    """
    db = SessionLocal()
    try:
        details = {
            "action": "Interactive CLI Session",
            "mode": "Live SSH Terminal",
            "execution_status": status
        }
        if error_msg:
            details["error"] = error_msg

        log_event(
            db=db,
            event_type="Configuration",
            severity="INFO" if status == "Connected" else "ERROR",
            author=username,
            target_devices=[target_meta],
            details=details
        )
    finally:
        db.close()


@router.websocket("/ws/cli/{device_id}")
async def cli_websocket(websocket: WebSocket, device_id: int, token: str = Query(None)):
    
    # --- MANUAL WEBSOCKET AUTHENTICATION ---
    if not token:
        await websocket.close(code=1008, reason="Missing Token")
        return
        
    try:
        # Verify the token is valid and not expired
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username: raise ValueError("Invalid Token")
    except Exception as e:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    # --------------------------------------------

    await websocket.accept()

    db = SessionLocal()
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    
    # Extract metadata before closing the DB session
    if device:
        target_meta = {
            "hostname": device.hostname,
            "ip_address": device.ip_address,
            "device_type": device.device_type,
            "os_type": device.os_type
        }
        password = decrypt_secret(device.encrypted_password)
        user = device.username or "admin"
    
    db.close()

    if not device:
        await websocket.send_text("\r\n[ERROR] Device not found in database.\r\n")
        await websocket.close()
        return
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        await websocket.send_text(f"\r\n[INFO] Initializing SSH connection to {device.hostname} ({device.ip_address})...\r\n")

        await asyncio.to_thread(
            ssh.connect, hostname=device.ip_address, username=user,
            password=password, look_for_keys=False, allow_agent=False, timeout=10,
            disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512'], 'keys': []} # Re-enables legacy ssh-rsa host keys
        )

        channel = ssh.invoke_shell()
        channel.setblocking(0) 

        await websocket.send_text(f"\r\n[SUCCESS] Connected to {device.hostname}!\r\n")
        
        # --- AUDIT LOG: SUCCESSFUL ACCESS ---
        log_cli_access(username, target_meta, "Connected")

        async def read_from_ws():
            try:
                while True:
                    data = await websocket.receive_text()
                    if channel and channel.send_ready():
                        channel.send(data)
            except WebSocketDisconnect: pass
            except Exception as e: print(f"WebSocket Read Error: {e}")

        async def read_from_ssh():
            try:
                while True:
                    if channel and channel.recv_ready():
                        data = channel.recv(4096).decode('utf-8', errors='ignore')
                        await websocket.send_text(data)
                    await asyncio.sleep(0.01)
            except Exception as e: print(f"SSH Read Error: {e}")

        ws_task = asyncio.create_task(read_from_ws())
        ssh_task = asyncio.create_task(read_from_ssh())

        done, pending = await asyncio.wait([ws_task, ssh_task], return_when=asyncio.FIRST_COMPLETED)

        for task in pending: task.cancel()

    except Exception as e:
        # --- AUDIT LOG: FAILED ACCESS ---
        log_cli_access(username, target_meta, "Failed", str(e))
        await websocket.send_text(f"\r\n[ERROR] SSH Connection Failed: {str(e)}\r\n")
        
    finally:
        ssh.close()
        try: await websocket.close()
        except: pass