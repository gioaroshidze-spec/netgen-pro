#!/usr/bin/env bash
set -euo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

if [[ "${VNMS_UPDATE_RUNNING_COPY:-0}" != "1" ]]; then
    SELF_STAGE="$(mktemp -d /tmp/vnms-update-run.XXXXXX)"
    install -m 0750 "${BASH_SOURCE[0]}" "$SELF_STAGE/update.sh"
    VNMS_UPDATE_RUNNING_COPY=1 VNMS_UPDATE_TEMP_DIR="$SELF_STAGE"         exec "$SELF_STAGE/update.sh" "$@"
fi
cleanup_running_copy() {
    [[ "${VNMS_UPDATE_TEMP_DIR:-}" == /tmp/vnms-update-run.* ]] &&
        rm -rf -- "$VNMS_UPDATE_TEMP_DIR"
}
trap cleanup_running_copy EXIT

[[ "${EUID}" -eq 0 ]] || die "Run vnms-update with sudo."
TARGET_RELEASE_TAG="${1:-}"
MANIFEST_PACKAGE="${2:-/var/lib/vnms/releases/vnms-deployment-${TARGET_RELEASE_TAG}.tar.gz}"
[[ "$TARGET_RELEASE_TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] ||
    die "Usage: vnms-update <release-tag> [deployment-manifest.tar.gz]"
command -v flock >/dev/null || die "flock is required."
command -v tar >/dev/null || die "tar is required."
exec 9>/run/lock/vnms-update.lock
flock -n 9 || die "Another VNMS update is already running."

ENV_FILE=/etc/vnms/vnms.env
INSTALL_ROOT=/opt/vnms
COMPOSE_FILE="$INSTALL_ROOT/docker-compose.prod.yml"
UPDATE_FILE="$INSTALL_ROOT/bin/update.sh"
[[ -r "$ENV_FILE" && -r "$COMPOSE_FILE" && -r "$UPDATE_FILE" ]] ||
    die "VNMS production deployment is not installed."
[[ "$(stat -c '%u' "$ENV_FILE")" == "0" ]] || die "VNMS environment file must be owned by root."
. "$ENV_FILE"
PREVIOUS_RELEASE_TAG="${VNMS_RELEASE_TAG:?Installed release tag is missing}"
[[ "$TARGET_RELEASE_TAG" != "$PREVIOUS_RELEASE_TAG" ]] ||
    die "VNMS $TARGET_RELEASE_TAG is already installed."

LOG_FILE=/var/log/vnms/update.log
install -d -m 0750 -o root -g root "$(dirname "$LOG_FILE")"
if [[ -f "$LOG_FILE" && "$(stat -c '%s' "$LOG_FILE")" -gt 1048576 ]]; then
    [[ ! -e "$LOG_FILE.2" ]] || mv -f "$LOG_FILE.2" "$LOG_FILE.3"
    [[ ! -e "$LOG_FILE.1" ]] || mv -f "$LOG_FILE.1" "$LOG_FILE.2"
    mv -f "$LOG_FILE" "$LOG_FILE.1"
fi
touch "$LOG_FILE"
chmod 0640 "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
printf '[%s] update start requested=%s previous=%s\n' "$STAMP" "$TARGET_RELEASE_TAG" "$PREVIOUS_RELEASE_TAG"

[[ -r "$MANIFEST_PACKAGE" ]] || die "Deployment manifest package is missing: $MANIFEST_PACKAGE"
MANIFEST_STAGE="$(mktemp -d /tmp/vnms-manifest.XXXXXX)"
cleanup_manifest() {
    [[ "${MANIFEST_STAGE:-}" == /tmp/vnms-manifest.* ]] &&
        rm -rf -- "$MANIFEST_STAGE"
}
trap 'cleanup_manifest; cleanup_running_copy' EXIT

mapfile -t archive_entries < <(tar -tzf "$MANIFEST_PACKAGE")
for entry in "${archive_entries[@]}"; do
    [[ "$entry" != /* && "$entry" != *"/../"* && "$entry" != "../"* ]] ||
        die "Unsafe path in deployment manifest package."
    case "$entry" in
        vnms-deploy/|vnms-deploy/docker-compose.prod.yml|vnms-deploy/update.sh|vnms-deploy/install.sh|vnms-deploy/vnms.env.example|vnms-deploy/README.md|vnms-deploy/VERSION) ;;
        *) die "Unexpected file in deployment manifest package: $entry" ;;
    esac
done
tar --extract --gzip --file "$MANIFEST_PACKAGE" --directory "$MANIFEST_STAGE"     --no-same-owner --no-same-permissions
STAGED="$MANIFEST_STAGE/vnms-deploy"
for required in docker-compose.prod.yml update.sh install.sh vnms.env.example README.md VERSION; do
    [[ -f "$STAGED/$required" && ! -L "$STAGED/$required" ]] ||
        die "Deployment manifest is missing a regular $required file."
done
MANIFEST_RELEASE_TAG="$(tr -d '[:space:]' < "$STAGED/VERSION")"
[[ "$MANIFEST_RELEASE_TAG" == "$TARGET_RELEASE_TAG" ]] ||
    die "Deployment manifest version $MANIFEST_RELEASE_TAG does not match requested $TARGET_RELEASE_TAG."
bash -n "$STAGED/update.sh" "$STAGED/install.sh"

compose_with() {
    local compose_file="$1" release_tag="$2"
    shift 2
    VNMS_RELEASE_TAG="$release_tag" docker compose         --env-file "$ENV_FILE" -f "$compose_file" "$@"
}
VNMS_RELEASE_TAG="$TARGET_RELEASE_TAG" docker compose     --env-file "$ENV_FILE" -f "$STAGED/docker-compose.prod.yml" config --quiet
printf '[%s] deployment manifest validated for requested=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$TARGET_RELEASE_TAG"

BACKUP_ROOT=/var/lib/vnms/update-backups
BACKUP_DIR="${BACKUP_ROOT}/${STAMP}-${PREVIOUS_RELEASE_TAG}-to-${TARGET_RELEASE_TAG}"
install -d -m 0750 -o root -g root "$BACKUP_DIR/deployment"
[[ -s /var/lib/vnms/netgen.db ]] || die "Production database is missing or empty."
install -m 0600 "$ENV_FILE" "$BACKUP_DIR/vnms.env"
for relative in docker-compose.prod.yml bin/update.sh vnms.env.example README.md VERSION; do
    if [[ -f "$INSTALL_ROOT/$relative" ]]; then
        install -D -m 0640 "$INSTALL_ROOT/$relative" "$BACKUP_DIR/deployment/$relative"
    fi
done

wait_healthy() {
    local compose_file="$1" release_tag="$2" deadline backend_id frontend_id
    deadline=$((SECONDS + 180))
    while (( SECONDS < deadline )); do
        backend_id="$(compose_with "$compose_file" "$release_tag" ps -q backend)"
        frontend_id="$(compose_with "$compose_file" "$release_tag" ps -q frontend)"
        if [[ -n "$backend_id" && -n "$frontend_id" ]] &&
           [[ "$(docker inspect -f '{{.State.Health.Status}}' "$backend_id" 2>/dev/null || true)" == healthy ]] &&
           [[ "$(docker inspect -f '{{.State.Health.Status}}' "$frontend_id" 2>/dev/null || true)" == healthy ]] &&
           compose_with "$compose_file" "$release_tag" exec -T frontend                wget -qO- http://127.0.0.1/api/version |
               grep -F "\"version\":\"$release_tag\"" >/dev/null; then
            return 0
        fi
        sleep 3
    done
    return 1
}

atomic_install() {
    local source="$1" destination="$2" mode="$3" temporary
    temporary="$(mktemp "$(dirname "$destination")/.vnms-install.XXXXXX")"
    install -m "$mode" "$source" "$temporary"
    mv -f "$temporary" "$destination"
}

write_release_tag() {
    local release_tag="$1" temporary
    temporary="$(mktemp /etc/vnms/vnms.env.XXXXXX)"
    awk -v release_tag="$release_tag" '
        BEGIN { done=0 }
        /^VNMS_RELEASE_TAG=/ { print "VNMS_RELEASE_TAG=" release_tag; done=1; next }
        { print }
        END { if (!done) print "VNMS_RELEASE_TAG=" release_tag }
    ' "$ENV_FILE" > "$temporary"
    chmod 0600 "$temporary"
    mv -f "$temporary" "$ENV_FILE"
    printf '%s\n' "$release_tag" > "$INSTALL_ROOT/VERSION"
}

restore_deployment_file() {
    local relative="$1" mode="$2"
    if [[ -f "$BACKUP_DIR/deployment/$relative" ]]; then
        install -D -m "$mode" "$BACKUP_DIR/deployment/$relative" "$INSTALL_ROOT/$relative"
    else
        rm -f -- "$INSTALL_ROOT/$relative"
    fi
}

rollback() {
    local failure_status="$?"
    trap - ERR
    set +e
    printf '[%s] rollback attempt target=%s previous=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$TARGET_RELEASE_TAG" "$PREVIOUS_RELEASE_TAG"
    compose_with "$STAGED/docker-compose.prod.yml" "$TARGET_RELEASE_TAG" stop backend frontend
    install -m 0640 "$BACKUP_DIR/netgen.db" /var/lib/vnms/netgen.db
    install -m 0600 "$BACKUP_DIR/vnms.env" "$ENV_FILE"
    restore_deployment_file docker-compose.prod.yml 0644
    restore_deployment_file bin/update.sh 0750
    restore_deployment_file vnms.env.example 0644
    restore_deployment_file README.md 0644
    restore_deployment_file VERSION 0644
    compose_with "$COMPOSE_FILE" "$PREVIOUS_RELEASE_TAG" up -d
    if wait_healthy "$COMPOSE_FILE" "$PREVIOUS_RELEASE_TAG"; then
        printf '[%s] rollback outcome=success health=passed restored=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$PREVIOUS_RELEASE_TAG"
    else
        printf '[%s] rollback outcome=failed health=failed restored=%s manual_action=required\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$PREVIOUS_RELEASE_TAG" >&2
    fi
    printf '[%s] update end outcome=failed requested=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$TARGET_RELEASE_TAG"
    exit "$failure_status"
}

compose_with "$COMPOSE_FILE" "$PREVIOUS_RELEASE_TAG" stop backend
trap 'compose_with "$COMPOSE_FILE" "$PREVIOUS_RELEASE_TAG" up -d' ERR
install -m 0640 /var/lib/vnms/netgen.db "$BACKUP_DIR/netgen.db"
trap rollback ERR
printf '[%s] database backup outcome=success\n' "$(date -u +%Y%m%dT%H%M%SZ)"

compose_with "$STAGED/docker-compose.prod.yml" "$TARGET_RELEASE_TAG" pull
atomic_install "$STAGED/docker-compose.prod.yml" "$COMPOSE_FILE" 0644
atomic_install "$STAGED/update.sh" "$UPDATE_FILE" 0750
atomic_install "$STAGED/vnms.env.example" "$INSTALL_ROOT/vnms.env.example" 0644
atomic_install "$STAGED/README.md" "$INSTALL_ROOT/README.md" 0644
printf '[%s] deployment manifest install outcome=success\n' "$(date -u +%Y%m%dT%H%M%SZ)"

compose_with "$COMPOSE_FILE" "$TARGET_RELEASE_TAG" run --rm backend     python migration_manager.py upgrade
printf '[%s] migration outcome=success target=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$TARGET_RELEASE_TAG"
if [[ "${VNMS_UPDATE_FAILURE_INJECTION:-}" == "after_migration" ]]; then
    [[ "${VNMS_ALLOW_UPDATE_FAILURE_INJECTION:-0}" == "1" ]] ||
        die "Failure injection requires VNMS_ALLOW_UPDATE_FAILURE_INJECTION=1."
    printf '[%s] controlled failure injection=after_migration\n' "$(date -u +%Y%m%dT%H%M%SZ)"
    false
fi

write_release_tag "$TARGET_RELEASE_TAG"
compose_with "$COMPOSE_FILE" "$TARGET_RELEASE_TAG" up -d
wait_healthy "$COMPOSE_FILE" "$TARGET_RELEASE_TAG"
printf '[%s] health-check outcome=success version=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$TARGET_RELEASE_TAG"
trap - ERR
printf '[%s] update end outcome=success requested=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$TARGET_RELEASE_TAG"

mapfile -t old_backups < <(
    find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' |
        sort -rn | tail -n +6 | cut -d' ' -f2-
)
for old_backup in "${old_backups[@]}"; do
    [[ "$old_backup" == "$BACKUP_ROOT/"* ]] || die "Unsafe backup retention path."
    rm -rf -- "$old_backup"
done
