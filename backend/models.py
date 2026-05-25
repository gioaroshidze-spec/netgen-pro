from sqlalchemy import Column, Integer, String, DateTime, JSON
from database import Base
from datetime import datetime, timezone

class NetworkDevice(Base):
    # This is the actual name of the table inside the SQLite database
    __tablename__ = "network_devices"

    # Columns for our table
    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String, unique=True, index=True)
    ip_address = Column(String, unique=True, index=True)
    device_type = Column(String) # e.g., 'switch', 'router'
    os_type = Column(String, default="cisco")
    username = Column(String)

    # Note: We will handle passwords and ssh keys securely later!

class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    event_type = Column(String, index=True)     # e.g., 'Configuration', 'Maintenance', 'Inventory', 'Auth'
    severity = Column(String, index=True)       # e.g., 'INFO', 'SUCCESS', 'WARNING', 'ERROR'
    author = Column(String, default="System", index=True)
    target_devices = Column(JSON, default=list)  # JSON Array of hostnames: ["cctv_sw1", "cctv_sw2"]
    details = Column(JSON, default=dict)  # Flexible JSON payload for prompts, diffs, or simple messages

# --- CONFIGURATION TEMPLATES MODEL ---

class ConfiguraitonTemplate(Base):
    __tablename__ = "configuration_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    category = Column(String, index=True)
    description = Column(String)
    payload = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# --- USER / AUTHENTICATION
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="admin")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))