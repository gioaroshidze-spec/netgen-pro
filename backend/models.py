from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Float
from database import Base
from datetime import datetime, timezone

class NetworkDevice(Base):
    __tablename__ = "network_devices"

    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String, unique=True, index=True)
    ip_address = Column(String, unique=True, index=True)
    device_type = Column(String)          # e.g., 'switch', 'router'
    os_type = Column(String, default="cisco") # 'cisco', 'aruba', 'hpe', 'mikrotik'
    username = Column(String)
    
    # --- VISUALIZATION PILLARS ---
    pos_x = Column(Float, default=100.0)       # 2D Canvas X Coordinate
    pos_y = Column(Float, default=100.0)       # 2D Canvas Y Coordinate
    floor = Column(String, default="Floor 1")  # Multi-level environment zone layering


class TopologyEdge(Base):
    __tablename__ = "topology_edges"

    id = Column(Integer, primary_key=True, index=True)
    
    # Connection Source (Local Node and Port)
    source_hostname = Column(String, index=True)
    source_port = Column(String)
    
    # Connection Target (Remote Node and Port)
    target_hostname = Column(String, index=True)
    target_port = Column(String)
    
    # Metadata for Heatmapping / Interconnection Status
    link_type = Column(String, default="ethernet")    # trunk, access, etherchannel
    current_utilization = Column(Float, default=0.0)  # Live bandwidth allocation metric


class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    event_type = Column(String, index=True)      # 'Configuration', 'Maintenance', 'Inventory', 'Auth'
    severity = Column(String, index=True)        # 'INFO', 'SUCCESS', 'WARNING', 'ERROR'
    author = Column(String, default="System", index=True)
    target_devices = Column(JSON, default=list)  # Array of hostnames: ["cctv_sw1"]
    details = Column(JSON, default=dict)         # Deep forensic execution payloads


class ConfiguraitonTemplate(Base):
    __tablename__ = "configuration_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    category = Column(String, index=True)        # 'Switching', 'Routing', 'Security'
    description = Column(String)
    payload = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="admin")       # 'admin', 'viewer'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    job_type = Column(String)        # 'backup', 'template_push'
    target_devices = Column(JSON)    # Array of target hostnames
    job_payload = Column(JSON)       # Checkbox parameters or target raw template configurations
    
    # Recurrence Windows
    cron_day_of_week = Column(String, nullable=True)
    cron_hour = Column(String, nullable=True)
    cron_minute = Column(String, nullable=True)
    interval_hours = Column(Integer, nullable=True)
    run_once_time = Column(DateTime, nullable=True)
    
    # State and Auditing
    is_active = Column(Boolean, default=True)
    created_by = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_run_status = Column(String, default="Pending")
    last_run_time = Column(DateTime, nullable=True)