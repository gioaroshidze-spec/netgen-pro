from sqlalchemy.orm import Session
import models
from datetime import datetime, timezone

def log_event(
    db: Session,
    event_type: str,
    severity: str,
    details: dict,
    target_devices: list = None,
    author: str = "System"
):
    """
    Universal logging helper. Injects an immutable audit record into the database.
    """

    if target_devices is None:
        target_devices = []

    db_log = models.EventLog(
        timestamp=datetime.now(timezone.utc),
        event_type=event_type,
        severity=severity,
        author=author,
        target_devices=target_devices,
        details=details
    )

    db.add(db_log)
    db.commit()
    db.refresh(db_log)

    return db_log