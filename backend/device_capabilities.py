from dataclasses import asdict, dataclass


AUTOMATED_RESTORE_UNQUALIFIED_REASON = (
    "No validated automated restore profile exists for this platform/version."
)


@dataclass(frozen=True)
class DeviceCapabilities:
    backup: bool = False
    deploy: bool = False
    check_mode: bool = False
    deterministic_verify: bool = False
    automated_restore: bool = False
    automated_restore_reason: str = AUTOMATED_RESTORE_UNQUALIFIED_REASON

    def as_dict(self):
        return asdict(self)


def get_device_capabilities(device=None) -> DeviceCapabilities:
    """Return conservative capabilities for the current, unenriched inventory."""
    os_type = (getattr(device, "os_type", None) or "").casefold()

    if os_type == "cisco":
        return DeviceCapabilities(
            backup=True,
            deploy=True,
            check_mode=True,
            deterministic_verify=True,
        )
    if os_type in {"mikrotik", "aruba", "hpe", "alcatel", "alcatel-lucent"}:
        return DeviceCapabilities(backup=True, deploy=True)
    return DeviceCapabilities()


def capabilities_by_hostname(devices):
    return {
        device.hostname: get_device_capabilities(device).as_dict()
        for device in devices
    }
