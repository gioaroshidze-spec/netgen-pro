#!/usr/bin/env bash
set -euo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ "${EUID}" -eq 0 ]] || die "Run this installer with sudo."
[[ "$(uname -s)" == "Linux" ]] || die "VNMS production installation supports Linux only."
[[ -r /etc/os-release ]] || die "Unable to identify this Linux distribution."
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || die "This baseline currently supports Ubuntu; detected ${ID:-unknown}."
command -v docker >/dev/null || die "Install Docker Engine before running this installer."
docker compose version >/dev/null 2>&1 || die "Install the Docker Compose plugin before running this installer."
command -v openssl >/dev/null || die "OpenSSL is required to generate runtime secrets."
[[ ! -e /etc/vnms/vnms.env && ! -e /var/lib/vnms/netgen.db ]] || die "An existing VNMS installation or database was found. Refusing to regenerate secrets; use vnms-update or the documented existing-database onboarding procedure."

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for required in docker-compose.prod.yml update.sh vnms.env.example README.md VERSION; do
    [[ -r "$SOURCE_DIR/$required" ]] || die "Deployment bundle is incomplete: missing $required."
done
DEFAULT_RELEASE_TAG="$(tr -d '[:space:]' < "$SOURCE_DIR/VERSION")"

read -r -p "Registry host (for example ghcr.io): " VNMS_REGISTRY
read -r -p "Image namespace (organization or user): " VNMS_IMAGE_NAMESPACE
read -r -p "VNMS release tag [${DEFAULT_RELEASE_TAG}]: " VNMS_RELEASE_TAG
VNMS_RELEASE_TAG="${VNMS_RELEASE_TAG:-$DEFAULT_RELEASE_TAG}"
read -r -p "HTTP bind address [0.0.0.0]: " VNMS_HTTP_BIND
VNMS_HTTP_BIND="${VNMS_HTTP_BIND:-0.0.0.0}"
read -r -p "HTTP port [80]: " VNMS_HTTP_PORT
VNMS_HTTP_PORT="${VNMS_HTTP_PORT:-80}"
[[ "$VNMS_REGISTRY" =~ ^[A-Za-z0-9.-]+(:[0-9]+)?$ ]] || die "Invalid registry host."
[[ "$VNMS_IMAGE_NAMESPACE" =~ ^[A-Za-z0-9._/-]+$ ]] || die "Invalid image namespace."
[[ "$VNMS_RELEASE_TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || die "Invalid release tag."
[[ "$VNMS_HTTP_BIND" =~ ^[0-9A-Fa-f:.]+$ ]] || die "Invalid HTTP bind address."
[[ "$VNMS_HTTP_PORT" =~ ^[0-9]{1,5}$ ]] && (( VNMS_HTTP_PORT >= 1 && VNMS_HTTP_PORT <= 65535 )) || die "Invalid HTTP port."

read -r -p "LiteLLM model (leave blank to disable AI) [${ACTIVE_AI_MODEL:-}]: " AI_MODEL_INPUT
ACTIVE_AI_MODEL="${AI_MODEL_INPUT:-${ACTIVE_AI_MODEL:-}}"
AI_API_KEY="${VNMS_AI_API_KEY:-}"
if [[ -n "${VNMS_INSTALL_AI_API_KEY_FILE:-}" ]]; then
    [[ -z "$AI_API_KEY" ]] || die "Set only VNMS_AI_API_KEY or VNMS_INSTALL_AI_API_KEY_FILE."
    [[ -r "$VNMS_INSTALL_AI_API_KEY_FILE" ]] || die "The configured AI API key input file is unreadable."
    AI_API_KEY="$(<"$VNMS_INSTALL_AI_API_KEY_FILE")"
fi
if [[ -n "$ACTIVE_AI_MODEL" && -z "$AI_API_KEY" ]]; then
    read -r -s -p "AI provider API key: " AI_API_KEY
    printf '\n'
fi
[[ -z "$AI_API_KEY" || -n "$ACTIVE_AI_MODEL" ]] || die "An AI API key requires a LiteLLM model."
[[ -z "$ACTIVE_AI_MODEL" || -n "$AI_API_KEY" ]] || die "The selected AI model requires an API key."

read -r -s -p "Initial admin password (minimum 12 characters): " ADMIN_PASSWORD
printf '\n'
read -r -s -p "Confirm initial admin password: " ADMIN_PASSWORD_CONFIRM
printf '\n'
[[ "$ADMIN_PASSWORD" == "$ADMIN_PASSWORD_CONFIRM" ]] || die "Passwords do not match."
(( ${#ADMIN_PASSWORD} >= 12 )) || die "Initial admin password is too short."

install -d -m 0750 -o root -g root /opt/vnms /opt/vnms/bin /etc/vnms /var/lib/vnms /var/lib/vnms/archive /var/log/vnms
install -d -m 0700 -o root -g root /etc/vnms/secrets
install -d -m 0750 -o root -g root /var/log/vnms/backend /var/log/vnms/ansible /var/log/vnms/frontend /var/lib/vnms/update-backups /var/lib/vnms/releases
install -m 0644 "$SOURCE_DIR/docker-compose.prod.yml" /opt/vnms/docker-compose.prod.yml
install -m 0644 "$SOURCE_DIR/vnms.env.example" /opt/vnms/vnms.env.example
install -m 0644 "$SOURCE_DIR/README.md" /opt/vnms/README.md
install -m 0750 "$SOURCE_DIR/update.sh" /opt/vnms/bin/update.sh
ln -sfn /opt/vnms/bin/update.sh /usr/local/sbin/vnms-update
install -m 0640 /dev/null /var/log/vnms/update.log

umask 077
openssl rand -base64 48 | tr -d '\n' > /etc/vnms/secrets/jwt_secret
openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n' > /etc/vnms/secrets/encryption_key
printf '%s' "$ADMIN_PASSWORD" > /etc/vnms/secrets/bootstrap_admin
printf '%s' "$AI_API_KEY" > /etc/vnms/secrets/ai_api_key
unset ADMIN_PASSWORD ADMIN_PASSWORD_CONFIRM AI_API_KEY VNMS_AI_API_KEY
chmod 0600 /etc/vnms/secrets/jwt_secret /etc/vnms/secrets/encryption_key /etc/vnms/secrets/bootstrap_admin /etc/vnms/secrets/ai_api_key

ENV_TMP="$(mktemp /etc/vnms/vnms.env.XXXXXX)"
trap 'rm -f -- "$ENV_TMP"' EXIT
{
    printf 'VNMS_REGISTRY=%s\n' "$VNMS_REGISTRY"
    printf 'VNMS_IMAGE_NAMESPACE=%s\n' "$VNMS_IMAGE_NAMESPACE"
    printf 'VNMS_RELEASE_TAG=%s\n' "$VNMS_RELEASE_TAG"
    printf 'VNMS_ENV_FILE=/etc/vnms/vnms.env\n'
    printf 'VNMS_HTTP_BIND=%s\n' "$VNMS_HTTP_BIND"
    printf 'VNMS_HTTP_PORT=%s\n' "$VNMS_HTTP_PORT"
    printf 'VNMS_ALLOWED_ORIGINS=\n'
    printf 'ACTIVE_AI_MODEL=%s\n' "$ACTIVE_AI_MODEL"
} > "$ENV_TMP"
chmod 0600 "$ENV_TMP"
mv "$ENV_TMP" /etc/vnms/vnms.env
trap - EXIT

COMPOSE=(docker compose --env-file /etc/vnms/vnms.env -f /opt/vnms/docker-compose.prod.yml)
docker info >/dev/null 2>&1 || die "Docker daemon is unavailable. Do not add users to the docker group automatically; run with sudo and check Docker."
printf 'Pulling exact versioned VNMS images. This root-run installer uses root Docker credentials; if needed, run sudo docker login %s first.\n' "$VNMS_REGISTRY"
"${COMPOSE[@]}" pull
"${COMPOSE[@]}" run --rm backend python migration_manager.py upgrade
"${COMPOSE[@]}" run --rm backend python bootstrap_admin.py
: > /etc/vnms/secrets/bootstrap_admin
chmod 0600 /etc/vnms/secrets/bootstrap_admin
"${COMPOSE[@]}" up -d

deadline=$((SECONDS + 180))
while (( SECONDS < deadline )); do
    backend_id="$("${COMPOSE[@]}" ps -q backend)"
    frontend_id="$("${COMPOSE[@]}" ps -q frontend)"
    if [[ -n "$backend_id" && -n "$frontend_id" ]] &&
       [[ "$(docker inspect -f '{{.State.Health.Status}}' "$backend_id")" == "healthy" ]] &&
       [[ "$(docker inspect -f '{{.State.Health.Status}}' "$frontend_id")" == "healthy" ]] &&
       "${COMPOSE[@]}" exec -T frontend wget -qO- http://127.0.0.1/api/version |
           grep -F "\"version\":\"$VNMS_RELEASE_TAG\"" >/dev/null; then
        printf '%s\n' "$VNMS_RELEASE_TAG" > /opt/vnms/VERSION
        host_address=localhost
        [[ "$VNMS_HTTP_BIND" == "0.0.0.0" ]] && host_address="$(hostname -I | awk '{print $1}')"
        printf 'VNMS %s is healthy at http://%s:%s/ and reports matching image metadata.\n' "$VNMS_RELEASE_TAG" "$host_address" "$VNMS_HTTP_PORT"
        exit 0
    fi
    sleep 3
done
"${COMPOSE[@]}" ps
die "VNMS did not become healthy with matching /version metadata within 180 seconds. The bootstrap password file was cleared; inspect service logs before retrying."
