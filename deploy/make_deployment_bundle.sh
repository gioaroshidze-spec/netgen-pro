#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || { printf 'Usage: %s <version>\n' "$0" >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf -- "$STAGE"' EXIT
mkdir -p "$STAGE/vnms-deploy"
install -m 0644 "$ROOT/deploy/docker-compose.prod.yml" "$STAGE/vnms-deploy/"
install -m 0644 "$ROOT/deploy/vnms.env.example" "$STAGE/vnms-deploy/"
install -m 0644 "$ROOT/deploy/README.md" "$STAGE/vnms-deploy/"
install -m 0755 "$ROOT/deploy/install.sh" "$STAGE/vnms-deploy/"
install -m 0755 "$ROOT/deploy/update.sh" "$STAGE/vnms-deploy/"
printf '%s\n' "$VERSION" > "$STAGE/vnms-deploy/VERSION"
tar -C "$STAGE" -czf "$ROOT/deploy/vnms-deployment-${VERSION}.tar.gz" vnms-deploy
printf 'Created %s\n' "$ROOT/deploy/vnms-deployment-${VERSION}.tar.gz"
