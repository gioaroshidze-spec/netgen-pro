import json
import os
import re
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
from litellm import completion
from netmiko import ConnectHandler

# --- IMPORT THE BOUNCERS ---
from routers.auth import get_current_admin, get_current_user
from ansible_engine import normalize_ansible_payload, run_ansible_playbook
from routers.auth import decrypt_secret
from logger import log_event
from backup_service import create_preconfiguration_backups
from change_control import proposal_hash
from verification_service import run_verification, VerificationConflict
from rollback_service import (
    ACTIVE_ROLLBACK_STATES,
    ELIGIBLE_CHANGE_STATES,
    RollbackRejected,
    active_manual_restore_locks,
    authorize_rollback,
    cancel_manual_restore,
    execute_rollback,
    manual_restore_handoff,
    overlapping_active_rollback,
    persist_backup_artifacts,
    prepare_manual_restore,
    rollback_lifecycle_blocker,
    sanitize_backup_results,
    verify_manual_restore,
)
from device_capabilities import AUTOMATED_RESTORE_UNQUALIFIED_REASON

router = APIRouter(tags=["Configuration Engine"])

# ==========================================
# --- STRICT ANSIBLE PAYLOAD SANITIZER ---
# ==========================================
def validate_ansible_payload(payload: dict, devices):
    """
    Strictly validates the payload through the same vendor-aware normalization
    boundary used by both check-mode simulation and live production execution.
    """
    normalize_ansible_payload(payload, devices)

# ==========================================
# --- STREAM INTERCEPTOR & LOGGER ---
# ==========================================
def simulation_succeeded(output):
    clean = output.replace("data: ", "").replace("\n\n", "\n")
    has_recap = "PLAY RECAP" in clean
    complete = "PLAYBOOK COMPLETE: No errors detected." in clean
    failed = bool(re.search(r"failed=[1-9]\d*|unreachable=[1-9]\d*", clean, re.IGNORECASE))
    fatal = bool(re.search(r"(^|\n)\s*(fatal|failed|\[ERROR\])", clean, re.IGNORECASE))
    return has_recap and complete and not failed and not fatal

def stream_ansible_and_log(ansible_stream, db: Session, prompt: str, ai_config_data: dict, devices: list, mode: str, author: str, source_template: str = None, change=None):
    """
    Wraps the Ansible output generator. Streams data to the frontend in real-time,
    and once finished, parses the recap, skips, and errors to save a rich audit log.
    """
    full_output = ""
    
    # 1. Yield chunks to the frontend exactly as they arrive
    try:
        for chunk in ansible_stream:
            full_output += chunk
            yield chunk
    except Exception as exc:
        full_output += f"\ndata: [ERROR] {exc}\n\n"
        yield f"data: [ERROR] {exc}\n\n"

    # 2. Once the stream finishes, clean the SSE formatting for parsing
    clean_output = full_output.replace("data: ", "").replace("\n\n", "\n")

    # 3. Surgically extract ONLY the relevant blocks (Failures, Skips & Recap)
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

    final_ansible_log = final_ansible_log.strip()

    # 4. Determine strict Success/Fail status
    has_failures = not simulation_succeeded(full_output)
    final_severity = "ERROR" if has_failures else "SUCCESS"
    execution_status = "Failed" if has_failures else "Success"

    # 5. Build the rich target device payload
    target_devices_payload = [
        {
            "hostname": dev.hostname,
            "ip_address": dev.ip_address,
            "device_type": dev.device_type,
            "os_type": dev.os_type
        } for dev in devices
    ]

    # 6. Build the UI Details mapping
    details = {
        "action": "AI Configuration Deployment",
        "mode": mode,
        "prompt": prompt,
        "generated_commands": json.dumps(ai_config_data, indent=2),
        "execution_status": execution_status,
        "ansible_logs": final_ansible_log
    }
    if change:
        details.update({"change_id": change.change_id, "proposal_hash": change.proposal_hash})
        if mode == "Production Push":
            details.update({
                "pre_backup_files": change.pre_backup_files,
                "simulation_gate": "failed_overridden" if change.simulation_override else "passed",
            })

    # INJECT TEMPLATE TRACKING IF PRESENT
    if source_template:
        details["source_template"] = source_template

    # 7. Commit to database
    log_event(
        db=db,
        event_type="Configuration",
        severity=final_severity,
        details=details,
        target_devices=target_devices_payload,
        author=author
    )
    if change:
        now = datetime.now(timezone.utc)
        if mode.startswith("Simulate"):
            change.simulation_completed_at = now
            change.simulation_success = not has_failures
            change.status = "simulation_passed" if not has_failures else "simulation_failed"
        else:
            change.deployed_at = now if not has_failures else None
            change.status = "verifying" if not has_failures else "deployment_failed"
        db.commit()
        if mode == "Production Push" and not has_failures:
            yield "data: --------------------------------------------------\n\n"
            yield "data: Verifying post-change state...\n\n"
            verification = run_verification(
                db, change, devices, "System", run_ansible_playbook,
                audit_logger=log_event,
            )
            if verification.status == "verified":
                yield "data: POST-CHANGE VERIFICATION PASSED: All target devices are converged.\n\n"
            elif verification.status == "verification_failed":
                yield "data: POST-CHANGE VERIFICATION FAILED: One or more devices differ from the approved desired state.\n\n"
            else:
                yield "data: POST-CHANGE VERIFICATION INCONCLUSIVE: VNMS could not reliably determine final state.\n\n"


# ==========================================
# --- ROUTES ---
# ==========================================
@router.post("/configuration/generate")
def generate_configuration(request: schemas.AIConfigGenerate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    target_hostnames = request.switches + request.routers
    devices = []
    if target_hostnames:
        devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()

    os_mapping_text = ""
    for dev in devices:
        os_mapping_text += f"- Hostname: {dev.hostname} | OS Type: {dev.os_type.upper()}\n"

    system_prompt = (
        "You are an expert Enterprise Network Automation API. "
        "Your job is to read the network requirement and the provided running configs, and output the desired state. "
        "CRITICAL RULES: "
        "1. You MUST respond ONLY with a raw, valid JSON object. No markdown, no conversational text. "
        "2. The JSON object must map exact hostnames to a dictionary containing TWO keys: 'config' and 'exec'. "
        "3. VENDOR SYNTAX STRICTNESS: You must generate the exact, vendor-specific syntax for each device based on its operating system.\n"
        "   - Cisco (cisco): Standard Cisco IOS commands.\n"
        "   - Aruba/HPE (aruba/hpe): Use Aruba AOS-CX or ProVision syntax as appropriate.\n"
        "   - MikroTik (mikrotik): Use MikroTik RouterOS syntax (e.g., '/ip address add...').\n"
        "   - Alcatel-Lucent (alcatel): Use Alcatel AOS syntax.\n"
        "4. The 'config' list is strictly for configuration mode commands. Never include 'conf t', 'configure terminal', 'exit', or 'end'. "
        "5. CISCO IOS HIERARCHY: Global configuration commands may be strings. Commands requiring parent context MUST use an object containing exactly 'parents' and 'lines'; never flatten child commands or use context-changing commands. "
        "Cisco interface example: {\"cctv_sw1\": {\"config\": [{\"parents\": [\"interface GigabitEthernet0/1\"], \"lines\": [\"description VNMS_PHASE2_TRANSPORT_TEST\"]}], \"exec\": []}}. "
        "Cisco global VLAN example: {\"cctv_sw1\": {\"config\": [\"vlan 123\"], \"exec\": []}}. "
        "Cisco VLAN submode example: {\"parents\": [\"vlan 123\"], \"lines\": [\"name USERS\"]}. "
        "Nested Cisco contexts preserve parent order, for example parents ['router ospf 10', 'address-family ipv4']. "
        "6. The 'exec' list is strictly for Privileged EXEC mode commands (e.g., 'write memory', 'copy run start'); never put 'write memory' in 'config'. "
        "7. TEMPLATE OVERRIDE: If a base template is provided, preserve its architectural logic but translate the syntax and hierarchy to match the target device's OS. "
    )

    user_prompt = f"Target Devices & Operating Systems:\n{os_mapping_text if os_mapping_text else 'None'}\n\nNetwork Requirement: {request.prompt}"

    if request.base_template:
        user_prompt += f"\n\n--- BASE TEMPLATE PROVIDED ---\nAdapt the following configuration structure for the new targets, translating to their specific OS syntax:\n{json.dumps(request.base_template, indent=2)}"

    device_context = ""
    
    if devices:
        for dev in devices:
            try:
                netmiko_os = 'cisco_ios'
                if dev.os_type == 'aruba': netmiko_os = 'aruba_os'
                elif dev.os_type == 'hpe': netmiko_os = 'hp_procurve'
                elif dev.os_type == 'mikrotik': netmiko_os = 'mikrotik_routeros'
                elif dev.os_type in ['alcatel', 'alcatel-lucent']: netmiko_os = 'alcatel_aos'
                
                connection_params = {
                    'device_type': netmiko_os, 'host': dev.ip_address,
                    'username': dev.username, 'password': decrypt_secret(dev.encrypted_password),
                    'fast_cli': True
                }
                
                with ConnectHandler(**connection_params) as net_connect:
                    if dev.os_type != 'mikrotik':
                        try: net_connect.enable()
                        except: pass
                    
                    show_cmd = "show running-config"
                    if dev.os_type == 'mikrotik': show_cmd = "/export"
                    elif dev.os_type in ['alcatel', 'alcatel-lucent']: show_cmd = "show configuration snapshot"
                    
                    raw_config = net_connect.send_command(show_cmd)
                    clean_lines = [line for line in raw_config.splitlines() if not line.startswith("Building configuration") and not line.startswith("Current configuration")]
                    config_content = "\n".join(clean_lines)
                    
                    device_context += f"\n! --- LIVE RUNNING CONFIGURATION FOR {dev.hostname} ({dev.os_type.upper()}) ---\n{config_content}\n"
                    
            except Exception as e:
                print(f"Failed to fetch live config for {dev.hostname}: {e}")
                device_context += f"\n! --- ERROR: COULD NOT FETCH LIVE CONFIG FOR {dev.hostname}. Rely strictly on user prompt. ---\n"
    
    if device_context:
        user_prompt += f"\n\nHere is the LIVE running configuration for the target devices. Analyze this to ensure your generated commands don't conflict with existing setups:\n{device_context}"

    try:
        model_name = os.getenv("ACTIVE_AI_MODEL", "claude-opus-4-7") 
        response = completion(
            model=model_name,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )
        
        raw_response = response.choices[0].message.content
        clean_text = raw_response.replace("```json", "").replace("```", "").strip()
        
        try:
            parsed_json = json.loads(clean_text)
            beautiful_json = json.dumps(parsed_json, indent=2) 
            return {"status": "success", "config": beautiful_json}
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="AI generated invalid JSON format. Please try generating again.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Engine Error: Check console for details. {str(e)}")


@router.post("/configuration/simulate")
def simulate_configuration(request: schemas.SimulateConfigRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not request.switches and not request.routers:
        raise HTTPException(status_code=400, detail="No target devices selected.")
    try: 
        ai_config_data = json.loads(request.config_text)
    except json.JSONDecodeError: 
        raise HTTPException(status_code=400, detail="Configuration is not valid JSON.")
    if not isinstance(ai_config_data, dict):
        raise HTTPException(
            status_code=400,
            detail="Root payload must be a JSON object mapping hostnames to commands.",
        )

    target_hostnames = request.switches + request.routers
    if len(target_hostnames) != len(set(target_hostnames)):
        raise HTTPException(status_code=400, detail="Duplicate target hostnames are not allowed.")
    normalized_targets = sorted(target_hostnames)
    if set(ai_config_data) != set(normalized_targets):
        raise HTTPException(status_code=400, detail="Configuration hostnames must exactly match selected targets.")
    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(target_hostnames)).all()
    if len(devices) != len(normalized_targets):
        raise HTTPException(status_code=404, detail="One or more selected devices were not found in the database.")
    try:
        validate_ansible_payload(ai_config_data, devices)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    source_template = request.source_template
    change = models.ConfigurationChange(
        change_id=str(uuid.uuid4()), created_by=current_user.username, prompt=request.prompt,
        source_template=source_template, target_devices=normalized_targets,
        config_payload=ai_config_data,
        proposal_hash=proposal_hash(ai_config_data, normalized_targets, source_template),
        status="simulating", simulation_started_at=datetime.now(timezone.utc),
        simulated_by=current_user.username,
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    ansible_stream = run_ansible_playbook(ai_config_data, devices, is_check_mode=True)

    return StreamingResponse(
        stream_ansible_and_log(ansible_stream, db, request.prompt, ai_config_data, devices, "Simulate (--check)", current_user.username, source_template, change),
        media_type="text/event-stream", headers={"X-VNMS-Change-ID": change.change_id}
    )

@router.post("/configuration/push")
def push_configuration(request: schemas.PushConfigRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    change = db.query(models.ConfigurationChange).filter(models.ConfigurationChange.change_id == request.change_id).first()
    if not change:
        raise HTTPException(status_code=404, detail="Configuration change not found.")
    if change.status in ("deployed", "deploying", "deployment_failed", "pre_backup_failed"):
        raise HTTPException(status_code=409, detail="Configuration change has already been consumed.")
    expected_hash = proposal_hash(change.config_payload, change.target_devices, change.source_template)
    if expected_hash != change.proposal_hash:
        log_event(db=db, event_type="Configuration", severity="ERROR", author=current_user.username,
                  details={"action": "Proposal Integrity Failure", "change_id": change.change_id}, target_devices=[])
        raise HTTPException(status_code=409, detail="Stored proposal integrity verification failed.")
    if change.status not in ("simulation_passed", "admin_override_authorized"):
        raise HTTPException(status_code=409, detail=f"Configuration change is not deployable from state '{change.status}'.")

    conflict = overlapping_active_rollback(db, change.target_devices)
    if conflict:
        active_rollback, overlapping_hostnames = conflict
        reason = (
            f"Active manual restore {active_rollback.rollback_id} blocks production "
            f"Push for overlapping target device(s): {', '.join(overlapping_hostnames)}."
        )
        log_event(
            db=db,
            event_type="Configuration",
            severity="WARNING",
            author=current_user.username,
            target_devices=overlapping_hostnames,
            details={
                "action": "Production Push Rejected - Active Manual Restore",
                "change_id": change.change_id,
                "rollback_id": active_rollback.rollback_id,
                "overlapping_hostnames": overlapping_hostnames,
                "reason": reason,
                "device_contact_performed": False,
                "device_configuration_changed": False,
            },
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "active_manual_restore",
                "message": reason,
                "owner_change_id": active_rollback.change_id,
                "rollback_id": active_rollback.rollback_id,
                "overlapping_hostnames": overlapping_hostnames,
                "state": active_rollback.status,
            },
        )

    devices = db.query(models.NetworkDevice).filter(models.NetworkDevice.hostname.in_(change.target_devices)).all()
    if len(devices) != len(change.target_devices) or {d.hostname for d in devices} != set(change.target_devices):
        raise HTTPException(status_code=409, detail="One or more stored target devices no longer exist.")
    change.status = "awaiting_pre_backup"
    db.commit()
    files, backup_results = create_preconfiguration_backups(devices)
    change.pre_backup_files = files
    change.pre_backup_completed_at = datetime.now(timezone.utc)
    expected_targets = set(change.target_devices)
    successful_targets = {
        result["hostname"] for result in backup_results if result.get("success")
    }
    failures = sorted(
        {result["hostname"] for result in backup_results if not result.get("success")}
        | (expected_targets - successful_targets)
        | (expected_targets - set(files))
    )
    for result in backup_results:
        log_event(db=db, event_type="Configuration", severity="SUCCESS" if result["success"] else "ERROR",
                  author=current_user.username, target_devices=[result["hostname"]],
                  details={"action": "Pre-Configuration Backup", "change_id": change.change_id,
                           "target": result["hostname"], "success": result["success"],
                           "filename": files.get(result["hostname"]), "error": result.get("error")})
    if failures:
        change.pre_backup_success = False
        change.status = "pre_backup_failed"
        db.commit()
        raise HTTPException(status_code=502, detail={"message": "Pre-configuration backup failed; deployment blocked.", "failed_targets": failures})
    try:
        artifacts = persist_backup_artifacts(db, change.change_id, backup_results, "pre_config")
    except Exception as exc:
        db.rollback()
        change = db.query(models.ConfigurationChange).filter(
            models.ConfigurationChange.change_id == request.change_id
        ).one()
        change.pre_backup_success = False
        change.status = "pre_backup_failed"
        db.commit()
        log_event(db=db, event_type="Configuration", severity="ERROR", author=current_user.username,
                  target_devices=change.target_devices,
                  details={"action": "Pre-Configuration Artifact Persistence Failed",
                           "change_id": change.change_id, "proposal_hash": change.proposal_hash,
                           "error": str(exc)})
        raise HTTPException(status_code=502, detail="Pre-configuration artifact integrity metadata could not be persisted; deployment blocked.")
    log_event(db=db, event_type="Configuration", severity="SUCCESS", author=current_user.username,
              target_devices=change.target_devices,
              details={"action": "Pre-Configuration Artifacts Integrity-Bound",
                       "change_id": change.change_id, "proposal_hash": change.proposal_hash,
                       "artifacts": {a.hostname: {"filename": a.filename, "sha256": a.sha256,
                                                   "size_bytes": a.size_bytes} for a in artifacts}})
    change.pre_backup_success = True
    change.status = "deploying"
    change.deployed_by = current_user.username
    db.commit()
    ansible_stream = run_ansible_playbook(change.config_payload, devices, is_check_mode=False)

    return StreamingResponse(
        stream_ansible_and_log(ansible_stream, db, change.prompt, change.config_payload, devices, "Production Push", current_user.username, change.source_template, change),
        media_type="text/event-stream"
    )

@router.post("/configuration/changes/{change_id}/override-simulation")
def authorize_simulation_override(
    change_id: str,
    request: schemas.SimulationOverrideRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    change = db.query(models.ConfigurationChange).filter(models.ConfigurationChange.change_id == change_id).first()
    if not change:
        raise HTTPException(status_code=404, detail="Configuration change not found.")
    if change.status != "simulation_failed":
        raise HTTPException(status_code=409, detail="Only a failed simulation can be overridden.")
    expected_hash = proposal_hash(change.config_payload, change.target_devices, change.source_template)
    if expected_hash != change.proposal_hash:
        log_event(db=db, event_type="Configuration", severity="ERROR", author=current_user.username,
                  details={"action": "Proposal Integrity Failure", "change_id": change.change_id}, target_devices=[])
        raise HTTPException(status_code=409, detail="Stored proposal integrity verification failed.")
    reason = request.override_reason.strip()
    if not 10 <= len(reason) <= 1000:
        raise HTTPException(status_code=422, detail="Override reason must be between 10 and 1000 characters.")
    change.simulation_override = True
    change.simulation_override_by = current_user.username
    change.simulation_override_reason = reason
    change.simulation_override_at = datetime.now(timezone.utc)
    change.status = "admin_override_authorized"
    db.commit()
    log_event(db=db, event_type="Configuration", severity="WARNING", author=current_user.username,
              details={"action": "Simulation Failed — Admin Override Authorized", "change_id": change.change_id,
                       "proposal_hash": change.proposal_hash, "override_reason": reason,
                       "simulation_state": "failed"}, target_devices=change.target_devices)
    return {"change_id": change.change_id, "status": "admin_override_authorized",
            "message": "Admin Override Authorized — Production Push Available"}


@router.get("/configuration/active-manual-restores")
def get_active_manual_restores(
    target: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    return active_manual_restore_locks(db, target)


def _get_change_or_404(db, change_id):
    change = db.query(models.ConfigurationChange).filter(
        models.ConfigurationChange.change_id == change_id
    ).first()
    if not change:
        raise HTTPException(status_code=404, detail="Configuration change not found.")
    return change


@router.get("/configuration/changes/{change_id}")
def get_change_status(
    change_id: str, db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    change = _get_change_or_404(db, change_id)
    latest_verification = db.query(models.ConfigurationVerification).filter(
        models.ConfigurationVerification.change_id == change_id
    ).order_by(models.ConfigurationVerification.attempt_number.desc()).first()
    latest_rollback = db.query(models.ConfigurationRollback).filter(
        models.ConfigurationRollback.change_id == change_id
    ).order_by(models.ConfigurationRollback.authorized_at.desc()).first()
    integrity_bound_hosts = {
        row[0] for row in db.query(models.ConfigurationBackupArtifact.hostname).filter(
            models.ConfigurationBackupArtifact.change_id == change_id,
            models.ConfigurationBackupArtifact.artifact_type == "pre_config",
        ).all()
    }
    pre_config_artifacts = db.query(models.ConfigurationBackupArtifact).filter(
        models.ConfigurationBackupArtifact.change_id == change_id,
        models.ConfigurationBackupArtifact.artifact_type == "pre_config",
    ).all()
    lifecycle_blocker = rollback_lifecycle_blocker(db, change)
    if change.status not in ELIGIBLE_CHANGE_STATES:
        eligibility_reason = "Change is not currently rollback-eligible."
    elif integrity_bound_hosts != set(change.target_devices):
        eligibility_reason = "Integrity-bound Pre_Config artifacts are incomplete."
    else:
        eligibility_reason = lifecycle_blocker
    return {
        "change_id": change.change_id, "status": change.status,
        "targets": change.target_devices,
        "simulation_success": change.simulation_success,
        "pre_backup_success": change.pre_backup_success,
        "latest_verification": None if not latest_verification else {
            "verification_id": latest_verification.verification_id,
            "attempt_number": latest_verification.attempt_number,
            "status": latest_verification.status,
            "per_device_results": latest_verification.per_device_results,
            "error": latest_verification.error,
            "exec_actions_state_verified": False,
        },
        "rollback": {
            "eligible": eligibility_reason is None,
            "eligibility_reason": eligibility_reason,
            "authorized": bool(
                latest_rollback
                and latest_rollback.status in ACTIVE_ROLLBACK_STATES
            ),
            "rollback_id": latest_rollback.rollback_id if latest_rollback else None,
            "status": latest_rollback.status if latest_rollback else None,
            "automated_restore": False,
            "capability_reason": AUTOMATED_RESTORE_UNQUALIFIED_REASON,
            "artifacts": {
                artifact.hostname: {
                    "filename": artifact.filename,
                    "sha256": artifact.sha256,
                    "size_bytes": artifact.size_bytes,
                }
                for artifact in pre_config_artifacts
            },
            "device_contact_performed": (
                False if latest_rollback and latest_rollback.status == "manual_restore_required"
                else None
            ),
            "per_device_results": sanitize_backup_results(
                latest_rollback.per_device_results if latest_rollback else {}
            ),
            "verification_results": latest_rollback.verification_results if latest_rollback else {},
            "error": (
                "Manual restore operation failed."
                if latest_rollback and latest_rollback.error else None
            ),
        },
    }


@router.post("/configuration/changes/{change_id}/verify")
def verify_change(
    change_id: str, request: schemas.VerifyChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    change = _get_change_or_404(db, change_id)
    if change.status not in {"verified", "verification_failed", "verification_error"}:
        raise HTTPException(status_code=409, detail=f"Change cannot be verified from state '{change.status}'.")
    devices = db.query(models.NetworkDevice).filter(
        models.NetworkDevice.hostname.in_(change.target_devices)
    ).all()
    try:
        record = run_verification(
            db, change, devices, current_user.username, run_ansible_playbook,
            audit_logger=log_event,
        )
    except VerificationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "change_id": change.change_id,
        "verification_id": record.verification_id,
        "attempt_number": record.attempt_number,
        "status": record.status,
        "per_device_results": record.per_device_results,
        "error": record.error,
        "exec_actions_state_verified": False,
    }


@router.post("/configuration/changes/{change_id}/authorize-rollback")
def authorize_change_rollback(
    change_id: str, request: schemas.RollbackAuthorizationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    change = _get_change_or_404(db, change_id)
    reason = request.reason.strip()
    if not 10 <= len(reason) <= 1000:
        raise HTTPException(status_code=422, detail="Rollback reason must be between 10 and 1000 characters.")
    try:
        rollback = authorize_rollback(
            db, change, current_user.username, reason, audit_logger=log_event
        )
    except RollbackRejected as exc:
        log_event(db=db, event_type="Configuration", severity="ERROR", author=current_user.username,
                  target_devices=change.target_devices,
                  details={"action": "Rollback Authorization Rejected", "change_id": change.change_id,
                           "proposal_hash": change.proposal_hash, "reason": str(exc)})
        raise HTTPException(status_code=409, detail=str(exc))
    return {**manual_restore_handoff(db, change, rollback),
            "status": rollback.status, "message": "Manual Restore Required"}


@router.post("/configuration/changes/{change_id}/rollback")
def rollback_change(
    change_id: str, request: schemas.RollbackExecutionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    change = _get_change_or_404(db, change_id)
    rollback = db.query(models.ConfigurationRollback).filter(
        models.ConfigurationRollback.rollback_id == request.rollback_id
    ).first()
    if not rollback:
        raise HTTPException(status_code=404, detail="Rollback authorization not found.")
    try:
        rollback = execute_rollback(
            db, change, rollback, current_user.username, audit_logger=log_event
        )
    except RollbackRejected as exc:
        log_event(db=db, event_type="Configuration", severity="ERROR", author=current_user.username,
                  target_devices=change.target_devices,
                  details={"action": "Rollback Execution Rejected", "change_id": change.change_id,
                           "proposal_hash": change.proposal_hash,
                           "rollback_id": request.rollback_id, "reason": str(exc)})
        raise HTTPException(status_code=409, detail=str(exc))
    return {"change_id": change.change_id, "rollback_id": rollback.rollback_id,
            "status": rollback.status, "per_device_results": rollback.per_device_results,
            "verification_results": rollback.verification_results, "error": rollback.error}


def _get_rollback_or_404(db, change, rollback_id):
    rollback = db.query(models.ConfigurationRollback).filter(
        models.ConfigurationRollback.rollback_id == rollback_id
    ).first()
    if not rollback:
        raise HTTPException(status_code=404, detail="Rollback authorization not found.")
    if rollback.change_id != change.change_id:
        raise HTTPException(
            status_code=409,
            detail="Rollback authorization does not belong to this change.",
        )
    return rollback


@router.post("/configuration/changes/{change_id}/cancel-manual-restore")
def cancel_change_manual_restore(
    change_id: str,
    request: schemas.ManualRestoreCancellationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    change = _get_change_or_404(db, change_id)
    rollback = _get_rollback_or_404(db, change, request.rollback_id)
    reason = request.reason.strip()
    if not 10 <= len(reason) <= 1000:
        raise HTTPException(
            status_code=422,
            detail="Cancellation reason must be between 10 and 1000 characters.",
        )
    try:
        rollback = cancel_manual_restore(
            db, change, rollback, current_user.username, reason, audit_logger=log_event
        )
    except RollbackRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "change_id": change.change_id,
        "rollback_id": rollback.rollback_id,
        "status": rollback.status,
        "device_contact_performed": False,
        "device_configuration_changed": False,
    }


@router.post("/configuration/changes/{change_id}/prepare-manual-restore")
def prepare_change_manual_restore(
    change_id: str, request: schemas.ManualRestoreActionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    change = _get_change_or_404(db, change_id)
    rollback = _get_rollback_or_404(db, change, request.rollback_id)
    try:
        rollback = prepare_manual_restore(
            db, change, rollback, current_user.username, audit_logger=log_event
        )
    except RollbackRejected as exc:
        log_event(
            db=db, event_type="Configuration", severity="ERROR",
            author=current_user.username, target_devices=change.target_devices,
            details={
                "action": "Prepare Manual Restore Rejected",
                "change_id": change.change_id,
                "rollback_id": request.rollback_id,
                "reason": str(exc),
                "device_contact_performed": False,
            },
        )
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        **manual_restore_handoff(
            db, change, rollback, device_contact_performed=True
        ),
        "status": rollback.status,
        "pre_rollback_files": rollback.pre_rollback_files or {},
        "message": (
            "Manual restore is ready for the vendor-approved procedure."
            if rollback.status == "manual_restore_ready"
            else "Manual restore preparation failed; create a new rollback authorization."
        ),
    }


@router.post("/configuration/changes/{change_id}/verify-manual-restore")
def verify_change_manual_restore(
    change_id: str, request: schemas.ManualRestoreActionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    change = _get_change_or_404(db, change_id)
    rollback = _get_rollback_or_404(db, change, request.rollback_id)
    try:
        rollback = verify_manual_restore(
            db, change, rollback, current_user.username, audit_logger=log_event
        )
    except RollbackRejected as exc:
        log_event(
            db=db, event_type="Configuration", severity="ERROR",
            author=current_user.username, target_devices=change.target_devices,
            details={
                "action": "Verify Manual Restore Rejected",
                "change_id": change.change_id,
                "rollback_id": request.rollback_id,
                "reason": str(exc),
                "device_contact_performed": False,
            },
        )
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "change_id": change.change_id,
        "rollback_id": rollback.rollback_id,
        "status": rollback.status,
        "verification_results": rollback.verification_results,
        "error": rollback.error,
    }
