from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

# ==========================================
# --- NEW: ORGANIZATION SCHEMAS ---
# ==========================================
class ZoneBase(BaseModel):
    name: str

class ZoneResponse(ZoneBase):
    id: int
    class Config:
        from_attributes = True

class FloorBase(BaseModel):
    name: str

class FloorResponse(FloorBase):
    id: int
    zones: List[ZoneResponse] = []
    class Config:
        from_attributes = True

class BuildingBase(BaseModel):
    name: str

class BuildingResponse(BuildingBase):
    id: int
    floors: List[FloorResponse] = []
    class Config:
        from_attributes = True

class BuildingCreate(BuildingBase):
    pass

class FloorCreate(FloorBase):
    building_id: int

class ZoneCreate(ZoneBase):
    floor_id: int


# --- DEVICE CRUD SCHEMAS ---
# This is the shape of the data we EXPECT the user to send us
class DeviceCreate(BaseModel):
    hostname: str
    ip_address: str
    device_type: str
    os_type: str
    username: str
    password: Optional[str] = None
    is_legacy: Optional[bool] = False
    pos_x: Optional[float] = 100.0       
    pos_y: Optional[float] = 100.0       
    zone_id: Optional[int] = None # <-- REPLACED 'floor' with relational zone_id

# This is the shape of the data we RETURN to the user
# It inherits everything from DeviceCreate, but adds the DB-generated ID
class DeviceResponse(DeviceCreate):
    id: int
    status: Optional[str] = "unknown" 
    latency: Optional[str] = "<1ms"  # Added to support map health badges
    last_seen: Optional[datetime] = None

    class Config:
        from_attributes = True

class DeviceUpdate(BaseModel):
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    device_type: Optional[str] = None
    os_type: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_legacy: Optional[bool] = False
    pos_x: Optional[float] = None        
    pos_y: Optional[float] = None        
    zone_id: Optional[int] = None # <-- REPLACED 'floor' with relational zone_id


# --- NEW: USER MANAGEMENT SCHEMAS ---
class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    requires_password_change: bool
    class Config:
        from_attributes = True

class AdminPasswordReset(BaseModel):
    new_password: str


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
    base_template: Optional[dict] = None

class SimulateConfigRequest(BaseModel):
    prompt: Optional[str] = "Manual Edit / No Prompt"
    config_text: str
    switches: list[str]
    routers: list[str]
    source_template: Optional[str] = None  # <-- ALLOWS THE TEMPLATE NAME THROUGH

class PushConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_id: str

class SimulationOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    override_reason: str


# --- EVENT LOG SCHEMAS ---
class EventLogCreate(BaseModel):
    event_type: str
    severity: str
    author: Optional[str] = "System"
    target_devices: list[Any] = []
    details: dict = {}

class EventLogResponse(EventLogCreate):
    id: int
    timestamp: datetime

    class Config: # Fixed 'config' capitalization to 'Config' for Pydantic standard
        from_attributes = True


# --- CONFIGURATION TEMPLATE SCHEMAS ---
class TemplateCreate(BaseModel):
    name: str
    category: str
    payload: dict
    prompt: Optional[str] = None  # <-- ALLOWS THE PROMPT THROUGH

class TemplateResponse(TemplateCreate):
    id: int
    description: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- SCHEDULED JOBS SCHEMAS ---
class ScheduledJobBase(BaseModel):
    name: str
    job_type: str  # 'backup' or 'template_push'
    target_devices: List[str]
    job_payload: Dict[str, Any]
    cron_day_of_week: Optional[str] = None
    cron_hour: Optional[str] = None
    cron_minute: Optional[str] = None
    interval_hours: Optional[int] = None
    run_once_time: Optional[datetime] = None

class ScheduledJobCreate(ScheduledJobBase):
    pass

class ScheduledJobResponse(ScheduledJobBase):
    id: int
    is_active: bool
    created_by: str
    created_at: datetime
    last_run_status: str
    last_run_time: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- NEW: TOPOLOGY LINK SCHEMAS ---
class EdgeBase(BaseModel):
    source_hostname: str
    source_port: str
    target_hostname: str
    target_port: str
    link_type: Optional[str] = "ethernet"
    current_utilization: Optional[float] = 0.0

class EdgeResponse(EdgeBase):
    id: int

    class Config:
        from_attributes = True

# Used when React drops a bunch of dragged coordinates back to the API
class CoordinateUpdate(BaseModel):
    id: int
    pos_x: float
    pos_y: float

# Add these classes to the bottom of your existing schemas.py
class SavedViewBase(BaseModel):
    name: str
    zone_ids: List[int]
    coordinates: Dict[str, Dict[str, float]]

class SavedViewCreate(SavedViewBase):
    pass

class SavedViewResponse(SavedViewBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
