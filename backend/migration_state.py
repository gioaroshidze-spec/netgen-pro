"""Alembic revision identities shared by migration and readiness code."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BASELINE_REVISION = "0001_phase3_baseline"


def alembic_config() -> Config:
    path = Path(__file__).with_name("alembic.ini")
    config = Config(str(path))
    config.set_main_option(
        "script_location", str(Path(__file__).with_name("alembic"))
    )
    return config


def get_current_migration_head() -> str:
    """Return the single current head independently of the historical baseline."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if not head:
        raise RuntimeError("Alembic has no current migration head.")
    return head
