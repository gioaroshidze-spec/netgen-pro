from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import engine, SessionLocal

# Create the database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NetGen Pro API",
    description="Backend engine for network Management System",
    version="1.0.0"
)

# --- DATABASE DEPENDENCY ---
# This function opens a connection to the DB for every request, the safely closes it
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API ENDPOINT ---

@app.get("/")
def read_root():
    return {"status": "online", "message": "NetGen Pro Backend is active!"}

# 1. Create a new device (POST)
@app.post("/device/", response_model=schemas.DeviceResponse)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db)):
    # Package the incoming data into a database model
    db_device = models.NetworkDevice(
        hostname=device.hostname,
        ip_address=device.ip_address,
        device_type=device.device_type,
        username=device.username
    )

    # Add to DB, commit the transaction, and refresh to get the new ID
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device

# 2. Get a list of all devices (GET)
@app.get("/device/", response_model=list[schemas.DeviceResponse])
def get_devices(db: Session = Depends(get_db)):
    #Query the database for all NetworkDevice records
    devices = db.query(models.NetworkDevice).all()
    return devices