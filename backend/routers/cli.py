import asyncio
import paramiko
import os
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from database import SessionLocal
import models

# Re-import variables to decode the token manually
from routers.auth import SECRET_KEY, ALGORITHM

router = APIRouter(tags=["CLI"])

@router.websocket("/ws/cli/{device_id}")
async def cli_websocket(websocket: WebSocket, device_id: int, token: str = Query(None)):
    
    # --- NEW: MANUAL WEBSOCKET AUTHENTICATION ---
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
    db.close()

    if not device:
        await websocket.send_text("\r\n[ERROR] Device not found in database.\r\n")
        await websocket.close()
        return
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        await websocket.send_text(f"\r\n[INFO] Initializing SSH connection to {device.hostname} ({device.ip_address})...\r\n")

        password = os.getenv("DEVICE_PASSWORD", "Werfds123")
        user = device.username or "admin"

        await asyncio.to_thread(
            ssh.connect, hostname=device.ip_address, username=user,
            password=password, look_for_keys=False, allow_agent=False, timeout=10,
            disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512'], 'keys': []} # <-- THE FIX: Re-enables legacy ssh-rsa host keys
        )

        channel = ssh.invoke_shell()
        channel.setblocking(0) 

        await websocket.send_text(f"\r\n[SUCCESS] Connected to {device.hostname}!\r\n")

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
        await websocket.send_text(f"\r\n[ERROR] SSH Connection Failed: {str(e)}\r\n")
    finally:
        ssh.close()
        try: await websocket.close()
        except: pass