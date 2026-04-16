from pydantic import BaseModel
from typing import Optional

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

class BulkBackupRequest(BaseModel):
    device_ids: list[int]
    options: BackupOptions