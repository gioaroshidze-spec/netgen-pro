"""Safe build metadata and container health endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from sqlalchemy import inspect, text

from database import engine
from migration_state import BASELINE_REVISION, get_current_migration_head
from runtime_config import build_metadata, is_production


router = APIRouter(tags=["System"])
STARTED_MONOTONIC = time.monotonic()


def readiness_snapshot() -> dict:
    result = {"status": "ready", "database": "ok", "schema": "ok"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            table_names = set(inspect(connection).get_table_names())
            required = {"users", "network_devices", "scheduled_jobs"}
            if not required.issubset(table_names):
                raise RuntimeError("required VNMS tables are missing")
            if is_production():
                if "alembic_version" not in table_names:
                    raise RuntimeError("database is not under migration control")
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                expected_revision = get_current_migration_head()
                if revision != expected_revision:
                    raise RuntimeError(
                        f"database migration is at {revision!r}, "
                        f"expected head {expected_revision!r}"
                    )
                result["migration_revision"] = revision
                result["migration_head"] = expected_revision
    except Exception as exc:
        return {
            "status": "not_ready",
            "database": "error",
            "schema": "unavailable",
            "detail": str(exc),
        }
    return result


@router.get("/version")
def version():
    return build_metadata()


@router.get("/health/live")
def live():
    return {"status": "alive", "uptime_seconds": int(time.monotonic() - STARTED_MONOTONIC)}


@router.get("/health/ready")
def ready():
    result = readiness_snapshot()
    if result["status"] != "ready":
        raise HTTPException(status_code=503, detail=result)
    return result
