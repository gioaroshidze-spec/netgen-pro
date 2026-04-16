from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import subprocess
import models, schemas
from database import engine, SessionLocal

# Create the database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NetGen Pro API",
    description="Backend engine for network Management System",
    version="1.0.0"
)

# --- CORS CONFIGURATION ---
# This allows your React frontend to securely talk to the FastAPI backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React's address
    allow_credentials=True,
    allow_methods=["*"],  # Allows all standard methods (GET, POST, etc.)
    allow_headers=["*"],
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

# 3. Update an existing device (PUT)
@app.put("/devices/{device_id}", response_model=schemas.DeviceResponse)
def update_device(device_id: int, device_update: schemas.DeviceUpdate, db: Session = Depends(get_db)):
    # Find the device in the database
    db_device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()

    # If it doesn't exist, throw a 404 error
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Update only the fields the user actually sent us
    update_data = device_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_device, key, value)

    db.commit()
    db.refresh(db_device)
    return db_device

# 4. Delete a device (DELETE)
@app.delete("/devices/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    # Find the device in the database
    db_device = db.query(models.NetworkDevice).filter(models.NetworkDevice.id == device_id).first()

    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    
    db.delete(db_device)
    db.commit()
    return {"message": f"Device {device_id} successfully deleted"}

# 5. Network Mapper (GET)
@app.get("/network-map/")
def get_network_map(db: Session = Depends(get_db)):
    # Grab all devices from our database "inventory"
    devices = db.query(models.NetworkDevice).all()
    mapped_devices = []

    for device in devices:
        
        # Clean the IP of any invisible space or newlines
        clean_ip = device.ip_address.strip()

        # We run the native Ubuntu ping command:
        # -c 1 (send exactly 1 packet)
        # -W 1 (wait a maximum of 1 second for a reply)
        command = ["ping", "-c", "1", "-W", "1", clean_ip]

        # Execute the command in the background
        response = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # If it fails, print the EXACT Ubuntu error to your VS Code terminal
        if response.returncode != 0:
            print(f"PING FAILED for {clean_ip}")
            print(f"Error output: {response.stderr.strip()}")
            print(f"Standard output: {response.stdout.strip()}")
            print("-" * 30)


        # If returncode is 0, the ping was successful
        status = "online" if response.returncode == 0 else "offline"

        mapped_devices.append({
            "id": device.id,
            "hostname": device.hostname,
            "ip_address": device.ip_address,
            "device_type": device.device_type,
            "status": status
        })
    return mapped_devices