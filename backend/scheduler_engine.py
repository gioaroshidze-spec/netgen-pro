import os
import io
import zipfile
import asyncio
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from netmiko import ConnectHandler
from apscheduler.triggers.date import DateTrigger
from routers.topology import background_discovery
from database import SessionLocal
import models
from logger import log_event
from ansible_engine import run_ansible_playbook

# Initialize the APScheduler
scheduler = BackgroundScheduler()
ARCHIVE_DIR = "archive"

def execute_scheduled_job(job_id: int, manual_run_by: str = None):
    """The actual worker function. Accepts manual_run_by to track manual executions."""
    db: Session = SessionLocal()
    try:
        job = db.query(models.ScheduledJob).filter(models.ScheduledJob.id == job_id).first()
        if not job or not job.is_active:
            return

        # Determine the execution context
        exec_type = "Manual Run" if manual_run_by else "Automated Schedule"
        triggered_by = manual_run_by if manual_run_by else "Cron/Timer"

        print(f"\n[SCHEDULER] Waking up to execute Job {job_id}: {job.name} (Triggered by: {triggered_by})...")
        targets = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(job.target_devices)).all()
        
        if not targets:
            job.last_run_status = "Failed (No valid targets)"
            job.last_run_time = datetime.now(timezone.utc)
            db.commit()
            return

        # ==========================================
        # 1. EXECUTE BACKUP JOB
        # ==========================================
        if job.job_type == 'backup':
            success_count = 0
            for device in targets:
                try:
                    netmiko_os = 'hp_procurve' if device.os_type in ['aruba', 'hpe'] else 'cisco_ios'
                    connection_params = {
                        'device_type': netmiko_os, 'host': device.ip_address,
                        'username': device.username, 'password': os.getenv("DEVICE_PASSWORD", "Werfds123"),
                    }
                    with ConnectHandler(**connection_params) as net_connect:
                        net_connect.enable()
                        
                        if job.job_payload.get('save_nvram'): net_connect.save_config()
                        if job.job_payload.get('save_flash'):
                            net_connect.send_command_timing("copy running-config flash:VNMS_Last_Good.cfg\n")
                        
                        raw_config = net_connect.send_command("show running-config")
                        clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration")]
                        config = "\n".join(clean_lines)

                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"Scheduled_{job.name.replace(' ', '_')}_{device.os_type}_{device.device_type}_{device.hostname}_{timestamp}.txt"
                        
                        os.makedirs(ARCHIVE_DIR, exist_ok=True)
                        with open(os.path.join(ARCHIVE_DIR, filename), "w") as f:
                            f.write(config)
                        success_count += 1
                except Exception as e:
                    print(f"[SCHEDULER] Error backing up {device.hostname}: {e}")

            # ALWAYS log as "System", but put the forensic data in the details!
            log_event(
                db=db, event_type="Maintenance", severity="INFO" if success_count > 0 else "ERROR", 
                author="System",  # <--- FIXED
                target_devices=job.target_devices,
                details={
                    "action": "Scheduled Backup Executed", 
                    "execution_type": exec_type, 
                    "triggered_by": triggered_by,  # <--- Added to show who clicked Run Now
                    "scheduled_by": job.created_by, # <--- Shows who originally created the job
                    "job_name": job.name, 
                    "success_count": success_count
                }
            )

        # ==========================================
        # 2. EXECUTE TEMPLATE PUSH
        # ==========================================
        elif job.job_type == 'template_push':
            prompt_audit = f"Scheduled Job: {job.name} | Type: {exec_type} | Triggered By: {triggered_by} | Originally Scheduled By: {job.created_by}"
            
            generator = run_ansible_playbook(
                config_data=job.job_payload.get('template_config', {}),
                devices=targets,
                db=db,
                prompt=prompt_audit,
                is_check_mode=False,
                author="System"  # <--- FIXED
            )
            
            output_logs = ""
            try:
                for chunk in generator:
                    output_logs += chunk
            except Exception as e:
                output_logs += f"\nError reading ansible stream: {str(e)}"
            
            print(f"[SCHEDULER] Template push {job.name} finished.")

        job.last_run_status = "Success"
        job.last_run_time = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        print(f"[SCHEDULER] Job {job_id} failed catastrophically: {e}")
        if 'job' in locals() and job:
            job.last_run_status = f"Failed: {str(e)[:50]}"
            job.last_run_time = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
def sync_jobs_to_scheduler():
    """Reads the database and loads all active jobs into the APScheduler clock."""
    scheduler.remove_all_jobs()
    db = SessionLocal()
    
    try:
        active_jobs = db.query(models.ScheduledJob).filter(models.ScheduledJob.is_active == True).all()
        for job in active_jobs:
            job_id_str = f"job_{job.id}"
            
            # Determine Trigger Type
            if job.run_once_time:
                trigger = DateTrigger(run_date=job.run_once_time)
            elif job.interval_hours:
                trigger = IntervalTrigger(hours=job.interval_hours)
            else:
                trigger = CronTrigger(
                    day_of_week=job.cron_day_of_week or '*',
                    hour=job.cron_hour or '*',
                    minute=job.cron_minute or '0'
                )
            
            scheduler.add_job(
                execute_scheduled_job,
                trigger=trigger,
                args=[job.id],
                id=job_id_str,
                replace_existing=True
            )
        print(f"[SCHEDULER] Synced {len(active_jobs)} active jobs to the engine.")
    except Exception as e:
        print(f"[SCHEDULER] Error syncing jobs: {e}")
    finally:
        db.close()

def start_scheduler():
    sync_jobs_to_scheduler()
    
    # --- NEW: Permanent System Discovery Sweep (1 Hour) ---
    scheduler.add_job(
        background_discovery,
        trigger=IntervalTrigger(hours=1),
        args=["System_Scheduler"], # This sets the author in the Audit Logs!
        id="system_topology_discovery",
        replace_existing=True
    )
    
    scheduler.start()