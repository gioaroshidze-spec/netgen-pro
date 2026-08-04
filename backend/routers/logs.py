import threading
import time
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from pydantic import BaseModel
from database import get_db, SessionLocal
import models, schemas
from typing import Optional
from datetime import datetime, timedelta, timezone
from routers.auth import get_current_user, get_current_admin
import os
import zipfile
import io
import re
from fastapi.responses import StreamingResponse
from logger import log_event

router = APIRouter(tags=["Audit Logs"])

# --- DYNAMIC RETENTION CONFIG ---
# Default to 60, but can be updated via the UI
RETENTION_DAYS = 60

class RetentionConfig(BaseModel):
    days: int

@router.get("/logs/retention")
def get_retention_policy(current_user: models.User = Depends(get_current_user)):
    """Fetches the current auto-purge retention policy."""
    return {"days": RETENTION_DAYS}

@router.put("/logs/retention")
def update_retention_policy(config: RetentionConfig, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin)):
    """Updates the daemon's auto-purge retention policy. Admin only."""
    global RETENTION_DAYS
    if config.days < 1:
        raise HTTPException(status_code=400, detail="Retention must be at least 1 day.")
    
    RETENTION_DAYS = config.days
    
    # Audit trail for the policy change
    log_event(
        db=db,
        event_type="System",
        severity="WARNING",
        author=current_admin.username,
        target_devices=[],
        details={"action": "Updated Automated Log Retention Policy", "new_retention_days": RETENTION_DAYS}
    )
    return {"message": f"Auto-purge retention updated to {RETENTION_DAYS} days."}

# ==========================================
# --- ENTERPRISE LOG PURGE DAEMON ---
# ==========================================
def auto_purge_loop():
    """
    Daemon thread that runs every 24 hours and silently purges logs older than RETENTION_DAYS.
    """
    time.sleep(10) # Let the server fully boot first
    
    while True:
        db = SessionLocal()
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
            records_to_delete = db.query(models.EventLog).filter(models.EventLog.timestamp < cutoff_date)
            deleted_count = records_to_delete.count()
            
            if deleted_count > 0:
                records_to_delete.delete(synchronize_session=False)
                db.commit()
                
                # Log the automated cleanup
                log_event(
                    db=db,
                    event_type="System",
                    severity="WARNING",
                    author="System Daemon",
                    target_devices=[],
                    details={
                        "action": "Automated Background Log Purge",
                        "days_retained": RETENTION_DAYS,
                        "records_deleted": deleted_count
                    }
                )
                print(f"[PURGE DAEMON] Successfully purged {deleted_count} logs older than {RETENTION_DAYS} days.")
        except Exception as e:
            print(f"[PURGE DAEMON] Error during automated log cleanup: {e}")
        finally:
            db.close()
        
        # Sleep for 24 hours (86400 seconds)
        time.sleep(86400)

# Kick off the daemon thread automatically when this module is loaded
threading.Thread(target=auto_purge_loop, daemon=True).start()

# ==========================================
# --- STANDARD LOGGING ENDPOINTS ---
# ==========================================

@router.get("/logs/", response_model=list[schemas.EventLogResponse])
def get_audit_logs(
    db: Session = Depends(get_db),
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    author: Optional[str] = None,
    device: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: models.User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    query = db.query(models.EventLog)

    if event_type: query = query.filter(models.EventLog.event_type == event_type)
    if severity: query = query.filter(models.EventLog.severity == severity)
    if author: query = query.filter(models.EventLog.author == author)
    if start_date: query = query.filter(models.EventLog.timestamp >= start_date)
    if end_date: query = query.filter(models.EventLog.timestamp <= end_date)
    if device: query = query.filter(cast(models.EventLog.target_devices, String).like(f'%"{device}"%'))

    return query.order_by(models.EventLog.timestamp.desc()).offset(skip).limit(limit).all()

class ExportLogRequest(BaseModel):
    filters_applied: dict
    record_count: int

@router.post("/logs/export")
def log_csv_export(request: ExportLogRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    log_event(
        db=db,
        event_type="System",
        severity="INFO",
        author=current_user.username,
        target_devices=[],
        details={
            "action": "Exported Audit Logs to CSV",
            "filters": request.filters_applied,
            "total_records": request.record_count
        }
    )
    return {"status": "Logged successfully"}


@router.get("/logs/support-bundle")
def generate_support_bundle(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db) # <-- INJECT DATABASE SESSION HERE
):
    """
    Zips up the backend application logs and a sanitized inventory file for diagnostic support.
    Restricted to Admin users.
    """
    import os
    import zipfile
    import io
    import re
    from fastapi.responses import StreamingResponse
    
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        
        # 1. ADD THE BACKEND LOG FILE
        if os.path.exists("backend_app.log"):
            zip_file.write("backend_app.log", arcname="backend_app.log")
        else:
            zip_file.writestr("backend_app.log", "No log file generated yet.")

        # 2. ADD & SANITIZE THE INVENTORY FILE
        inventory_path = "inventory.ini"
        if os.path.exists(inventory_path):
            with open(inventory_path, "r") as f:
                inventory_data = f.read()
                
            sanitized_inventory = re.sub(
                r'(ansible_password|ansible_become_password)\s*=\s*[^\s]+', 
                r'\1=********', 
                inventory_data
            )
            zip_file.writestr("sanitized_inventory.ini", sanitized_inventory)
        else:
            zip_file.writestr("sanitized_inventory.ini", "Inventory file not found at path.")
            
    zip_buffer.seek(0)

    # 3. Log that the admin generated a bundle safely using injected db
    log_event(
        db=db,
        event_type="System",
        severity="WARNING",
        author=current_user.username,
        target_devices=[],
        details={"action": "Generated Diagnostic Support Bundle"}
    )

    return StreamingResponse(
        zip_buffer, 
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": "attachment; filename=VNMS_Diagnostic_Bundle.zip"}
    )