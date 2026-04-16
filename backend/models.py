from sqlalchemy import Column, Integer, String
from database import Base

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

