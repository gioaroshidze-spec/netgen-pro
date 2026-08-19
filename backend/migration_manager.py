"""Conservative fresh/existing SQLite onboarding for Alembic."""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect

from database import engine
from migration_state import (
    BASELINE_REVISION,
    alembic_config,
    get_current_migration_head,
)


IGNORED_TABLES = {"alembic_version"}


def _normalized_type(column) -> str:
    return str(column["type"]).upper().replace(" ", "")


def _table_signature(inspector, table_name: str) -> dict:
    columns = {
        column["name"]: {
            "type": _normalized_type(column),
            "nullable": bool(column["nullable"]),
            "primary_key": int(column.get("primary_key") or 0),
        }
        for column in inspector.get_columns(table_name)
    }
    indexes = {
        item["name"]: {
            "columns": tuple(item["column_names"]),
            "unique": bool(item["unique"]),
        }
        for item in inspector.get_indexes(table_name)
    }
    foreign_keys = sorted(
        (
            tuple(item["constrained_columns"]),
            item["referred_table"],
            tuple(item["referred_columns"]),
            (item.get("options") or {}).get("ondelete"),
        )
        for item in inspector.get_foreign_keys(table_name)
    )
    return {
        "columns": columns,
        "indexes": indexes,
        "foreign_keys": foreign_keys,
    }


def _schema_signature(bind) -> dict:
    inspector = inspect(bind)
    tables = set(inspector.get_table_names()) - IGNORED_TABLES
    return {
        table_name: _table_signature(inspector, table_name)
        for table_name in sorted(tables)
    }


def _baseline_signature() -> dict:
    """Build the expected structure from immutable revision 0001, not models.py."""
    baseline_engine = create_engine("sqlite://")
    try:
        with baseline_engine.connect() as connection:
            config = alembic_config()
            config.attributes["connection"] = connection
            command.upgrade(config, BASELINE_REVISION)
            return _schema_signature(connection)
    finally:
        baseline_engine.dispose()


def schema_mismatches() -> list[str]:
    actual = _schema_signature(engine)
    expected = _baseline_signature()
    problems = []
    actual_tables = set(actual)
    expected_tables = set(expected)
    if actual_tables != expected_tables:
        problems.append(
            f"table set differs (missing={sorted(expected_tables - actual_tables)}, "
            f"unexpected={sorted(actual_tables - expected_tables)})"
        )
    for table_name in sorted(actual_tables & expected_tables):
        for element in ("columns", "indexes", "foreign_keys"):
            if actual[table_name][element] != expected[table_name][element]:
                problems.append(f"{table_name} {element} differ from immutable baseline")
    return problems


def upgrade(existing_backup: str | None = None) -> None:
    tables = set(inspect(engine).get_table_names())
    config = alembic_config()
    if not tables:
        command.upgrade(config, "head")
        return
    if "alembic_version" not in tables:
        if not existing_backup:
            raise RuntimeError(
                "Existing database has no migration revision. Create and verify a backup, "
                "then rerun with --existing-backup /absolute/path/to/backup.db."
            )
        backup = Path(existing_backup)
        if not backup.is_absolute() or not backup.is_file() or backup.stat().st_size == 0:
            raise RuntimeError("The existing database backup must be an absolute, non-empty file.")
        problems = schema_mismatches()
        if problems:
            raise RuntimeError("Baseline schema validation failed: " + "; ".join(problems))
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["upgrade", "validate"])
    parser.add_argument("--existing-backup")
    args = parser.parse_args()
    if args.action == "validate":
        problems = schema_mismatches()
        if problems:
            raise RuntimeError("Baseline schema validation failed: " + "; ".join(problems))
        print("Database matches the immutable VNMS Phase 1-3 baseline schema.")
    else:
        upgrade(args.existing_backup)
        print(f"Database migration is at head {get_current_migration_head()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
