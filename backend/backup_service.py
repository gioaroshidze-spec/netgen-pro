import os
from datetime import datetime
from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException
from connection_utils import get_netmiko_params

def build_backup_filename(prefix, os_type, device_type, hostname, timestamp):
    return f"{prefix}_{os_type or 'UnknownOS'}_{device_type or 'UnknownDevice'}_{hostname}_{timestamp}.txt"

def capture_running_configuration(device) -> dict:
    command = "show running-config"
    if device.os_type == "mikrotik":
        command = "/export"
    elif device.os_type in ("alcatel", "alcatel-lucent"):
        command = "show configuration snapshot"
    try:
        with ConnectHandler(**get_netmiko_params(device)) as connection:
            if device.os_type != "mikrotik":
                try:
                    connection.enable()
                except Exception:
                    pass
            raw = connection.send_command(command)
        clean = "\n".join(line for line in raw.splitlines() if not line.startswith(("Building configuration", "Current configuration")))
        return {"hostname": device.hostname, "success": True, "config": clean}
    except (NetmikoTimeoutException, NetmikoAuthenticationException):
        return {"hostname": device.hostname, "success": False, "error": "Connection Timeout or Auth Failed"}
    except Exception as exc:
        return {"hostname": device.hostname, "success": False, "error": str(exc)}

def create_preconfiguration_backups(devices, archive_dir="archive", now=None):
    os.makedirs(archive_dir, exist_ok=True)
    results, files = [], {}
    for device in devices:
        result = capture_running_configuration(device)
        results.append(result)
        if result["success"]:
            timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
            filename = build_backup_filename("Pre_Config", device.os_type, device.device_type, device.hostname, timestamp)
            try:
                with open(os.path.join(archive_dir, filename), "w", encoding="utf-8") as archive:
                    archive.write(result["config"])
                files[device.hostname] = filename
            except Exception as exc:
                result["success"] = False
                result["error"] = f"Archive write failed: {exc}"
    return files, results
