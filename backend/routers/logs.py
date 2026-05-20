from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from database import get_db
import models, schemas
from typing import Optional
from datetime import datetime

router = APIRouter(tags=["Audit Logs"])

@router.get("/logs/", response_model=list[schemas.EventLogResponse])
def get_audit_logs(
    db: Session = Depends(get_db),
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    author: Optional[str] = None,
    device: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=500), # Default to 50 logs to keep UI fast
    skip: int = Query(0, ge=0)
):
    """
    Fetches the audit logs with highly flexible, optional filtering parameters.
    """
    query = db.query(models.EventLog)

    # 1. Exact Match Filters
    if event_type:
        query = query.filter(models.EventLog.event_type == event_type)
    if severity:
        query = query.filter(models.EventLog.severity == severity)
    if author:
        query = query.filter(models.EventLog.author == author)
        
    # 2. Time Interval Filters
    if start_date:
        query = query.filter(models.EventLog.timestamp >= start_date)
    if end_date:
        query = query.filter(models.EventLog.timestamp <= end_date)
        
    # 3. Target Device Filter (JSON Search)
    if device:
        # We cast the JSON array to a string to safely search inside it across all SQL dialects
        query = query.filter(cast(models.EventLog.target_devices, String).like(f'%"{device}"%'))

    # Order by newest first, then apply pagination (skip/limit)
    logs = query.order_by(models.EventLog.timestamp.desc()).offset(skip).limit(limit).all()
    
    return logs