import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func

import models
from change_control import proposal_hash
from logger import log_event


_RECAP_LINE = re.compile(r"^\s*([^\s:]+)\s*:\s*(.*?)\s*$")
_COUNTER = re.compile(r"\b(ok|changed|unreachable|failed)=(\d+)\b", re.IGNORECASE)
_SUPPORTED_VERIFICATION_OS_TYPES = {"cisco"}


class VerificationConflict(ValueError):
    pass


def _target_errors(hostnames, message):
    return {
        hostname: {"status": "verification_error", "error": message}
        for hostname in hostnames
    }


def parse_verification_output(output, expected_hostnames):
    clean = output.replace("data: ", "").replace("\r\n", "\n")
    recap_index = clean.rfind("PLAY RECAP")
    results = {}
    errors = []
    if recap_index < 0:
        errors.append("PLAY RECAP is missing.")
    else:
        recap = clean[recap_index:].splitlines()[1:]
        for line in recap:
            if line.startswith(("PLAYBOOK COMPLETE:", "PLAYBOOK FINISHED")):
                break
            match = _RECAP_LINE.match(line)
            if not match:
                continue
            hostname, counters_text = match.groups()
            if hostname not in expected_hostnames:
                continue
            if hostname in results:
                errors.append(f"Duplicate recap entry for {hostname}.")
                continue
            counters = {name.casefold(): int(value) for name, value in _COUNTER.findall(counters_text)}
            missing = {"ok", "changed", "unreachable", "failed"} - set(counters)
            if missing:
                errors.append(f"Recap entry for {hostname} is missing counters: {', '.join(sorted(missing))}.")
                continue
            if counters["unreachable"] or counters["failed"]:
                target_status = "verification_error"
            elif counters["changed"]:
                target_status = "verification_failed"
            else:
                target_status = "verified"
            results[hostname] = {"status": target_status, **counters}

    missing_hosts = sorted(set(expected_hostnames) - set(results))
    if missing_hosts:
        errors.append(f"Expected targets missing from recap: {', '.join(missing_hosts)}.")
        for hostname in missing_hosts:
            results[hostname] = {"status": "verification_error", "error": "Missing or malformed recap entry."}

    if "PLAYBOOK COMPLETE: No errors detected." not in clean:
        errors.append("Ansible did not emit a successful completion marker.")
    if re.search(r"(^|\n)\s*(fatal:|\[ERROR\]|PLAYBOOK FINISHED WITH ERRORS)", clean, re.IGNORECASE):
        errors.append("Ansible emitted a fatal or error condition.")

    statuses = {item["status"] for item in results.values()}
    if errors or "verification_error" in statuses:
        status = "verification_error"
    elif "verification_failed" in statuses:
        status = "verification_failed"
    else:
        status = "verified"
    summary = clean[recap_index if recap_index >= 0 else max(0, len(clean) - 4000):].strip()[-4000:]
    return status, results, " ".join(errors) or None, summary


def run_verification(db, change, devices, requested_by, runner, audit_logger=log_event):
    active = db.query(models.ConfigurationVerification).filter(
        models.ConfigurationVerification.change_id == change.change_id,
        models.ConfigurationVerification.status == "verifying",
    ).first()
    if active:
        raise VerificationConflict("A verification attempt is already active for this change.")

    if change.status != "verifying":
        claimed = db.query(models.ConfigurationChange).filter(
            models.ConfigurationChange.id == change.id,
            models.ConfigurationChange.status.in_([
                "verified", "verification_failed", "verification_error"
            ]),
        ).update(
            {models.ConfigurationChange.status: "verifying"},
            synchronize_session=False,
        )
        db.commit()
        if claimed != 1:
            raise VerificationConflict(
                "A verification attempt is already active or the change is no longer eligible."
            )
        db.refresh(change)

    attempt = (db.query(func.max(models.ConfigurationVerification.attempt_number)).filter(
        models.ConfigurationVerification.change_id == change.change_id
    ).scalar() or 0) + 1
    now = datetime.now(timezone.utc)
    record = models.ConfigurationVerification(
        verification_id=str(uuid.uuid4()), change_id=change.change_id,
        attempt_number=attempt, requested_by=requested_by, started_at=now,
        status="verifying", per_device_results={},
    )
    db.add(record)
    db.commit()

    expected_hash = proposal_hash(change.config_payload, change.target_devices, change.source_template)
    if expected_hash != change.proposal_hash:
        status, results, error, summary = (
            "verification_error",
            _target_errors(change.target_devices, "Stored proposal integrity verification failed."),
            "Stored proposal integrity verification failed.", ""
        )
    elif {device.hostname for device in devices} != set(change.target_devices):
        status, results, error, summary = (
            "verification_error",
            _target_errors(change.target_devices, "One or more stored target devices no longer exist."),
            "One or more stored target devices no longer exist.", ""
        )
    elif unsupported := [
        device for device in devices
        if (device.os_type or "cisco").casefold()
        not in _SUPPORTED_VERIFICATION_OS_TYPES
    ]:
        unsupported_targets = ", ".join(
            f"{device.hostname} ({device.os_type or 'unknown'})"
            for device in sorted(unsupported, key=lambda item: item.hostname)
        )
        unsupported_error = (
            "Deterministic post-change verification is currently supported only "
            f"for Cisco IOS; unsupported targets: {unsupported_targets}."
        )
        status, results, error, summary = (
            "verification_error",
            _target_errors(change.target_devices, unsupported_error),
            unsupported_error,
            "",
        )
    else:
        try:
            output = "".join(runner(
                change.config_payload, devices, is_check_mode=True,
                execution_mode="verification",
            ))
            status, results, error, summary = parse_verification_output(
                output, set(change.target_devices)
            )
        except Exception as exc:
            status, results, error, summary = (
                "verification_error",
                _target_errors(change.target_devices, "Verification execution failed."),
                str(exc), "",
            )

    record.status = status
    record.per_device_results = results
    record.ansible_summary = summary
    record.error = error
    record.completed_at = datetime.now(timezone.utc)
    change.status = status
    db.commit()
    severity = "SUCCESS" if status == "verified" else ("WARNING" if status == "verification_failed" else "ERROR")
    audit_logger(
        db=db, event_type="Configuration", severity=severity, author=requested_by,
        target_devices=change.target_devices,
        details={
            "action": "Post-Change Configuration Verification",
            "change_id": change.change_id, "proposal_hash": change.proposal_hash,
            "verification_id": record.verification_id, "attempt_number": attempt,
            "state_transition": f"verifying -> {status}",
            "per_device_results": results, "error": error,
            "exec_actions_state_verified": False,
            "exec_actions_present": any(
                isinstance(change.config_payload.get(hostname), dict)
                and change.config_payload[hostname].get("exec")
                for hostname in change.target_devices
            ),
        },
    )
    return record
