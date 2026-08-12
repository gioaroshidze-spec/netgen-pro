import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import models
from backup_service import (
    ARCHIVE_DIR,
    create_postrollback_backups,
    create_prerollback_backups,
)
from change_control import proposal_hash
from config_compare import normalize_config_for_comparison
from device_capabilities import (
    AUTOMATED_RESTORE_UNQUALIFIED_REASON,
    capabilities_by_hostname,
)
from logger import log_event


ELIGIBLE_CHANGE_STATES = {
    "verified", "verification_failed", "verification_error", "deployment_failed"
}
ACTIVE_ROLLBACK_STATES = {
    "manual_restore_required",
    "capturing_pre_rollback",
    "manual_restore_ready",
    "verifying_manual_restore",
}
TERMINAL_ROLLBACK_FAILURE_STATES = {
    "manual_restore_prepare_failed",
    "manual_restore_verification_failed",
    "manual_restore_verification_error",
}
SUCCESSFUL_ROLLBACK_STATES = {"manual_restore_verified"}


class RollbackRejected(ValueError):
    pass


def sanitize_backup_result(result):
    """Project a capture result to validated, non-secret artifact metadata."""
    if not isinstance(result, dict):
        return {"hostname": "unknown", "success": False, "error": "Backup capture failed."}
    hostname = result.get("hostname")
    if not isinstance(hostname, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,255}", hostname):
        hostname = "unknown"
    projected = {
        "hostname": hostname,
        "success": result.get("success") is True,
    }
    filename = result.get("filename")
    if (
        isinstance(filename, str)
        and len(filename) <= 255
        and filename == os.path.basename(filename)
    ):
        projected["filename"] = filename
    sha256 = result.get("sha256")
    if isinstance(sha256, str) and re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        projected["sha256"] = sha256.lower()
    size_bytes = result.get("size_bytes")
    if isinstance(size_bytes, int) and not isinstance(size_bytes, bool) and size_bytes >= 0:
        projected["size_bytes"] = size_bytes
    status = result.get("status")
    if status in {"success", "failed", "error", "timeout"}:
        projected["status"] = status
    if result.get("error"):
        projected["error"] = "Backup capture failed."
    return projected


def sanitize_backup_results(results):
    """Return hostname-keyed safe metadata without configuration content."""
    values = results.values() if isinstance(results, dict) else (results or [])
    projected = {}
    for result in values:
        safe = sanitize_backup_result(result)
        projected[safe["hostname"]] = safe
    return projected


def rollback_lifecycle_blocker(db, change):
    """Return the lifecycle reason that prevents a fresh authorization, if any."""
    verified = db.query(models.ConfigurationRollback).filter(
        models.ConfigurationRollback.change_id == change.change_id,
        models.ConfigurationRollback.status.in_(SUCCESSFUL_ROLLBACK_STATES),
    ).first()
    if verified:
        return (
            "A successfully verified manual restore already completed for this "
            "change; a new rollback authorization is prohibited."
        )
    try:
        reject_overlapping_active_rollbacks(db, change)
    except RollbackRejected as exc:
        return str(exc)
    return None


def persist_backup_artifacts(db, change_id, results, artifact_type, rollback_id=None):
    artifacts = []
    for result in results:
        if not result.get("success"):
            continue
        required = ("hostname", "filename", "sha256", "size_bytes")
        if any(result.get(field) in (None, "") for field in required):
            raise RollbackRejected("Backup artifact metadata is incomplete.")
        artifact = models.ConfigurationBackupArtifact(
            change_id=change_id,
            rollback_id=rollback_id,
            hostname=result["hostname"],
            artifact_type=artifact_type,
            filename=result["filename"],
            sha256=result["sha256"],
            size_bytes=result["size_bytes"],
        )
        db.add(artifact)
        artifacts.append(artifact)
    db.commit()
    return artifacts


def _safe_artifact_path(filename, archive_dir=ARCHIVE_DIR):
    if not filename or filename != os.path.basename(filename):
        raise RollbackRejected("Backup artifact path is unsafe.")
    root = Path(archive_dir).resolve()
    path = (root / filename).resolve()
    if path.parent != root:
        raise RollbackRejected("Backup artifact is outside the configured archive directory.")
    if not path.is_file():
        raise RollbackRejected(f"Backup artifact is missing: {filename}")
    return path


def validate_preconfig_artifacts(db, change, archive_dir=ARCHIVE_DIR):
    artifacts = db.query(models.ConfigurationBackupArtifact).filter(
        models.ConfigurationBackupArtifact.change_id == change.change_id,
        models.ConfigurationBackupArtifact.artifact_type == "pre_config",
    ).all()
    by_hostname = {}
    for artifact in artifacts:
        if artifact.hostname in by_hostname:
            raise RollbackRejected(f"Duplicate Pre_Config artifact for {artifact.hostname}.")
        by_hostname[artifact.hostname] = artifact
    if set(by_hostname) != set(change.target_devices):
        raise RollbackRejected(
            "Integrity-bound Pre_Config artifacts are incomplete; "
            "legacy/unhashed backups cannot be rolled back."
        )

    validated = {}
    for hostname in change.target_devices:
        artifact = by_hostname[hostname]
        if change.pre_backup_files.get(hostname) != artifact.filename:
            raise RollbackRejected(f"Pre_Config filename binding failed for {hostname}.")
        path = _safe_artifact_path(artifact.filename, archive_dir)
        if not re.search(
            rf"^Pre_Config_.*_{re.escape(hostname)}_\d{{8}}_\d{{6}}\.txt$",
            artifact.filename,
        ):
            raise RollbackRejected(
                f"Pre_Config hostname-to-filename binding failed for {hostname}."
            )
        content = path.read_bytes()
        if (
            len(content) != artifact.size_bytes
            or hashlib.sha256(content).hexdigest() != artifact.sha256
        ):
            raise RollbackRejected(f"Pre_Config artifact integrity failed for {hostname}.")
        validated[hostname] = (artifact, path)
    return validated


def _validate_change_and_targets(db, change, archive_dir=ARCHIVE_DIR):
    if change.status not in ELIGIBLE_CHANGE_STATES:
        raise RollbackRejected(
            f"Change is not rollback-eligible from state '{change.status}'."
        )
    if (
        proposal_hash(
            change.config_payload, change.target_devices, change.source_template
        )
        != change.proposal_hash
    ):
        raise RollbackRejected("Stored proposal integrity verification failed.")
    devices = db.query(models.NetworkDevice).filter(
        models.NetworkDevice.hostname.in_(change.target_devices)
    ).all()
    if {device.hostname for device in devices} != set(change.target_devices):
        raise RollbackRejected("One or more stored target devices no longer exist.")
    return devices, validate_preconfig_artifacts(db, change, archive_dir)


def _started_production_at(change):
    return change.pre_backup_completed_at or change.deployed_at


def _comparable_timestamp(value):
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def reject_newer_overlapping_changes(db, change):
    baseline = _started_production_at(change)
    if baseline is None:
        return
    candidates = db.query(models.ConfigurationChange).filter(
        models.ConfigurationChange.id != change.id,
        models.ConfigurationChange.pre_backup_completed_at != None,  # noqa: E711
    ).all()
    targets = set(change.target_devices)
    for candidate in candidates:
        if candidate.status in {"awaiting_pre_backup", "pre_backup_failed"}:
            continue
        started = _started_production_at(candidate)
        if (
            started
            and _comparable_timestamp(started) > _comparable_timestamp(baseline)
            and targets.intersection(candidate.target_devices or [])
        ):
            raise RollbackRejected(
                f"Newer VNMS production change {candidate.change_id} overlaps this target set."
            )


def reject_overlapping_active_rollbacks(db, change, exclude_rollback_id=None):
    query = db.query(models.ConfigurationRollback).filter(
        models.ConfigurationRollback.status.in_(ACTIVE_ROLLBACK_STATES)
    )
    if exclude_rollback_id is not None:
        query = query.filter(
            models.ConfigurationRollback.rollback_id != exclude_rollback_id
        )
    active_rollbacks = query.all()
    if not active_rollbacks:
        return

    active_change_ids = {item.change_id for item in active_rollbacks}
    active_changes = db.query(models.ConfigurationChange).filter(
        models.ConfigurationChange.change_id.in_(active_change_ids)
    ).all()
    changes_by_id = {item.change_id: item for item in active_changes}
    requested_targets = set(change.target_devices or [])
    for active in active_rollbacks:
        active_change = changes_by_id.get(active.change_id)
        if active_change is None:
            continue
        overlap = sorted(
            requested_targets.intersection(active_change.target_devices or [])
        )
        if overlap:
            raise RollbackRejected(
                "Another rollback is active for overlapping target device(s): "
                + ", ".join(overlap)
                + "."
            )


def _artifact_metadata(artifacts):
    return {
        hostname: {
            "filename": artifact.filename,
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
        }
        for hostname, (artifact, _path) in artifacts.items()
    }


def manual_restore_handoff(
    db, change, rollback, archive_dir=ARCHIVE_DIR, device_contact_performed=False
):
    devices, artifacts = _validate_change_and_targets(db, change, archive_dir)
    return {
        "rollback_id": rollback.rollback_id,
        "change_id": change.change_id,
        "target_hostnames": list(change.target_devices),
        "artifacts": _artifact_metadata(artifacts),
        "reason": rollback.reason,
        "automated_restore": False,
        "capability_reason": AUTOMATED_RESTORE_UNQUALIFIED_REASON,
        "device_capabilities": capabilities_by_hostname(devices),
        "device_contact_performed": device_contact_performed,
    }


def authorize_rollback(
    db,
    change,
    requested_by,
    reason,
    archive_dir=ARCHIVE_DIR,
    audit_logger=log_event,
):
    reason = reason.strip()
    if not 10 <= len(reason) <= 1000:
        raise RollbackRejected(
            "Rollback reason must be between 10 and 1000 characters."
        )
    lifecycle_blocker = rollback_lifecycle_blocker(db, change)
    if lifecycle_blocker:
        raise RollbackRejected(lifecycle_blocker)
    devices, artifacts = _validate_change_and_targets(db, change, archive_dir)
    reject_newer_overlapping_changes(db, change)
    rollback = models.ConfigurationRollback(
        rollback_id=str(uuid.uuid4()),
        change_id=change.change_id,
        requested_by=requested_by,
        reason=reason,
        authorized_at=datetime.now(timezone.utc),
        status="manual_restore_required",
        per_device_results={},
        verification_results={},
    )
    db.add(rollback)
    db.commit()
    handoff = {
        "rollback_id": rollback.rollback_id,
        "change_id": change.change_id,
        "target_hostnames": list(change.target_devices),
        "artifacts": _artifact_metadata(artifacts),
        "reason": reason,
        "automated_restore": False,
        "capability_reason": AUTOMATED_RESTORE_UNQUALIFIED_REASON,
        "device_capabilities": capabilities_by_hostname(devices),
        "device_contact_performed": False,
    }
    audit_logger(
        db=db,
        event_type="Configuration",
        severity="WARNING",
        author=requested_by,
        target_devices=change.target_devices,
        details={
            "action": "Manual Restore Required",
            "proposal_hash": change.proposal_hash,
            "state_transition": "none -> manual_restore_required",
            **handoff,
        },
    )
    return rollback


def _record_prepare_failure(
    db, change, rollback, requested_by, error, results, audit_logger
):
    safe_results = sanitize_backup_results(results)
    rollback.status = "manual_restore_prepare_failed"
    rollback.error = str(error)
    rollback.per_device_results = safe_results
    rollback.completed_at = datetime.now(timezone.utc)
    db.commit()
    audit_logger(
        db=db,
        event_type="Configuration",
        severity="ERROR",
        author=requested_by,
        target_devices=change.target_devices,
        details={
            "action": "Prepare Manual Restore Failed",
            "change_id": change.change_id,
            "rollback_id": rollback.rollback_id,
            "state_transition": (
                "capturing_pre_rollback -> manual_restore_prepare_failed"
            ),
            "error": str(error),
            "per_device_results": safe_results,
            "device_contact_performed": True,
            "device_configuration_changed": False,
        },
    )
    return rollback


def prepare_manual_restore(
    db,
    change,
    rollback,
    requested_by,
    archive_dir=ARCHIVE_DIR,
    backup_runner=create_prerollback_backups,
    audit_logger=log_event,
):
    if rollback.change_id != change.change_id:
        raise RollbackRejected("Rollback authorization does not belong to this change.")
    devices, _artifacts = _validate_change_and_targets(db, change, archive_dir)
    reject_newer_overlapping_changes(db, change)
    reject_overlapping_active_rollbacks(
        db, change, exclude_rollback_id=rollback.rollback_id
    )
    started_at = datetime.now(timezone.utc)
    claimed = db.query(models.ConfigurationRollback).filter(
        models.ConfigurationRollback.id == rollback.id,
        models.ConfigurationRollback.status == "manual_restore_required",
    ).update(
        {
            models.ConfigurationRollback.status: "capturing_pre_rollback",
            models.ConfigurationRollback.started_at: started_at,
        },
        synchronize_session=False,
    )
    db.commit()
    if claimed != 1:
        raise RollbackRejected(
            "Prepare Manual Restore is single-use and is not valid from the current state."
        )
    db.refresh(rollback)

    try:
        files, backup_results = backup_runner(devices, archive_dir=archive_dir)
    except Exception:
        return _record_prepare_failure(
            db, change, rollback, requested_by,
            "Mandatory Pre_Rollback capture failed.", {}, audit_logger,
        )

    try:
        persist_backup_artifacts(
            db,
            change.change_id,
            backup_results,
            "pre_rollback",
            rollback.rollback_id,
        )
    except Exception:
        db.rollback()
        db.refresh(rollback)
        return _record_prepare_failure(
            db, change, rollback, requested_by,
            "Pre_Rollback artifact metadata persistence failed.",
            {item.get("hostname", "unknown"): item for item in backup_results},
            audit_logger,
        )

    results_by_host = sanitize_backup_results(backup_results)
    failures = [item for item in backup_results if not item.get("success")]
    if failures or set(files) != set(change.target_devices):
        rollback.pre_rollback_files = files
        return _record_prepare_failure(
            db, change, rollback, requested_by,
            "Mandatory Pre_Rollback capture failed; manual restore is not ready.",
            results_by_host,
            audit_logger,
        )

    rollback.pre_rollback_files = files
    rollback.per_device_results = results_by_host
    rollback.status = "manual_restore_ready"
    rollback.error = None
    db.commit()
    handoff = manual_restore_handoff(
        db, change, rollback, archive_dir, device_contact_performed=True
    )
    audit_logger(
        db=db,
        event_type="Configuration",
        severity="WARNING",
        author=requested_by,
        target_devices=change.target_devices,
        details={
            "action": "Manual Restore Prepared",
            "proposal_hash": change.proposal_hash,
            "state_transition": "capturing_pre_rollback -> manual_restore_ready",
            "pre_rollback_artifacts": {
                item["hostname"]: {
                    "filename": item["filename"],
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in backup_results
                if item.get("success")
            },
            **handoff,
        },
    )
    return rollback


def verify_manual_restore(
    db,
    change,
    rollback,
    requested_by,
    archive_dir=ARCHIVE_DIR,
    post_backup_runner=create_postrollback_backups,
    audit_logger=log_event,
):
    if rollback.change_id != change.change_id:
        raise RollbackRejected("Rollback authorization does not belong to this change.")
    devices, artifacts = _validate_change_and_targets(db, change, archive_dir)
    claimed = db.query(models.ConfigurationRollback).filter(
        models.ConfigurationRollback.id == rollback.id,
        models.ConfigurationRollback.status == "manual_restore_ready",
    ).update(
        {models.ConfigurationRollback.status: "verifying_manual_restore"},
        synchronize_session=False,
    )
    db.commit()
    if claimed != 1:
        raise RollbackRejected(
            "Verify Manual Restore is valid only once after manual_restore_ready."
        )
    db.refresh(rollback)

    try:
        _files, post_results = post_backup_runner(devices, archive_dir=archive_dir)
    except Exception:
        post_results = []
        capture_error = "Post_Rollback capture failed."
    else:
        capture_error = None

    if capture_error is None:
        try:
            persist_backup_artifacts(
                db,
                change.change_id,
                post_results,
                "post_rollback",
                rollback.rollback_id,
            )
        except Exception:
            db.rollback()
            db.refresh(rollback)
            capture_error = "Post_Rollback artifact metadata persistence failed."

    verification = {}
    post_by_host = {
        result.get("hostname"): result
        for result in post_results
        if result.get("hostname")
    }
    safe_post_by_host = sanitize_backup_results(post_results)
    for hostname in change.target_devices:
        post = post_by_host.get(hostname)
        if capture_error or not post or not post.get("success"):
            verification[hostname] = {
                "status": "verification_error",
                "error": capture_error or "Post_Rollback capture failed.",
            }
            continue
        try:
            original = artifacts[hostname][1].read_text(encoding="utf-8")
            current = _safe_artifact_path(
                post["filename"], archive_dir
            ).read_text(encoding="utf-8")
            matches = normalize_config_for_comparison(
                original
            ) == normalize_config_for_comparison(current)
            verification[hostname] = {
                "status": "matched" if matches else "different",
                "matches_pre_config": matches,
                "post_rollback_filename": post["filename"],
                "post_rollback_sha256": post["sha256"],
            }
        except Exception:
            verification[hostname] = {
                "status": "verification_error",
                "error": "Post_Rollback comparison failed.",
            }

    has_error = any(
        item.get("status") == "verification_error"
        for item in verification.values()
    )
    matched = bool(verification) and all(
        item.get("matches_pre_config") is True
        for item in verification.values()
    )
    if matched:
        status = "manual_restore_verified"
        error = None
    elif has_error:
        status = "manual_restore_verification_error"
        error = "Manual restore verification could not be completed reliably."
    else:
        status = "manual_restore_verification_failed"
        error = (
            "Post_Rollback configuration does not exactly match the normalized "
            "Pre_Config artifact."
        )

    rollback.verification_results = verification
    rollback.per_device_results = safe_post_by_host
    rollback.status = status
    rollback.error = error
    rollback.completed_at = datetime.now(timezone.utc)
    db.commit()
    audit_logger(
        db=db,
        event_type="Configuration",
        severity="SUCCESS" if matched else "ERROR",
        author=requested_by,
        target_devices=change.target_devices,
        details={
            "action": "Manual Restore Verification",
            "change_id": change.change_id,
            "proposal_hash": change.proposal_hash,
            "rollback_id": rollback.rollback_id,
            "state_transition": f"verifying_manual_restore -> {status}",
            "per_device_results": verification,
            "device_contact_performed": True,
            "device_configuration_changed": False,
        },
    )
    return rollback


def execute_rollback(
    db,
    change,
    rollback,
    requested_by,
    archive_dir=ARCHIVE_DIR,
    audit_logger=log_event,
):
    """Fail closed; no current inventory profile qualifies for automated restore."""
    if rollback.change_id != change.change_id:
        raise RollbackRejected("Rollback authorization does not belong to this change.")
    _validate_change_and_targets(db, change, archive_dir)
    raise RollbackRejected(
        "Automated restore is unsupported for this capability profile. "
        + AUTOMATED_RESTORE_UNQUALIFIED_REASON
    )
