from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import models
from database import engine

# Import our new segregated routers
from routers import devices, maintenance, compare, configuration

# Initialize Database Engine
models.Base.metadata.create_all(bind=engine)

# Initialize FastAPI App
app = FastAPI(title="VNMS Central API", version="1.0")

# Setup CORS for the React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTER ALL ROUTERS ---
app.include_router(devices.router)
app.include_router(maintenance.router)
app.include_router(compare.router)
app.include_router(configuration.router)

# Basic Health Check
@app.get("/")
def health_check():
    return {"status": "VNMS API Engine is running smoothly"}