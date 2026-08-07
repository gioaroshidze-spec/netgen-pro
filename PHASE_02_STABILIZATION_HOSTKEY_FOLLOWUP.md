# VNMS Phase 2 Stabilization Follow-up

## Title

**Add legacy-only `ssh-rsa` server host-key compatibility for Ansible libssh**

## Confirmed lab result

The earlier legacy KEX mismatch is resolved.

The current failure is now:

```text
kex error : no match for method server host key algo:
server [ssh-rsa]
client [ssh-ed25519, ecdsa-..., rsa-sha2-512, rsa-sha2-256]
```

This proves SSH negotiation progressed past key exchange and is now failing specifically because the legacy Cisco IOS switch offers only the `ssh-rsa` server host-key algorithm.

The lab device is explicitly marked:

```text
is_legacy = true
```

Do not broaden compatibility to non-legacy devices.

---

## Required change

Inspect the installed `ansible.netcommon.libssh` documentation first and confirm the supported variable name.

For the installed version, the expected variable is:

```yaml
ansible_libssh_hostkeys: "ssh-rsa"
```

Update the centralized Ansible inventory construction (`backend/connection_utils.py` or the actual current equivalent) so only devices with:

```python
device.is_legacy is True
```

receive all currently required legacy libssh compatibility values:

```yaml
ansible_network_cli_ssh_type: libssh
ansible_libssh_key_exchange_algorithms: "+diffie-hellman-group14-sha1"
ansible_libssh_hostkeys: "ssh-rsa"
```

Normal/non-legacy devices must receive none of these SHA-1 compatibility settings.

Do not add:

```text
diffie-hellman-group1-sha1
ssh-dss
```

Do not globally weaken SSH configuration.

`ssh-rsa` here is required because the confirmed server host-key advertisement contains only `ssh-rsa`.

---

## Tests

Update/add tests proving:

1. Legacy device inventory contains:
   - `ansible_network_cli_ssh_type: libssh`
   - `ansible_libssh_key_exchange_algorithms: +diffie-hellman-group14-sha1`
   - `ansible_libssh_hostkeys: ssh-rsa`
2. Non-legacy devices do not contain `ansible_libssh_hostkeys`.
3. `ssh-dss` is not enabled.
4. `diffie-hellman-group1-sha1` remains absent.
5. YAML serialization preserves the values correctly.
6. All existing Phase 1/Phase 2/stabilization tests continue to pass.

No automated test may contact a real device.

---

## Validation

Run:

```bash
python3 -m compileall -q backend -x 'backend/venv'

cd backend
venv/bin/python -m pytest -q tests
```

Also show:

```bash
git diff --check
git status --short
git diff --stat
```

Do not commit or push.

---

## Manual acceptance

After rebuilding/restarting the Docker stack, run the same simulation against the lab device marked `is_legacy=true`.

Expected:

- the previous KEX mismatch does not return;
- the current `server host key algo` mismatch does not return;
- SSH proceeds further toward authentication / Cisco IOS module execution.

If the next error is specifically about a cipher, MAC, authentication method, privilege escalation, or host-key verification:

1. stop;
2. capture the exact error;
3. do not enable additional obsolete algorithms speculatively.

Do not perform a live push using destructive configuration merely to validate SSH.

---

## Scope

This is a narrow Phase 2 stabilization follow-up.

Do not change:

- proposal integrity;
- override workflow;
- pre-config backup behavior;
- RBAC;
- rollback;
- post-change verification;
- unrelated frontend code;
- database schema.

Do not commit or push.

## Suggested future commit message

After all Phase 2 manual acceptance passes:

```text
security: complete controlled deployment pipeline
```
