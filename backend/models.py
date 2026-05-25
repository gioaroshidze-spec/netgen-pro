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

from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON
from database import Base
from datetime import datetime, timezone

# ... (Keep your existing User and NetworkDevice models here) ...

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    job_type = Column(String)  # e.g., 'backup', 'template_push'
    
    # We store arrays and dictionaries as JSON so the schema is completely flexible
    target_devices = Column(JSON)  # List of hostnames (e.g., ["cctv_sw1", "test2"])
    job_payload = Column(JSON)     # Options: { "save_archive": true } OR { "template_id": 4, "prompt": "..." }
    
    # --- Scheduling Parameters ---
    # If using Cron (Specific Days/Times)
    cron_day_of_week = Column(String, nullable=True) # e.g., "mon,wed,fri" or "*"
    cron_hour = Column(String, nullable=True)        # e.g., "2" (for 2 AM)
    cron_minute = Column(String, nullable=True)      # e.g., "0"
    
    # If using Interval (Every X hours)
    interval_hours = Column(Integer, nullable=True)  # e.g., 12
    run_once_time = Column(DateTime, nullable=True)
    
    # --- State and Audit ---
    is_active = Column(Boolean, default=True)        # Allows you to pause/turn off the job
    created_by = Column(String)                      # The username of the author
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_run_status = Column(String, default="Pending") # 'Success', 'Failed', 'Pending'
    last_run_time = Column(DateTime, nullable=True)