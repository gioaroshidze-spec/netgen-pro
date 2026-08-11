import hashlib
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

import models
from backup_service import (
    ARCHIVE_DIR,
    create_postrollback_backups,
    create_prerollback_backups,
)
from change_control import proposal_hash
from config_compare import normalize_config_for_comparison
from connection_utils import get_ansible_inventory_vars
from logger import log_event


ELIGIBLE_CHANGE_STATES = {
    "verified", "verification_failed", "verification_error", "deployment_failed"
}
ACTIVE_ROLLBACK_STATES = {
    "authorized", "capturing_pre_rollback", "rolling_back", "verifying_rollback"
}
CISCO_ROLLBACK_TEMP_FILE = "flash:vnms_rollback.cfg"
_CISCO_ROLLBACK_DIR_ENTRY_PATTERN = (
    r"(?m)^\s*\d+\s+-[rwx-]+\s+([0-9]+)\s+[^\r\n]*\s+"
    r"vnms_rollback\.cfg\s*$"
)

_RESTORE_SUMMARY_LIMIT = 4000
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
    re.DOTALL,
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r'''(?ix)
    (
        ["']?
        (?:ansible_password|encrypted_password|password|passwd|token|api[_-]?key|
           secret|private[_-]?key|authorization)
        ["']?\s*(?:=>|=|:)\s*
    )
    (?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,}\]]+)
    ''',
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


class RollbackRejected(ValueError):
    pass


def sanitize_restore_summary(summary):
    text = _ANSI_ESCAPE.sub("", str(summary or ""))
    text = _PRIVATE_KEY_BLOCK.sub("[REDACTED PRIVATE KEY]", text)
    text = _BEARER_TOKEN.sub("Bearer [REDACTED]", text)
    text = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}[REDACTED]", text
    )
    return text[-_RESTORE_SUMMARY_LIMIT:]


def persist_backup_artifacts(db, change_id, results, artifact_type, rollback_id=None):
    artifacts = []
    for result in results:
        if not result.get("success"):
            continue
        required = ("hostname", "filename", "sha256", "size_bytes")
        if any(result.get(field) in (None, "") for field in required):
            raise RollbackRejected("Backup artifact metadata is incomplete.")
        artifact = models.ConfigurationBackupArtifact(
            change_id=change_id, rollback_id=rollback_id,
            hostname=result["hostname"], artifact_type=artifact_type,
            filename=result["filename"], sha256=result["sha256"],
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
        raise RollbackRejected("Integrity-bound Pre_Config artifacts are incomplete; legacy/unhashed backups cannot be rolled back automatically.")

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
        if len(content) != artifact.size_bytes or hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise RollbackRejected(f"Pre_Config artifact integrity failed for {hostname}.")
        validated[hostname] = (artifact, path)
    return validated


def _validate_change_and_targets(db, change, archive_dir=ARCHIVE_DIR):
    if change.status not in ELIGIBLE_CHANGE_STATES:
        raise RollbackRejected(f"Change is not rollback-eligible from state '{change.status}'.")
    if proposal_hash(change.config_payload, change.target_devices, change.source_template) != change.proposal_hash:
        raise RollbackRejected("Stored proposal integrity verification failed.")
    devices = db.query(models.NetworkDevice).filter(
        models.NetworkDevice.hostname.in_(change.target_devices)
    ).all()
    if {device.hostname for device in devices} != set(change.target_devices):
        raise RollbackRejected("One or more stored target devices no longer exist.")
    unsupported = sorted(device.hostname for device in devices if (device.os_type or "cisco").lower() != "cisco")
    if unsupported:
        raise RollbackRejected(f"Automated rollback is supported only for validated Cisco IOS targets; unsupported: {', '.join(unsupported)}.")
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
        overlap = sorted(requested_targets.intersection(active_change.target_devices or []))
        if overlap:
            raise RollbackRejected(
                "Another rollback is active for overlapping target device(s): "
                + ", ".join(overlap)
                + "."
            )


def authorize_rollback(db, change, requested_by, reason, archive_dir=ARCHIVE_DIR, audit_logger=log_event):
    reason = reason.strip()
    if not 10 <= len(reason) <= 1000:
        raise RollbackRejected("Rollback reason must be between 10 and 1000 characters.")
    reject_overlapping_active_rollbacks(db, change)
    _, artifacts = _validate_change_and_targets(db, change, archive_dir)
    reject_newer_overlapping_changes(db, change)
    rollback = models.ConfigurationRollback(
        rollback_id=str(uuid.uuid4()), change_id=change.change_id,
        requested_by=requested_by, reason=reason,
        authorized_at=datetime.now(timezone.utc), status="authorized",
        per_device_results={}, verification_results={},
    )
    db.add(rollback)
    db.commit()
    audit_logger(
        db=db, event_type="Configuration", severity="WARNING", author=requested_by,
        target_devices=change.target_devices,
        details={
            "action": "Rollback Authorized", "change_id": change.change_id,
            "proposal_hash": change.proposal_hash, "rollback_id": rollback.rollback_id,
            "state_transition": "none -> authorized", "reason": reason,
            "artifacts": {host: {"filename": item[0].filename, "sha256": item[0].sha256} for host, item in artifacts.items()},
            "device_contact_performed": False,
            "out_of_band_changes_detectable": False,
        },
    )
    return rollback


def _parse_restore_recap(
    output, expected_hostnames, returncode,
    success_status="restored", failure_status="restore_failed",
):
    results = {}
    recap_index = output.rfind("PLAY RECAP")
    if recap_index >= 0:
        for line in output[recap_index:].splitlines()[1:]:
            match = re.match(r"^\s*([^\s:]+)\s*:\s*(.*?)\s*$", line)
            if not match or match.group(1) not in expected_hostnames:
                continue
            counters = {key: int(value) for key, value in re.findall(r"\b(ok|changed|unreachable|failed)=(\d+)\b", match.group(2))}
            if {"ok", "changed", "unreachable", "failed"} <= set(counters):
                results[match.group(1)] = {
                    **counters,
                    "status": success_status
                    if not counters["failed"] and not counters["unreachable"]
                    else failure_status,
                }
    for hostname in expected_hostnames:
        results.setdefault(
            hostname,
            {"status": failure_status, "error": "Missing or malformed restore recap."},
        )
    success = returncode == 0 and all(
        item["status"] == success_status for item in results.values()
    )
    return success, results


def run_cisco_restore(devices, validated_artifacts, rollback_id, subprocess_runner=subprocess.run):
    with tempfile.TemporaryDirectory() as temp_dir:
        inventory_path = os.path.join(temp_dir, "inventory.yaml")
        prepare_path = os.path.join(temp_dir, "prepare_rollback.yaml")
        replace_path = os.path.join(temp_dir, "replace_rollback.yaml")
        hosts = {}
        for device in devices:
            variables = get_ansible_inventory_vars(device)
            restore_path = validated_artifacts[device.hostname][1]
            variables["restore_file"] = str(restore_path)
            variables["restore_file_size"] = restore_path.stat().st_size
            hosts[device.hostname] = variables
        with open(inventory_path, "w", encoding="utf-8") as stream:
            yaml.safe_dump({"all": {"hosts": hosts}}, stream, sort_keys=False)
        prepare_playbook = [{
            "name": "Prepare bounded VNMS Cisco IOS rollback file",
            "hosts": "all", "gather_facts": False,
            "tasks": [
                {
                    "name": "Check for the exact VNMS rollback file",
                    "cisco.ios.ios_command": {
                        "commands": [{"command": f"dir {CISCO_ROLLBACK_TEMP_FILE}"}]
                    },
                    "register": "vnms_existing_temp",
                    "failed_when": False,
                    "changed_when": False,
                },
                {
                    "name": "Require a conclusive VNMS rollback file check",
                    "ansible.builtin.assert": {
                        "that": [
                            "vnms_existing_temp.stdout is defined",
                            "'vnms_rollback.cfg' in (vnms_existing_temp.stdout | default([]) | join('\\n')) or 'Error opening' in (vnms_existing_temp.stdout | default([]) | join('\\n')) or 'No such file' in (vnms_existing_temp.stdout | default([]) | join('\\n'))",
                        ],
                        "fail_msg": "The exact VNMS rollback file state could not be determined safely.",
                    },
                },
                {
                    "name": "Record whether the exact VNMS rollback file exists",
                    "ansible.builtin.set_fact": {
                        "vnms_temp_exists": "{{ 'vnms_rollback.cfg' in (vnms_existing_temp.stdout | default([]) | join('\\n')) and 'Error opening' not in (vnms_existing_temp.stdout | default([]) | join('\\n')) and 'No such file' not in (vnms_existing_temp.stdout | default([]) | join('\\n')) }}"
                    },
                    "changed_when": False,
                },
                {
                    "name": "Remove only the existing VNMS-owned rollback file",
                    "cisco.ios.ios_command": {
                        "commands": [
                            {"command": f"delete /force {CISCO_ROLLBACK_TEMP_FILE}"}
                        ]
                    },
                    "when": "vnms_temp_exists | bool",
                },
                {
                    "name": "Confirm the old VNMS rollback file is absent",
                    "cisco.ios.ios_command": {
                        "commands": [{"command": f"dir {CISCO_ROLLBACK_TEMP_FILE}"}]
                    },
                    "register": "vnms_after_delete",
                    "failed_when": False,
                    "changed_when": False,
                    "when": "vnms_temp_exists | bool",
                },
                {
                    "name": "Fail if the old VNMS rollback file remains",
                    "ansible.builtin.assert": {
                        "that": [
                            "'Error opening' in (vnms_after_delete.stdout | default([]) | join('\\n')) or 'No such file' in (vnms_after_delete.stdout | default([]) | join('\\n'))"
                        ],
                        "fail_msg": "The existing VNMS-owned rollback file could not be removed safely.",
                    },
                    "when": "vnms_temp_exists | bool",
                },
                {
                    "name": "Read available flash space",
                    "cisco.ios.ios_command": {
                        "commands": [{"command": "dir flash:"}]
                    },
                    "register": "vnms_flash_listing",
                    "changed_when": False,
                },
                {
                    "name": "Extract determinable free flash bytes",
                    "ansible.builtin.set_fact": {
                        "vnms_flash_free_matches": "{{ (vnms_flash_listing.stdout | default([]) | join('\\n')) | regex_findall('([0-9]+) bytes free') }}"
                    },
                    "changed_when": False,
                },
                {
                    "name": "Fail closed when flash space is determinably insufficient",
                    "ansible.builtin.fail": {
                        "msg": "Insufficient flash space for the validated VNMS rollback artifact."
                    },
                    "when": [
                        "vnms_flash_free_matches | length > 0",
                        "(vnms_flash_free_matches | first | int) < (restore_file_size | int)",
                    ],
                },
                {
                    "name": "Transfer integrity-validated Pre_Config artifact",
                    "ansible.netcommon.net_put": {
                        "src": "{{ restore_file }}",
                        "dest": CISCO_ROLLBACK_TEMP_FILE,
                        "protocol": "scp",
                        "mode": "binary",
                    },
                },
                {
                    "name": "Read back the exact transferred VNMS rollback file",
                    "cisco.ios.ios_command": {
                        "commands": [{"command": f"dir {CISCO_ROLLBACK_TEMP_FILE}"}]
                    },
                    "register": "vnms_transferred_temp",
                    "changed_when": False,
                },
                {
                    "name": "Require the exact transferred VNMS rollback file",
                    "ansible.builtin.assert": {
                        "that": [
                            "'vnms_rollback.cfg' in (vnms_transferred_temp.stdout | default([]) | join('\\n'))",
                            "'Error opening' not in (vnms_transferred_temp.stdout | default([]) | join('\\n'))",
                            "'No such file' not in (vnms_transferred_temp.stdout | default([]) | join('\\n'))",
                        ],
                        "fail_msg": "The exact transferred VNMS rollback file is not present.",
                    },
                },
                {
                    "name": "Extract the exact transferred VNMS rollback file size",
                    "ansible.builtin.set_fact": {
                        "vnms_transferred_size_matches": "{{ (vnms_transferred_temp.stdout | default([]) | join('\\n')) | regex_findall('"
                        + _CISCO_ROLLBACK_DIR_ENTRY_PATTERN
                        + "') }}"
                    },
                    "changed_when": False,
                },
                {
                    "name": "Require a uniquely parseable transferred file size",
                    "ansible.builtin.assert": {
                        "that": [
                            "vnms_transferred_size_matches | length == 1",
                        ],
                        "fail_msg": "The exact transferred VNMS rollback file size could not be determined safely.",
                    },
                },
                {
                    "name": "Require the transferred file size to match the validated artifact",
                    "ansible.builtin.assert": {
                        "that": [
                            "(vnms_transferred_size_matches | first | int) == (restore_file_size | int)",
                        ],
                        "fail_msg": "The transferred VNMS rollback file size does not match the validated artifact.",
                    },
                },
            ],
        }]
        with open(prepare_path, "w", encoding="utf-8") as stream:
            yaml.safe_dump(prepare_playbook, stream, sort_keys=False)
        prepared = subprocess_runner(
            ["ansible-playbook", "-i", inventory_path, prepare_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={**os.environ, "ANSIBLE_FORCE_COLOR": "0"},
        )
        prepare_output = prepared.stdout or ""
        prepare_success, prepare_results = _parse_restore_recap(
            prepare_output, set(hosts), prepared.returncode,
            success_status="prepared", failure_status="prepare_failed",
        )
        if not prepare_success:
            return False, prepare_results, prepare_output[-_RESTORE_SUMMARY_LIMIT:]

        replace_playbook = [{
            "name": "Apply the validated VNMS Cisco IOS rollback file",
            "hosts": "all", "gather_facts": False,
            "tasks": [{
                "name": "Replace running configuration from validated artifact",
                "cisco.ios.ios_command": {
                    "commands": [{
                        "command": f"configure replace {CISCO_ROLLBACK_TEMP_FILE} force"
                    }]
                },
            }],
        }]
        with open(replace_path, "w", encoding="utf-8") as stream:
            yaml.safe_dump(replace_playbook, stream, sort_keys=False)
        replaced = subprocess_runner(
            ["ansible-playbook", "-i", inventory_path, replace_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={**os.environ, "ANSIBLE_FORCE_COLOR": "0"},
        )
        replace_output = replaced.stdout or ""
        success, results = _parse_restore_recap(
            replace_output, set(hosts), replaced.returncode
        )
        combined_output = f"{prepare_output}\n{replace_output}"
        return success, results, combined_output[-_RESTORE_SUMMARY_LIMIT:]


def cleanup_cisco_rollback_temp(devices, subprocess_runner=subprocess.run):
    with tempfile.TemporaryDirectory() as temp_dir:
        inventory_path = os.path.join(temp_dir, "inventory.yaml")
        playbook_path = os.path.join(temp_dir, "cleanup_rollback.yaml")
        hosts = {
            device.hostname: get_ansible_inventory_vars(device) for device in devices
        }
        with open(inventory_path, "w", encoding="utf-8") as stream:
            yaml.safe_dump({"all": {"hosts": hosts}}, stream, sort_keys=False)
        playbook = [{
            "name": "Clean up bounded VNMS Cisco IOS rollback file",
            "hosts": "all", "gather_facts": False,
            "tasks": [
                {
                    "name": "Check for the exact VNMS rollback file after verification",
                    "cisco.ios.ios_command": {
                        "commands": [{"command": f"dir {CISCO_ROLLBACK_TEMP_FILE}"}]
                    },
                    "register": "vnms_cleanup_existing",
                    "failed_when": False,
                    "changed_when": False,
                },
                {
                    "name": "Require a conclusive post-verification file check",
                    "ansible.builtin.assert": {
                        "that": [
                            "vnms_cleanup_existing.stdout is defined",
                            "'vnms_rollback.cfg' in (vnms_cleanup_existing.stdout | default([]) | join('\\n')) or 'Error opening' in (vnms_cleanup_existing.stdout | default([]) | join('\\n')) or 'No such file' in (vnms_cleanup_existing.stdout | default([]) | join('\\n'))",
                        ],
                        "fail_msg": "The exact VNMS rollback file state could not be determined safely after verification.",
                    },
                },
                {
                    "name": "Record whether the verified VNMS rollback file exists",
                    "ansible.builtin.set_fact": {
                        "vnms_cleanup_exists": "{{ 'vnms_rollback.cfg' in (vnms_cleanup_existing.stdout | default([]) | join('\\n')) and 'Error opening' not in (vnms_cleanup_existing.stdout | default([]) | join('\\n')) and 'No such file' not in (vnms_cleanup_existing.stdout | default([]) | join('\\n')) }}"
                    },
                    "changed_when": False,
                },
                {
                    "name": "Delete only the verified VNMS-owned rollback file",
                    "cisco.ios.ios_command": {
                        "commands": [
                            {"command": f"delete /force {CISCO_ROLLBACK_TEMP_FILE}"}
                        ]
                    },
                    "when": "vnms_cleanup_exists | bool",
                },
                {
                    "name": "Confirm the VNMS rollback file was removed",
                    "cisco.ios.ios_command": {
                        "commands": [{"command": f"dir {CISCO_ROLLBACK_TEMP_FILE}"}]
                    },
                    "register": "vnms_cleanup_after",
                    "failed_when": False,
                    "changed_when": False,
                },
                {
                    "name": "Require the VNMS rollback file to be absent",
                    "ansible.builtin.assert": {
                        "that": [
                            "'Error opening' in (vnms_cleanup_after.stdout | default([]) | join('\\n')) or 'No such file' in (vnms_cleanup_after.stdout | default([]) | join('\\n'))"
                        ],
                        "fail_msg": "The VNMS-owned rollback file could not be removed after verification.",
                    },
                },
            ],
        }]
        with open(playbook_path, "w", encoding="utf-8") as stream:
            yaml.safe_dump(playbook, stream, sort_keys=False)
        completed = subprocess_runner(
            ["ansible-playbook", "-i", inventory_path, playbook_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={**os.environ, "ANSIBLE_FORCE_COLOR": "0"},
        )
        output = completed.stdout or ""
        success, results = _parse_restore_recap(
            output, set(hosts), completed.returncode,
            success_status="cleaned", failure_status="cleanup_failed",
        )
        return success, results, output[-_RESTORE_SUMMARY_LIMIT:]


def execute_rollback(db, change, rollback, requested_by, archive_dir=ARCHIVE_DIR,
                     backup_runner=create_prerollback_backups,
                     post_backup_runner=create_postrollback_backups,
                     restore_runner=run_cisco_restore,
                     cleanup_runner=cleanup_cisco_rollback_temp,
                     audit_logger=log_event):
    if rollback.change_id != change.change_id or rollback.status != "authorized":
        raise RollbackRejected("Rollback authorization is invalid, active, or has already been used.")
    devices, artifacts = _validate_change_and_targets(db, change, archive_dir)
    reject_newer_overlapping_changes(db, change)
    reject_overlapping_active_rollbacks(
        db, change, exclude_rollback_id=rollback.rollback_id
    )
    started_at = datetime.now(timezone.utc)
    claimed = db.query(models.ConfigurationRollback).filter(
        models.ConfigurationRollback.id == rollback.id,
        models.ConfigurationRollback.status == "authorized",
    ).update(
        {
            models.ConfigurationRollback.status: "capturing_pre_rollback",
            models.ConfigurationRollback.started_at: started_at,
        },
        synchronize_session=False,
    )
    db.commit()
    if claimed != 1:
        raise RollbackRejected("Rollback authorization is active or has already been used.")
    db.refresh(rollback)

    try:
        files, backup_results = backup_runner(devices, archive_dir=archive_dir)
    except Exception as exc:
        rollback.status = "pre_rollback_failed"
        rollback.error = f"Mandatory Pre_Rollback capture failed: {exc}"
        rollback.completed_at = datetime.now(timezone.utc)
        db.commit()
        audit_logger(
            db=db, event_type="Configuration", severity="ERROR", author=requested_by,
            target_devices=change.target_devices,
            details={
                "action": "Pre_Rollback Backup Failed", "change_id": change.change_id,
                "proposal_hash": change.proposal_hash, "rollback_id": rollback.rollback_id,
                "state_transition": "capturing_pre_rollback -> pre_rollback_failed",
                "error": str(exc),
            },
        )
        return rollback
    try:
        persist_backup_artifacts(
            db, change.change_id, backup_results, "pre_rollback", rollback.rollback_id
        )
    except Exception as exc:
        db.rollback()
        db.refresh(rollback)
        rollback.status = "pre_rollback_failed"
        rollback.error = f"Pre_Rollback artifact metadata persistence failed: {exc}"
        rollback.completed_at = datetime.now(timezone.utc)
        db.commit()
        audit_logger(
            db=db, event_type="Configuration", severity="ERROR", author=requested_by,
            target_devices=change.target_devices,
            details={
                "action": "Pre_Rollback Artifact Persistence Failed",
                "change_id": change.change_id, "proposal_hash": change.proposal_hash,
                "rollback_id": rollback.rollback_id,
                "state_transition": "capturing_pre_rollback -> pre_rollback_failed",
                "error": str(exc),
            },
        )
        return rollback
    rollback.pre_rollback_files = files
    failures = [result for result in backup_results if not result.get("success")]
    if failures or set(files) != set(change.target_devices):
        rollback.status = "pre_rollback_failed"
        rollback.per_device_results = {result["hostname"]: result for result in backup_results}
        rollback.error = "Mandatory Pre_Rollback capture failed; no restore was attempted."
        rollback.completed_at = datetime.now(timezone.utc)
        db.commit()
        audit_logger(db=db, event_type="Configuration", severity="ERROR", author=requested_by,
                     target_devices=change.target_devices,
                     details={"action": "Pre_Rollback Backup Failed", "change_id": change.change_id,
                              "proposal_hash": change.proposal_hash, "rollback_id": rollback.rollback_id,
                              "state_transition": "capturing_pre_rollback -> pre_rollback_failed",
                              "per_device_results": rollback.per_device_results})
        return rollback

    audit_logger(db=db, event_type="Configuration", severity="SUCCESS", author=requested_by,
                 target_devices=change.target_devices,
                 details={"action": "Pre_Rollback Backup Complete", "change_id": change.change_id,
                          "proposal_hash": change.proposal_hash, "rollback_id": rollback.rollback_id,
                          "filenames": files,
                          "artifact_hashes": {r["hostname"]: r["sha256"] for r in backup_results}})
    artifacts = validate_preconfig_artifacts(db, change, archive_dir)
    rollback.status = "rolling_back"
    db.commit()
    audit_logger(db=db, event_type="Configuration", severity="WARNING", author=requested_by,
                 target_devices=change.target_devices,
                 details={"action": "Cisco IOS Rollback Started", "change_id": change.change_id,
                          "proposal_hash": change.proposal_hash, "rollback_id": rollback.rollback_id,
                          "state_transition": "capturing_pre_rollback -> rolling_back"})
    try:
        restore_success, restore_results, _restore_summary = restore_runner(devices, artifacts, rollback.rollback_id)
    except Exception as exc:
        restore_success, restore_results, _restore_summary = False, {}, str(exc)
    rollback.per_device_results = restore_results
    if not restore_success:
        sanitized_restore_summary = sanitize_restore_summary(_restore_summary)
        rollback.status = "rollback_failed"
        rollback.error = sanitized_restore_summary or (
            "Cisco IOS restore execution failed without a diagnostic summary."
        )
        rollback.completed_at = datetime.now(timezone.utc)
        db.commit()
        audit_logger(db=db, event_type="Configuration", severity="ERROR", author=requested_by,
                     target_devices=change.target_devices,
                     details={"action": "Cisco IOS Rollback Failed", "change_id": change.change_id,
                              "proposal_hash": change.proposal_hash, "rollback_id": rollback.rollback_id,
                              "state_transition": "rolling_back -> rollback_failed",
                              "per_device_results": restore_results,
                              "restore_summary": rollback.error})
        return rollback

    rollback.status = "verifying_rollback"
    db.commit()
    try:
        _, post_results = post_backup_runner(devices, archive_dir=archive_dir)
    except Exception as exc:
        rollback.status = "rollback_verification_failed"
        rollback.error = f"Post_Rollback capture failed: {exc}"
        rollback.completed_at = datetime.now(timezone.utc)
        db.commit()
        audit_logger(
            db=db, event_type="Configuration", severity="ERROR", author=requested_by,
            target_devices=change.target_devices,
            details={
                "action": "Rollback Post-Verification Capture Failed",
                "change_id": change.change_id, "proposal_hash": change.proposal_hash,
                "rollback_id": rollback.rollback_id,
                "state_transition": "verifying_rollback -> rollback_verification_failed",
                "error": str(exc),
            },
        )
        return rollback
    try:
        persist_backup_artifacts(
            db, change.change_id, post_results, "post_rollback", rollback.rollback_id
        )
    except Exception as exc:
        db.rollback()
        db.refresh(rollback)
        rollback.status = "rollback_verification_failed"
        rollback.error = f"Post_Rollback artifact metadata persistence failed: {exc}"
        rollback.completed_at = datetime.now(timezone.utc)
        db.commit()
        audit_logger(
            db=db, event_type="Configuration", severity="ERROR", author=requested_by,
            target_devices=change.target_devices,
            details={
                "action": "Rollback Post-Verification Artifact Persistence Failed",
                "change_id": change.change_id, "proposal_hash": change.proposal_hash,
                "rollback_id": rollback.rollback_id,
                "state_transition": "verifying_rollback -> rollback_verification_failed",
                "error": str(exc),
            },
        )
        return rollback
    verification = {}
    post_by_host = {result["hostname"]: result for result in post_results}
    for hostname in change.target_devices:
        post = post_by_host.get(hostname)
        if not post or not post.get("success"):
            verification[hostname] = {"status": "verification_error", "error": (post or {}).get("error", "Post_Rollback capture missing.")}
            continue
        try:
            original = artifacts[hostname][1].read_text(encoding="utf-8")
            current = _safe_artifact_path(post["filename"], archive_dir).read_text(encoding="utf-8")
            matches = normalize_config_for_comparison(original) == normalize_config_for_comparison(current)
            verification[hostname] = {
                "status": "matched" if matches else "different",
                "matches_pre_config": matches,
                "post_rollback_filename": post["filename"],
                "post_rollback_sha256": post["sha256"],
            }
        except Exception as exc:
            verification[hostname] = {
                "status": "verification_error", "error": str(exc)
            }
    rollback.verification_results = verification
    matched = all(result.get("matches_pre_config") is True for result in verification.values())
    cleanup_success = None
    cleanup_results = {}
    cleanup_summary = ""
    if matched:
        try:
            cleanup_success, cleanup_results, cleanup_summary = cleanup_runner(devices)
        except Exception as exc:
            cleanup_success, cleanup_results, cleanup_summary = False, {}, str(exc)
        combined_results = {}
        for hostname in change.target_devices:
            combined_results[hostname] = {
                **(restore_results.get(hostname) or {}),
                "temporary_file_cleanup": cleanup_results.get(
                    hostname,
                    {"status": "cleanup_failed", "error": "Missing cleanup result."},
                ),
            }
        rollback.per_device_results = combined_results

    rollback.status = "rolled_back" if matched else "rollback_verification_failed"
    rollback.completed_at = datetime.now(timezone.utc)
    if not matched:
        rollback.error = "Post-rollback configuration does not exactly match the normalized Pre_Config artifact."
    elif cleanup_success:
        rollback.error = None
    else:
        rollback.error = sanitize_restore_summary(cleanup_summary) or (
            "Rollback verified, but the VNMS-owned temporary rollback file cleanup failed."
        )
    db.commit()
    audit_logger(db=db, event_type="Configuration", severity="WARNING" if matched and cleanup_success else "ERROR", author=requested_by,
                 target_devices=change.target_devices,
                 details={"action": "Cisco IOS Rollback Post-Verification", "change_id": change.change_id,
                          "proposal_hash": change.proposal_hash, "rollback_id": rollback.rollback_id,
                          "state_transition": f"verifying_rollback -> {rollback.status}",
                          "per_device_results": verification,
                          "temporary_file_cleanup": cleanup_results,
                          "temporary_file_retained": matched and not cleanup_success,
                          "cleanup_summary": rollback.error if matched and not cleanup_success else None})
    return rollback
