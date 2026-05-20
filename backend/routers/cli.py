import asyncio
import paramiko
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from database import SessionLocal
import models

router = APIRouter(tags=["CLI"])

@router.websocket("/ws/cli/{device_id}")
async def cli_websocket(websocket: WebSocket, device_id: int):
    # 1. Accept the WebSocket connection from React
    await websocket.accept()

    # 2. Safely grab the device from the database
    db = SessionLocal()
    device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()
    db.close

    if not device:
        await websocket.send_text("\r\n[ERROR] Device not found in database.\r\n")
        await websocket.close()
        return
    
    # 3. Initialize the SSH Client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        await websocket.send_text(f"\r\n[INFO] Initializing SSH connection to {device.hostname} ({device.ip_address})...\r\n")

        # 4. Connect to the switch (in a separate thread to prevent server lockup)
        password = os.getenv("", "Werfds123")
        username = device.username or "admin"

        await asyncio.to_thread(
            ssh.connect,
            hostname=device.ip_address,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10
        )

        # 5. Open a raw, interactive terminal shell (PTY)
        channel = ssh.invoke_shell()
        channel.setblocking(0) # Make it non-blocking

        await websocket.send_text(f"\r\n[SUCCESS] Connected to {device.hostname}!\r\n")

        # --- TASK A: READ FROM WEBSOCKET, WRITE TO SSH ---
        async def read_from_ws():
            try:
                while True:
                    data = await websocket.receive_text()
                    if channel and channel.send_ready():
                        channel.send(data)
            except WebSocketDisconnect:
                pass # Browser closed the tab/connection
            except Exception as e:
                print(f"WebSocket Read Error: {e}")

        # --- TASK B: READ FROM SSH, WRITE TO WEBSOCKET ---
        async def read_from_ssh():
            try:
                while True:
                    if channel and channel.recv_ready():
                        data = channel.recv(4096).decode('utf-8', errors='ignore')
                        await websocket.send_text(data)

                    # Yield control back to FastAPI so the server doesn't freeze
                    await asyncio.sleep(0.01)
            except Exception as e:
                print(f"SSH Read Error: {e}")

        # 6. Run both tasks side-by-side
        ws_task = asyncio.create_task(read_from_ws())
        ssh_task = asyncio.create_task(read_from_ssh())

        # 7. Wait until the user closes the terminal (or the switch drops connection)
        done, pending = await asyncio.wait(
            [ws_task, ssh_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Kill teh ramaining task
        for task in pending:
            task.cancel()

    except Exception as e:
        await websocket.send_text(f"\r\n[ERROR] SSH Connection Failed: {str(e)}\r\n")
    finally:
        ssh.close()
        try:
            await websocket.close()
        except:
            pass