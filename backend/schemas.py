from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# --- DEVICE CRUD SCHEMAS ---
# This is the shape of the data we EXPECT the user to send us
class DeviceCreate(BaseModel):
    hostname: str
    ip_address: str
    device_type: str
    os_type: str
    username: str

# This is the shape of the data we RETURN to the user
# It ingerits everything from DeviceCreate, but adds the DB-generated ID
class DeviceResponse(DeviceCreate):
    id: int

    class Config:
        from_attributes = True
class DeviceUpdate(BaseModel):
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    device_type: Optional[str] = None
    os_type: Optional[str] = None
    username: Optional[str] = None

# --- CONFIG GENERATOR SCHEMAS ---

class VlanConfig(BaseModel):
    id: int
    name: str

class SwitchConfigRequest(BaseModel):
    hostname: str
    management_ip: str
    default_gateway: str
    vlans: list[VlanConfig]

# --- BACKUP REQUESTS ---
class BackupOptions(BaseModel):
    save_nvram: bool
    save_flash: bool
    download_local: bool
    save_archive: bool
    prefix: Optional[str] = ""

class BulkBackupRequest(BaseModel):
    device_ids: list[int]
    options: BackupOptions

# --- CONFIGURATION ENGINE REQUESTS ---
class AIConfigGenerate(BaseModel):
    prompt: str
    switches: list[str]
    routers: list[str]

class SimulateConfigRequest(BaseModel):
    prompt: Optional[str] = "Manual Edit / No Prompt"
    config_text: str
    switches: list[str]
    routers: list[str]

# --- EVENT LOG SCHEMAS ---

class EventLogCreate(BaseModel):
    event_type: str
    severity: str
    author: Optional[str] = "System"
    target_devices: list[str] = []
    details: dict = {}

class EventLogResponse(EventLogCreate):
    id: int
    timestamp: datetime

    class config:
        from_attributes = True