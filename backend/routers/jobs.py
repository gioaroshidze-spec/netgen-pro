from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from routers.auth import get_current_user
from scheduler_engine import sync_jobs_to_scheduler
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from scheduler_engine import sync_jobs_to_scheduler, execute_scheduled_job

router = APIRouter(tags=["Scheduled Jobs"])

@router.get("/jobs/", response_model=List[schemas.ScheduledJobResponse])
def get_jobs(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Returns all jobs so they can be viewed in the Maintenance tab."""
    return db.query(models.ScheduledJob).all()

@router.post("/jobs/", response_model=schemas.ScheduledJobResponse)
def create_job(job: schemas.ScheduledJobCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Creates a new job, enforcing strict RBAC rules for Viewers."""
    
    if current_user.role != "admin":
        # 1. Viewers cannot schedule templates
        if job.job_type != "backup":
            raise HTTPException(status_code=403, detail="Viewers can only schedule backup jobs.")
        
        # 2. Viewers cannot schedule NVRAM or Flash saves
        payload = job.job_payload
        if payload.get("save_nvram") or payload.get("save_flash"):
            raise HTTPException(status_code=403, detail="Viewers cannot schedule backups to NVRAM or Flash.")

    new_job = models.ScheduledJob(**job.model_dump(), created_by=current_user.username)
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    sync_jobs_to_scheduler()
    return new_job

@router.put("/jobs/{job_id}/toggle")
def toggle_job(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Allows a user to pause or resume a job."""
    job = db.query(models.ScheduledJob).filter(models.ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # RBAC: Viewers can only toggle their OWN jobs
    if current_user.role != "admin" and job.created_by != current_user.username:
        raise HTTPException(status_code=403, detail="You can only modify your own jobs.")

    job.is_active = not job.is_active
    db.commit()

    sync_jobs_to_scheduler()
    return {"message": f"Job {'activated' if job.is_active else 'paused'}", "is_active": job.is_active}

@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Deletes a job from the database."""
    job = db.query(models.ScheduledJob).filter(models.ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # RBAC: Viewers can only delete their OWN jobs
    if current_user.role != "admin" and job.created_by != current_user.username:
        raise HTTPException(status_code=403, detail="You can only delete your own jobs.")
    
    db.delete(job)
    db.commit()

    sync_jobs_to_scheduler()
    return {"message": "Job deleted successfully"}

@router.post("/jobs/{job_id}/run")
def run_job_now(job_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Triggers a job instantly in the background."""
    job = db.query(models.ScheduledJob).filter(models.ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if current_user.role != "admin" and job.created_by != current_user.username:
        raise HTTPException(status_code=403, detail="You can only run your own jobs.")

    # Pass the user's username to the background worker!
    background_tasks.add_task(execute_scheduled_job, job.id, current_user.username)
    return {"message": "Job execution started in the background. Check Event Logs shortly."}