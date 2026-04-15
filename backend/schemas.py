from pydantic import BaseModel

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