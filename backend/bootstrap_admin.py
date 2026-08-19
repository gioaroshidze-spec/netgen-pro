"""Idempotent initial administrator bootstrap used by the production installer."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import models
from database import SessionLocal
from routers.auth import get_password_hash
from runtime_config import ConfigurationError, is_production


def bootstrap_admin(username: str, password: str) -> bool:
    if not username or len(username) > 128:
        raise ConfigurationError("Bootstrap administrator username is invalid.")
    if len(password) < 12:
        raise ConfigurationError("Bootstrap administrator password must be at least 12 characters.")
    db = SessionLocal()
    try:
        if db.query(models.User).filter(models.User.role == "admin").first():
            return False
        if db.query(models.User).filter(models.User.username == username).first():
            raise ConfigurationError(
                "Bootstrap username already exists but is not an administrator."
            )
        db.add(models.User(
            username=username,
            hashed_password=get_password_hash(password),
            role="admin",
            requires_password_change=True,
        ))
        db.commit()
        return True
    finally:
        db.close()


def _read_password() -> str:
    path_value = os.getenv("VNMS_BOOTSTRAP_PASSWORD_FILE")
    if not path_value:
        raise ConfigurationError("VNMS_BOOTSTRAP_PASSWORD_FILE is required.")
    try:
        return Path(path_value).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigurationError("Unable to read the bootstrap password file.") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Create VNMS's first administrator.")
    parser.add_argument("--username", default=os.getenv("VNMS_BOOTSTRAP_USERNAME", "admin"))
    args = parser.parse_args()
    if not is_production():
        raise ConfigurationError("The bootstrap command requires VNMS_ENV=production.")
    created = bootstrap_admin(args.username, _read_password())
    print("Initial administrator created." if created else "An administrator already exists; no changes made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
