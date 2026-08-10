import hashlib
import json


def proposal_hash(config_payload, target_devices, source_template=None):
    canonical = {
        "config_payload": config_payload,
        "target_devices": sorted(target_devices),
        "source_template": source_template,
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
