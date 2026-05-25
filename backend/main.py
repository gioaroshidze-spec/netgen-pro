from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import models
from database import engine, SessionLocal
from contextlib import asynccontextmanager

# Import our routers and scheduler
from routers import devices, maintenance, compare, configuration, logs, templates, cli, auth, jobs
from scheduler_engine import start_scheduler, scheduler # <-- NEW

# Initialize Database Engine
models.Base.metadata.create_all(bind=engine)

# --- NEW: LIFESPAN MANAGER (Starts and stops background processes) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing VNMS Background Scheduler...")
    start_scheduler()
    yield
    print("Shutting down VNMS Background Scheduler...")
    scheduler.shutdown()

# Initialize FastAPI App
app = FastAPI(title="VNMS Central API", version="1.0", lifespan=lifespan)

# Setup CORS for the React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- NEW: CREATE DEFAULT ADMIN USER ON STARTUP ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
db = SessionLocal()
admin_exists = db.query(models.User).filter(models.User.username == "admin").first()
if not admin_exists:
    print("Creating default admin user...")
    hashed_pw = pwd_context.hash("admin") # Default password is 'admin'
    default_admin = models.User(username="admin", hashed_password=hashed_pw, role="admin")
    db.add(default_admin)
    db.commit()
db.close()

# --- REGISTER ALL ROUTERS ---
app.include_router(jobs.router)
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(maintenance.router)
app.include_router(compare.router)
app.include_router(configuration.router)
app.include_router(logs.router)
app.include_router(templates.router)
app.include_router(cli.router)

# Basic Health Check
@app.get("/")
def health_check():
    return {"status": "VNMS API Engine is running smoothly"}