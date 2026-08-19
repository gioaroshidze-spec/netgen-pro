# VNMS production deployment

This bundle installs prebuilt, versioned VNMS images. It does not contain or
require the Git repository, backend source tree, frontend source tree, database,
archives, keys, environment files, or registry credentials.

## Developer release

Run the backend tests and frontend build first. Authenticate the build machine
to the private registry, then publish an explicit version and its deployment
manifest:

```bash
export VNMS_REGISTRY=ghcr.io
export VNMS_IMAGE_NAMESPACE=your-organization
./deploy/build_release.sh 0.4.0
./deploy/make_deployment_bundle.sh 0.4.0
```

The generated `deploy/vnms-deployment-0.4.0.tar.gz` is the controlled
deployment-manifest package. It contains only Compose, install/update helpers,
the environment example, this guide, and release metadata. It is safe to send
instead of application source, but its transport and origin must still be
trusted. `VNMS_TAG_STABLE=1` additionally moves `stable`; production always
selects the explicit `VNMS_RELEASE_TAG`, never `latest`.

Backend `/version` metadata is baked into the image at build time. The host
release tag selects an image but cannot override the version reported by that
image.

## Private registry authentication under sudo

Install and update run as root and therefore use root's Docker credential
context (normally `/root/.docker/config.json`). A prior unprivileged
`docker login` is not automatically visible to `sudo docker`. Authenticate
root explicitly before install/update. For a short-lived registry token:

```bash
read -r -s REGISTRY_TOKEN
printf '%s' "$REGISTRY_TOKEN" |
  sudo docker login ghcr.io --username YOUR_USER --password-stdin
unset REGISTRY_TOKEN
```

Use the least-privileged read-only token supported by the registry. Never put
tokens in this bundle or `vnms.env`. VNMS does not mount the Docker socket,
copy Docker credential files into containers, add users to the Docker group, or
include registry credentials in Support Bundles.

## Fresh Ubuntu installation

Install Docker Engine and the Docker Compose plugin using the organization's
approved method. Copy only the generated deployment tarball to the VM, extract
it, authenticate root to the registry as above, and run:

```bash
sudo ./install.sh
```

The installer prompts without echo for the initial administrator password and,
when AI is enabled, its provider API key. It generates unique JWT and Fernet
keys, migrates the empty database, creates only the first administrator, clears
the bootstrap password file, verifies health plus actual image `/version`, and
starts VNMS. The initial administrator must change the password on first login.
No `admin/admin` production fallback exists.

Runtime layout:

- `/opt/vnms`: Compose file, updater, release metadata, and deployment docs
- `/etc/vnms/vnms.env`: root-owned non-secret deployment settings
- `/etc/vnms/secrets`: root-only runtime secret files
- `/var/lib/vnms/netgen.db`: SQLite database
- `/var/lib/vnms/archive`: configuration backup artifacts
- `/var/lib/vnms/releases`: administrator-staged update manifest packages
- `/var/lib/vnms/update-backups`: five bounded pre-update snapshots
- `/var/log/vnms`: bounded backend, Ansible, frontend, and update logs

Back up `/var/lib/vnms` and `/etc/vnms` with access-controlled storage. Treat
database and archive backups as sensitive because they contain operational
data.

## Optional AI provider configuration

VNMS can run without AI. Leave the LiteLLM model prompt blank during install;
AI generation then returns a clear service-unavailable response while all
non-AI features remain available.

To enable AI, enter a LiteLLM model such as `provider/model-name` and provide
the key at the non-echoing prompt. For unattended secret input, prepare a
root-readable file outside the bundle and pass only its path:

```bash
sudo env ACTIVE_AI_MODEL=provider/model-name \
  VNMS_INSTALL_AI_API_KEY_FILE=/root/vnms-provider-key ./install.sh
```

The installer copies the value to
`/etc/vnms/secrets/ai_api_key` with mode `0600`; Compose supplies only
`VNMS_AI_API_KEY_FILE` to the backend. No key is stored in an image, Git,
`vnms.env`, updater output, or Support Bundle. Remove the input file after the
organization's secure backup procedure is complete.

## Update and failure behavior

Obtain the new release's deployment tarball through the trusted release channel
and stage it root-only:

```bash
sudo install -m 0640 vnms-deployment-0.4.1.tar.gz \
  /var/lib/vnms/releases/vnms-deployment-0.4.1.tar.gz
sudo vnms-update 0.4.1
```

A package at another location can be supplied as the second argument. The
updater copies itself to a temporary execution directory, locks against
concurrent runs, rejects unexpected/archive-traversal files, validates the
manifest `VERSION`, validates shell and Compose syntax, stops the backend for a
consistent SQLite copy, pulls exact images, and atomically installs the new
Compose/updater/docs. It then migrates, recreates services, requires readiness,
and confirms the actual image-owned `/version`.

On any failure it stops the failed services, restores the database,
`vnms.env`, previous release tag, Compose file, updater, and deployment docs,
then starts the prior images. It reports rollback success only after the prior
release passes health and `/version` checks. It never runs
`docker compose down -v`, prunes Docker, or deletes persistent application
data.

Updater diagnostics rotate at 1 MiB with three historical files and record
requested/previous releases, start/end, manifest install, migration, health,
and rollback outcomes. They never intentionally log secrets and are redacted
again when included in Support Bundle v2.

A controlled failure hook exists only for isolated local validation:

```bash
sudo env VNMS_ALLOW_UPDATE_FAILURE_INJECTION=1 \
  VNMS_UPDATE_FAILURE_INJECTION=after_migration \
  vnms-update 0.4.1 /path/to/test-only-manifest.tar.gz
```

Never run failure injection against a real installation. Use an isolated test
database, volumes, registry/images, and VM/container host, then verify the prior
database, deployment files, version, and health before discarding the test.

For an existing pre-Alembic database, stop/quiesce VNMS and make a verified
copy. Run the new backend migration command with
`--existing-backup /absolute/path/to/backup.db`. VNMS validates the exact
immutable Phase-3 schema, stamps only `0001_phase3_baseline`, and then upgrades
to the current dynamically discovered Alembic head. Any mismatch fails closed.

## Networking and support

The installer's bind prompt defaults to `0.0.0.0`, suitable for VM host/LAN
access when the host firewall permits the selected port. Use `127.0.0.1` for
local-only access. Set `VNMS_HTTP_PORT` to the permitted host port. Do not
expose VNMS beyond the trusted administrative network; configure Ubuntu/cloud
firewalls explicitly. This patch does not automate TLS.

Only Nginx publishes a host port. The backend remains internal. `/api/` and
`/ws/` are proxied to it. WebSocket access logging is disabled, and normal
logging uses `$uri`, never query strings, so CLI query tokens are not recorded.

Administrators can use **Event Logs -> Generate Support Bundle**. The bounded ZIP
contains safe build/health/migration/runtime data, bounded browser diagnostics,
rotated backend/Ansible/updater logs, and Nginx logs. It excludes the database,
archives, environment, request bodies, credentials, private keys, registry
configuration, and Docker socket. Redaction covers header, query, key-value,
and quoted JSON-like secret forms. Redaction is best-effort, so bundles must
still be handled as sensitive.

The VM receives no source repository and runs prebuilt images. This is
operational source separation, not DRM: root and Docker-privileged administrators
can inspect containers and image contents.
