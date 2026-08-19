from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import models
from database import engine, SessionLocal
from contextlib import asynccontextmanager
import os
from pathlib import Path
import bcrypt
import logging
from logging.handlers import RotatingFileHandler
from runtime_config import is_production, log_dir
from routers import system as system_router

# Import our routers and scheduler
from routers import devices, maintenance, compare, configuration, logs, templates, cli, auth, jobs, topology, organization
from scheduler_engine import start_scheduler, scheduler # <-- NEW

# --- INITIALIZE SYSTEM FILE LOGGER ---
# This creates a log file that maxes out at 5MB, keeping 3 backups, so it never fills the hard drive.
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
configured_log_dir = log_dir()
backend_log_path = (configured_log_dir / "backend" / "backend_app.log") if configured_log_dir else Path("backend_app.log")
backend_log_path.parent.mkdir(parents=True, exist_ok=True)
log_file_handler = RotatingFileHandler(backend_log_path, maxBytes=5*1024*1024, backupCount=3)
log_file_handler.setFormatter(log_formatter)

# Attach to the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(log_file_handler)

# Initialize Database Engine
if not is_production():
    models.Base.metadata.create_all(bind=engine)

# --- NEW: LIFESPAN MANAGER (Starts and stops background processes) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing VNMS Background Scheduler...")
    start_scheduler()
    yield
    print("Shutting down VNMS Background Scheduler...")
    if scheduler.running:
        scheduler.shutdown()

# Initialize FastAPI App
app = FastAPI(title="VNMS Central API", version="1.0", lifespan=lifespan)

@app.middleware("http")
async def persist_unhandled_exception(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logging.getLogger("vnms.backend").exception(
            "Unhandled backend exception for %s %s", request.method, request.url.path
        )
        raise

# --- THE SURGICAL INCISION: Dynamic CORS Origins ---
# Pulls a comma-separated list from the environment, falling back to local dev ports AND docker ports.
cors_origins = os.getenv(
    "VNMS_ALLOWED_ORIGINS", 
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost,http://127.0.0.1"
).split(",")

# Setup CORS for the React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-VNMS-Change-ID"],
)

# --- SECURED: CREATE DEFAULT ADMIN USER ON STARTUP ---
# Now uses native cryptographic byte compilation to avoid passlib system crashes
db = SessionLocal() if not is_production() else None
admin_exists = db.query(models.User).filter(models.User.username == "admin").first() if db else True
if db and not admin_exists:
    print("Creating default admin user...")
    
    # Secure native salt generation and hashing execution
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw("admin".encode('utf-8'), salt).decode('utf-8')
    
    default_admin = models.User(
        username="admin", 
        hashed_password=hashed_pw, 
        role="admin",
        requires_password_change=True # <-- THIS TRIGGERS THE TRAP
    )
    db.add(default_admin)
    db.commit()
if db:
    db.close()

# --- REGISTER ALL ROUTERS ---
app.include_router(system_router.router)
app.include_router(jobs.router)
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(maintenance.router)
app.include_router(compare.router)
app.include_router(configuration.router)
app.include_router(logs.router)
app.include_router(templates.router)
app.include_router(cli.router)
app.include_router(topology.router)
app.include_router(organization.router)

# Basic Health Check
@app.get("/")
def health_check():
    return {"status": "VNMS API Engine is running smoothly"}
