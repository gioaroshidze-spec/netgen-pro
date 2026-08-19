#!/usr/bin/env bash
set -euo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

VERSION="${1:-}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || die "Usage: $0 <version> (for example 0.4.0)"
[[ -n "${VNMS_REGISTRY:-}" ]] || die "Set VNMS_REGISTRY (for example ghcr.io)."
[[ -n "${VNMS_IMAGE_NAMESPACE:-}" ]] || die "Set VNMS_IMAGE_NAMESPACE."
command -v git >/dev/null || die "Git is required on the build machine."
command -v docker >/dev/null || die "Docker is required on the build machine."
git diff --check
if [[ -n "$(git status --porcelain)" && "${VNMS_ALLOW_DIRTY_BUILD:-0}" != "1" ]]; then
    die "Working tree is not clean. Commit/stash changes or set VNMS_ALLOW_DIRTY_BUILD=1 intentionally."
fi

SHA="$(git rev-parse HEAD)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BACKEND_IMAGE="${VNMS_REGISTRY}/${VNMS_IMAGE_NAMESPACE}/vnms-backend:${VERSION}"
FRONTEND_IMAGE="${VNMS_REGISTRY}/${VNMS_IMAGE_NAMESPACE}/vnms-frontend:${VERSION}"

docker build --pull --build-arg "VNMS_VERSION=$VERSION" --build-arg "VNMS_BUILD_SHA=$SHA" --build-arg "VNMS_BUILD_TIME=$BUILD_TIME" -f Dockerfile.backend -t "$BACKEND_IMAGE" .
docker build --pull --build-arg "VNMS_VERSION=$VERSION" --build-arg "VNMS_BUILD_SHA=$SHA" --build-arg "VNMS_BUILD_TIME=$BUILD_TIME" --build-arg VITE_API_URL=/api -f Dockerfile.frontend -t "$FRONTEND_IMAGE" .
docker push "$BACKEND_IMAGE"
docker push "$FRONTEND_IMAGE"

if [[ "${VNMS_TAG_STABLE:-0}" == "1" ]]; then
    docker tag "$BACKEND_IMAGE" "${VNMS_REGISTRY}/${VNMS_IMAGE_NAMESPACE}/vnms-backend:stable"
    docker tag "$FRONTEND_IMAGE" "${VNMS_REGISTRY}/${VNMS_IMAGE_NAMESPACE}/vnms-frontend:stable"
    docker push "${VNMS_REGISTRY}/${VNMS_IMAGE_NAMESPACE}/vnms-backend:stable"
    docker push "${VNMS_REGISTRY}/${VNMS_IMAGE_NAMESPACE}/vnms-frontend:stable"
fi
printf 'Published immutable VNMS release %s (%s).\n' "$VERSION" "$SHA"
