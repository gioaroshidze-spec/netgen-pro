import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import schemas
from database import Base


def serialize_event(timestamp):
    event = models.EventLog(
        id=1,
        timestamp=timestamp,
        event_type="System",
        severity="INFO",
        author="tester",
        target_devices=[],
        details={},
    )
    return json.loads(
        schemas.EventLogResponse.model_validate(event).model_dump_json()
    )["timestamp"]


def test_naive_sqlite_timestamp_serializes_as_utc():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        event = models.EventLog(
            timestamp=datetime(2026, 8, 11, 12, 1, 47),
            event_type="System",
            severity="INFO",
            author="tester",
            target_devices=[],
            details={},
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        assert event.timestamp.tzinfo is None
        assert serialize_event(event.timestamp) == "2026-08-11T12:01:47Z"
    finally:
        db.close()


def test_timezone_aware_utc_timestamp_remains_utc():
    timestamp = datetime(2026, 8, 11, 12, 1, 47, tzinfo=timezone.utc)

    assert serialize_event(timestamp) == "2026-08-11T12:01:47Z"


def test_utc_timestamp_is_not_converted_twice():
    timestamp = datetime(2026, 8, 11, 12, 1, 47, tzinfo=timezone.utc)
    serialized = serialize_event(timestamp)

    assert serialized == "2026-08-11T12:01:47Z"
    assert datetime.fromisoformat(serialized.replace("Z", "+00:00")) == timestamp
