import os
import io
import zipfile
import asyncio
import re
import json
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

from routers.auth import decrypt_secret
from connection_utils import get_netmiko_params

# Initialize the APScheduler
scheduler = BackgroundScheduler()
ARCHIVE_DIR = "archive"

def get_device_meta(device: models.NetworkDevice):
    """Helper to format device data cleanly for the Event Logs UI."""
    return {
        "hostname": device.hostname,
        "ip_address": device.ip_address,
        "device_type": device.device_type,
        "os_type": device.os_type
    }

def execute_scheduled_job(job_id: int, manual_run_by: str = None):
    """The actual worker function. Accepts manual_run_by to track manual executions."""
    db: Session = SessionLocal()
    try:
        job = db.query(models.ScheduledJob).filter(models.ScheduledJob.id == job_id).first()
        if not job or not job.is_active:
            return

        exec_type = "Manual Run" if manual_run_by else "Automated Schedule"
        triggered_by = manual_run_by if manual_run_by else "System_Scheduler"

        print(f"\n[SCHEDULER] Waking up to execute Job {job_id}: {job.name} (Triggered by: {triggered_by})...")
        targets = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(job.target_devices)).all()
        
        target_devices_payload = [get_device_meta(d) for d in targets]

        if not targets:
            job.last_run_status = "Failed (No valid targets)"
            job.last_run_time = datetime.now(timezone.utc)
            db.commit()
            return

        # Determine readable schedule timing
        schedule_timing = "Run Once"
        if job.interval_hours:
            schedule_timing = f"Recurring: Every {job.interval_hours} hours"
        elif job.cron_day_of_week:
            schedule_timing = f"Recurring: {job.cron_day_of_week} @ {job.cron_hour or '00'}:{job.cron_minute or '00'}"

        # ==========================================
        # 1. EXECUTE BACKUP JOB
        # ==========================================
        if job.job_type == 'backup':
            success_count = 0
            for device in targets:
                try:
                    show_cmd = "show running-config"
                    
                    if device.os_type == 'mikrotik': 
                        show_cmd = "/export"
                    elif device.os_type in ['alcatel', 'alcatel-lucent']: 
                        show_cmd = "show configuration snapshot"

                    connection_params = get_netmiko_params(device)
                    
                    with ConnectHandler(**connection_params) as net_connect:
                        if device.os_type != 'mikrotik':
                            try: net_connect.enable()
                            except: pass
                        
                        if job.job_payload.get('save_nvram') and device.os_type != 'mikrotik': 
                            try: net_connect.save_config()
                            except: pass
                            
                        if job.job_payload.get('save_flash'):
                            if device.os_type == 'cisco':
                                net_connect.send_command_timing("copy running-config flash:VNMS_Last_Good.cfg\n")
                            elif device.os_type == 'mikrotik':
                                net_connect.send_command("/export file=VNMS_Last_Good")
                        
                        raw_config = net_connect.send_command(show_cmd)
                        clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                        config = "\n".join(clean_lines)

                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"Scheduled_{job.name.replace(' ', '_')}_{device.os_type}_{device.device_type}_{device.hostname}_{timestamp}.txt"
                        
                        os.makedirs(ARCHIVE_DIR, exist_ok=True)
                        with open(os.path.join(ARCHIVE_DIR, filename), "w") as f:
                            f.write(config)
                        success_count += 1
                except Exception as e:
                    print(f"[SCHEDULER] Error backing up {device.hostname}: {e}")

            # Rich Audit Log for Scheduled Backups
            exec_status = "Success" if success_count == len(targets) else "Partial Failure" if success_count > 0 else "Failed"
            log_event(
                db=db, 
                event_type="Maintenance", 
                severity="SUCCESS" if success_count == len(targets) else "WARNING" if success_count > 0 else "ERROR", 
                author="System_Scheduler",
                target_devices=target_devices_payload,
                details={
                    "action": "Scheduled Job Execution", 
                    "job_name": job.name,
                    "job_type": "Automated Backup",
                    "created_by": job.created_by,
                    "enabled_by": triggered_by,
                    "schedule_timing": schedule_timing,
                    "execution_status": exec_status,
                    "options": job.job_payload
                }
            )

        # ==========================================
        # 2. EXECUTE TEMPLATE PUSH
        # ==========================================
        elif job.job_type == 'template_push':
            generator = run_ansible_playbook(
                ai_config_data=job.job_payload.get('template_config', {}),
                devices=targets,
                is_check_mode=False
            )
            
            output_logs = ""
            try:
                for chunk in generator:
                    output_logs += chunk
            except Exception as e:
                output_logs += f"\nError reading ansible stream: {str(e)}"
            
            # Regex Surgery to extract errors and recap
            clean_output = output_logs.replace("data: ", "").replace("\n\n", "\n")
            parts = re.split(r'(?=TASK \[|PLAY RECAP)', clean_output)
            
            important_blocks = []
            for i, part in enumerate(parts):
                if "PLAY RECAP" in part:
                    important_blocks.append(part.strip())
                elif re.search(r'^[ \t]*(fatal|failed|skipping|\[ERROR\])', part, re.MULTILINE | re.IGNORECASE):
                    important_blocks.append(part.strip())
                elif i == 0 and re.search(r'(error|fatal)', part, re.IGNORECASE):
                    important_blocks.append(part.strip())
                    
            final_ansible_log = "\n\n".join(important_blocks)
            if not final_ansible_log.strip():
                final_ansible_log = "--- NO ERRORS OR SKIPS DETECTED ---\n\n"
                recap_idx = clean_output.rfind("PLAY RECAP")
                if recap_idx != -1:
                    final_ansible_log += clean_output[recap_idx:].strip()
                else:
                    final_ansible_log += clean_output[-1000:] if len(clean_output) > 1000 else clean_output

            has_failures = bool(re.search(r'failed=[1-9]\d*|unreachable=[1-9]\d*', final_ansible_log)) or bool(re.search(r'^[ \t]*(fatal|failed|\[ERROR\])', final_ansible_log, re.MULTILINE | re.IGNORECASE))
            
            # Rich Audit Log for Scheduled Configurations
            log_event(
                db=db, 
                event_type="Configuration", 
                severity="ERROR" if has_failures else "SUCCESS", 
                author="System_Scheduler",
                target_devices=target_devices_payload,
                details={
                    "action": "Scheduled Job Execution", 
                    "job_name": job.name,
                    "job_type": "Automated Configuration",
                    "created_by": job.created_by,
                    "enabled_by": triggered_by,
                    "schedule_timing": schedule_timing,
                    "execution_status": "Failed" if has_failures else "Success",
                    "generated_commands": json.dumps(job.job_payload.get('template_config', {}), indent=2),
                    "ansible_logs": final_ansible_log.strip()
                }
            )
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
    scheduler.remove_all_jobs()
    db = SessionLocal()
    
    try:
        active_jobs = db.query(models.ScheduledJob).filter(models.ScheduledJob.is_active == True).all()
        for job in active_jobs:
            job_id_str = f"job_{job.id}"
            
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
    scheduler.add_job(
        background_discovery,
        trigger=IntervalTrigger(hours=1),
        args=["System_Scheduler"],
        id="system_topology_discovery",
        replace_existing=True
    )
    scheduler.start()