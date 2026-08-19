"""Immutable Phase 1-3 schema snapshot.

Revision ID: 0001_phase3_baseline

This historical revision never imports the live application models. Later
model changes belong in later Alembic revisions.
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_phase3_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _indexes(table, columns, unique=()):
    for column in columns:
        op.create_index(
            f"ix_{table}_{column}",
            table,
            [column],
            unique=column in unique,
        )


def upgrade():
    op.create_table(
        "buildings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("buildings", ("id", "name"), unique=("name",))

    op.create_table(
        "configuration_backup_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.String(), nullable=False),
        sa.Column("rollback_id", sa.String(), nullable=True),
        sa.Column("hostname", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "configuration_backup_artifacts",
        ("id", "change_id", "rollback_id", "hostname", "artifact_type"),
    )

    op.create_table(
        "configuration_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=True),
        sa.Column("source_template", sa.String(), nullable=True),
        sa.Column("target_devices", sa.JSON(), nullable=False),
        sa.Column("config_payload", sa.JSON(), nullable=False),
        sa.Column("proposal_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("simulation_started_at", sa.DateTime(), nullable=True),
        sa.Column("simulation_completed_at", sa.DateTime(), nullable=True),
        sa.Column("simulation_success", sa.Boolean(), nullable=True),
        sa.Column("simulated_by", sa.String(), nullable=True),
        sa.Column("simulation_override", sa.Boolean(), nullable=False),
        sa.Column("simulation_override_by", sa.String(), nullable=True),
        sa.Column("simulation_override_reason", sa.String(), nullable=True),
        sa.Column("simulation_override_at", sa.DateTime(), nullable=True),
        sa.Column("pre_backup_completed_at", sa.DateTime(), nullable=True),
        sa.Column("pre_backup_success", sa.Boolean(), nullable=True),
        sa.Column("pre_backup_files", sa.JSON(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(), nullable=True),
        sa.Column("deployed_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "configuration_changes",
        ("id", "change_id", "status"),
        unique=("change_id",),
    )

    op.create_table(
        "configuration_rollbacks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rollback_id", sa.String(), nullable=False),
        sa.Column("change_id", sa.String(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("authorized_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("pre_rollback_files", sa.JSON(), nullable=True),
        sa.Column("per_device_results", sa.JSON(), nullable=False),
        sa.Column("verification_results", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "configuration_rollbacks",
        ("id", "rollback_id", "change_id", "status"),
        unique=("rollback_id",),
    )

    op.create_table(
        "configuration_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("configuration_templates", ("id", "name", "category"))

    op.create_table(
        "configuration_verifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("verification_id", sa.String(), nullable=False),
        sa.Column("change_id", sa.String(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("per_device_results", sa.JSON(), nullable=False),
        sa.Column("ansible_summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "configuration_verifications",
        ("id", "verification_id", "change_id", "status"),
        unique=("verification_id",),
    )

    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("target_devices", sa.JSON(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("event_logs", ("id", "event_type", "severity", "author"))

    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("job_type", sa.String(), nullable=True),
        sa.Column("target_devices", sa.JSON(), nullable=True),
        sa.Column("job_payload", sa.JSON(), nullable=True),
        sa.Column("cron_day_of_week", sa.String(), nullable=True),
        sa.Column("cron_hour", sa.String(), nullable=True),
        sa.Column("cron_minute", sa.String(), nullable=True),
        sa.Column("interval_hours", sa.Integer(), nullable=True),
        sa.Column("run_once_time", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_status", sa.String(), nullable=True),
        sa.Column("last_run_time", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("scheduled_jobs", ("id", "name"))

    op.create_table(
        "topology_edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_hostname", sa.String(), nullable=True),
        sa.Column("source_port", sa.String(), nullable=True),
        sa.Column("target_hostname", sa.String(), nullable=True),
        sa.Column("target_port", sa.String(), nullable=True),
        sa.Column("link_type", sa.String(), nullable=True),
        sa.Column("current_utilization", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("topology_edges", ("id", "source_hostname", "target_hostname"))

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("requires_password_change", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("users", ("id", "username"), unique=("username",))

    op.create_table(
        "floors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("building_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["building_id"], ["buildings.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("floors", ("id", "name"))

    op.create_table(
        "saved_topology_views",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("zone_ids", sa.JSON(), nullable=True),
        sa.Column("coordinates", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("saved_topology_views", ("id", "name"))

    op.create_table(
        "zones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("floor_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["floor_id"], ["floors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes("zones", ("id", "name"))

    op.create_table(
        "network_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hostname", sa.String(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("device_type", sa.String(), nullable=True),
        sa.Column("os_type", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("encrypted_password", sa.String(), nullable=True),
        sa.Column("is_legacy", sa.Boolean(), nullable=True),
        sa.Column("pos_x", sa.Float(), nullable=True),
        sa.Column("pos_y", sa.Float(), nullable=True),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("last_cpu", sa.String(), nullable=True),
        sa.Column("last_ram", sa.String(), nullable=True),
        sa.Column("last_uptime", sa.String(), nullable=True),
        sa.Column("telemetry_updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "network_devices",
        ("id", "hostname", "ip_address"),
        unique=("hostname", "ip_address"),
    )


def downgrade():
    raise RuntimeError("The VNMS baseline migration is intentionally non-destructive.")
