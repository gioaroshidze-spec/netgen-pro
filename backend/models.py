from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone

# ==========================================
# --- NEW: ORGANIZATION HIERARCHY MODELS ---
# ==========================================
class Building(Base):
    __tablename__ = "buildings"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    # Relationships
    floors = relationship("Floor", back_populates="building", cascade="all, delete-orphan")

class Floor(Base):
    __tablename__ = "floors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"))
    
    # Relationships
    building = relationship("Building", back_populates="floors")
    zones = relationship("Zone", back_populates="floor", cascade="all, delete-orphan")

class Zone(Base):
    __tablename__ = "zones"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    floor_id = Column(Integer, ForeignKey("floors.id", ondelete="CASCADE"))
    
    # Relationships
    floor = relationship("Floor", back_populates="zones")
    devices = relationship("NetworkDevice", back_populates="zone")

# ==========================================
# --- EXISTING MODELS ---
# ==========================================
class NetworkDevice(Base):
    __tablename__ = "network_devices"

    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String, unique=True, index=True)
    ip_address = Column(String, unique=True, index=True)
    device_type = Column(String)          
    os_type = Column(String, default="cisco") 
    username = Column(String)
    encrypted_password = Column(String, nullable=True)
    is_legacy = Column(Boolean, default=False)

    # --- VISUALIZATION PILLARS ---
    pos_x = Column(Float, default=100.0)       
    pos_y = Column(Float, default=100.0)       
    
    # --- RELATIONAL ZONE ID ---
    zone_id = Column(Integer, ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    zone = relationship("Zone", back_populates="devices")

    # --- NEW: TELEMETRY CACHING ---
    last_cpu = Column(String, default="N/A")
    last_ram = Column(String, default="N/A")
    last_uptime = Column(String, default="N/A")
    telemetry_updated_at = Column(DateTime, nullable=True)

class TopologyEdge(Base):
    __tablename__ = "topology_edges"
    id = Column(Integer, primary_key=True, index=True)
    source_hostname = Column(String, index=True)
    source_port = Column(String)
    target_hostname = Column(String, index=True)
    target_port = Column(String)
    link_type = Column(String, default="ethernet")    
    current_utilization = Column(Float, default=0.0)  

class EventLog(Base):
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    event_type = Column(String, index=True)      
    severity = Column(String, index=True)        
    author = Column(String, default="System", index=True)
    target_devices = Column(JSON, default=list)  
    details = Column(JSON, default=dict)         

class ConfiguraitonTemplate(Base):
    __tablename__ = "configuration_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    category = Column(String, index=True)        
    description = Column(String)
    payload = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="admin")

    requires_password_change = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    job_type = Column(String)        
    target_devices = Column(JSON)    
    job_payload = Column(JSON)       
    cron_day_of_week = Column(String, nullable=True)
    cron_hour = Column(String, nullable=True)
    cron_minute = Column(String, nullable=True)
    interval_hours = Column(Integer, nullable=True)
    run_once_time = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_run_status = Column(String, default="Pending")
    last_run_time = Column(DateTime, nullable=True)

class SavedTopologyView(Base):
    __tablename__ = "saved_topology_views"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    zone_ids = Column(JSON)      
    coordinates = Column(JSON)   
    
    user = relationship("User")