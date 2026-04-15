from pydantic import BaseModel
from typing import Optional

# This is the shape of the data we EXPECT the user to send us
class DeviceCreate(BaseModel):
    hostname: str
    ip_address: str
    device_type: str
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
    username: Optional[str] = None