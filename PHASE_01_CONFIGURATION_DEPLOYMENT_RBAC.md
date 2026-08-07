# VNMS Hardening Roadmap — Phase 1

## Phase title

**Enforce server-side authorization for live configuration deployment**

## Instructions to Codex

Work directly in the existing VNMS repository. Implement this phase completely, but keep the change small, reviewable, and compatible with the current architecture.

Do not stop at recommendations. Inspect the repository, make the required code changes, add or update tests, run all safe local checks available in the repository, and report exactly what changed.

**Do not commit, push, merge, rebase, or modify Git history.** The developer will review and test the work before committing it.

---

## Product context

VNMS is an AI-assisted network automation platform. AI-generated configuration is an untrusted proposal. Ansible is the controlled execution engine.

The intended safety boundary is:

1. A user prepares or generates a proposed configuration.
2. The proposal can be simulated with Ansible check/diff mode.
3. A live production deployment requires stronger authorization.
4. Frontend controls improve usability, but backend authorization is authoritative.
5. A rejected request must never reach Ansible or a network device.

The current application has two roles: `admin` and `viewer`.

---

## Confirmed current behavior to verify in the repository

Before editing, inspect the actual files and confirm the current implementation. File locations may differ from the names below.

Expected relevant files include:

- `routers/configuration.py`
- `routers/auth.py`
- `schemas.py`
- `ansible_engine.py`
- `src/components/Configuration.jsx`
- Existing backend and frontend test directories
- Dependency manifests and test configuration

The current backend configuration routes are expected to include:

- `POST /configuration/generate`
- `POST /configuration/simulate`
- `POST /configuration/push`

The current implementation appears to authenticate all three routes with `get_current_user`. The live push route therefore does not enforce administrator privileges at the API boundary.

The frontend currently appears to calculate one shared execution permission similar to:

```javascript
const canExecute =
  userRole === 'admin' ||
  (userRole === 'viewer' && loadedTemplate !== null);
```

That shared value is used for both simulation and production deployment, which can expose the production push action to a viewer after loading a template.

Treat the repository code as the source of truth. If the implementation differs, adapt the smallest safe change while preserving the requirements below.

---

## Objective

Enforce the following policy:

| Capability | Unauthenticated | Viewer | Admin |
|---|---:|---:|---:|
| Generate an AI proposal | Denied | Allowed | Allowed |
| Simulate with Ansible check/diff | Denied | Allowed | Allowed |
| Push live configuration | Denied | Denied | Allowed |

The backend must enforce this policy regardless of frontend state, browser local storage, request payload, template name, or manually constructed API requests.

---

## Required implementation

### 1. Inspect before changing

First inspect:

- Repository structure
- README and developer documentation
- Python and JavaScript dependency manifests
- Existing authentication dependencies
- Existing route tests
- Existing frontend test setup
- Current configuration execution and streaming behavior
- Current audit logging behavior

Preserve existing interfaces and behavior unless this phase explicitly requires a change.

Do not perform a broad refactor.

### 2. Enforce authorization on the backend

Update the live configuration deployment route so that:

```text
POST /configuration/push
```

requires the existing administrator authorization dependency, expected to be `get_current_admin`.

Requirements:

- A missing or invalid token returns `401`.
- An authenticated non-admin user returns `403`.
- An authenticated admin may enter the existing push workflow.
- Authorization must occur before:
  - Parsing or executing the proposed device commands where practical
  - Calling `run_ansible_playbook`
  - Opening SSH connections
  - Starting a streaming deployment response
  - Making any change to a network device
- Do not trust a role supplied in request JSON, headers other than the verified bearer token, browser local storage, `source_template`, or a template name.
- Preserve the authenticated administrator username for audit attribution.
- Keep `generate` and `simulate` available to any authenticated user.
- Do not weaken authorization on any other route.

Prefer the existing authentication dependency rather than creating a duplicate role-checking system.

### 3. Make frontend permissions accurately reflect backend policy

Update the Configuration UI so simulation and production deployment use separate permissions.

Use clear concepts such as:

```javascript
const canSimulate = /* authenticated workflow rules */;
const canPush = userRole === 'admin';
```

Requirements:

- A viewer must not be able to initiate a production push from the UI.
- Prefer hiding the production button for viewers. A clearly disabled button with an explanatory message is acceptable if that better matches the existing UI.
- A viewer must still be able to simulate an otherwise valid proposal.
- An admin must retain both simulation and production push controls.
- Preserve the existing production confirmation dialog for admins.
- Frontend permissions are only a usability layer; do not treat them as the security control.
- Handle a backend `403` response clearly, without showing a misleading generic network error.
- Do not derive administrator access from a username such as `admin`; use the authenticated role already supplied to the component.
- Do not redesign the page or introduce an unrelated styling framework.

Where the current UI intentionally requires viewers to load an approved template before generating or simulating, preserve that restriction unless it directly conflicts with the policy above. Regardless of that UI restriction, live push remains admin-only.

### 4. Preserve execution safety and streaming behavior

Do not rewrite `run_ansible_playbook` or the server-sent event streaming implementation during this phase.

Preserve:

- Simulation using Ansible check mode
- Production push using normal execution mode
- Existing configuration payload validation
- Existing event logging
- Existing target selection
- Existing multi-vendor behavior
- Existing response media type and frontend stream parsing

Do not add actual device connections to tests.

### 5. Add backend authorization tests

Use the repository's existing test conventions. If no backend tests exist, create the smallest maintainable pytest structure using FastAPI's test tooling and dependency overrides.

At minimum, add tests proving:

1. `POST /configuration/push` without authentication returns `401`.
2. `POST /configuration/push` as a viewer returns `403`.
3. A viewer rejection occurs before `run_ansible_playbook` is called.
4. `POST /configuration/push` as an admin passes authorization and reaches the mocked execution boundary.
5. `POST /configuration/simulate` remains accessible to an authenticated viewer.
6. `POST /configuration/generate` remains protected by authentication.

Test isolation requirements:

- Do not contact real network devices.
- Do not invoke a real Ansible process.
- Do not invoke a real AI provider.
- Mock at the narrowest stable boundary.
- Do not use production credentials.
- Avoid relying on the repository's real SQLite database when dependency overrides or a temporary test database are practical.
- Assert both HTTP status and whether the mocked executor was called.
- Ensure mocks are restored between tests.

For streaming endpoints, it is acceptable to mock the generator with a minimal deterministic SSE-compatible stream.

### 6. Add or update frontend tests when supported

If the repository already has a frontend test framework, add tests proving:

- Viewer sees or can use simulation.
- Viewer cannot invoke production push.
- Admin can see and invoke the production push control.
- A `403` response is presented clearly.

If no frontend test framework exists, do not add a large dependency stack only for this phase. Instead:

- Keep the frontend change simple.
- Run the existing lint/build commands.
- Include exact manual UI test steps in the completion report.

### 7. Audit and error handling

Preserve successful deployment audit attribution to the authenticated administrator.

Do not log:

- Access tokens
- Passwords
- Decrypted device credentials
- Encryption keys
- Complete sensitive environment variables

A denied viewer request should return a clear `403` response such as the existing administrator dependency message. Do not expose internal tracebacks.

Do not introduce broad `except Exception: pass` handling.

---

## Explicit non-goals

Do not implement any of the following in Phase 1:

- Approval database models
- Two-person approval
- Proposal hashing
- Simulation-to-push binding
- Automatic backup before push
- Automatic rollback
- Post-change verification
- Risky-command classification
- Worker queues or Celery/RQ migration
- JWT secret redesign
- Device encryption-key redesign
- SSH host-key redesign
- AI configuration redaction
- Multi-vendor command changes
- Database migration framework
- Global RBAC redesign
- Frontend routing redesign
- Central API client refactor
- Cosmetic page redesign
- Unrelated cleanup

These belong in later phases. Note relevant findings in the final report, but do not mix them into this change.

---

## Expected files

Modify only files required by the implementation. Likely candidates are:

- Backend configuration router
- Frontend Configuration component
- Backend authorization tests
- Existing frontend tests, if a framework is already present
- Minimal test configuration only when necessary

Do not modify generated files, archives, logs, databases, secrets, or device configuration backups.

---

## Validation commands

Discover and use the repository's real commands rather than assuming paths. Run the applicable equivalents of:

```bash
# Backend syntax
python -m compileall .

# Backend tests
pytest -q

# Frontend dependency install only if dependencies are not already installed
npm ci

# Frontend checks
npm run lint
npm run test -- --run
npm run build
```

Rules:

- Do not claim a command passed unless it was actually run.
- Do not use real devices to validate this phase.
- Do not run production deployment.
- Do not run tests that contact an external AI service.
- If a command is unavailable or fails because of a pre-existing issue, record the exact command and concise failure reason.
- Distinguish pre-existing failures from failures introduced by this phase.

---

## Manual acceptance test

Provide exact API commands adapted to the repository's authentication response. Use safe mocked/lab conditions only.

Verify:

1. Log in as a viewer.
2. Attempt `POST /configuration/push` directly with the viewer token.
3. Confirm HTTP `403`.
4. Confirm no Ansible process starts and no device is contacted.
5. Open the Configuration page as viewer.
6. Confirm simulation remains available under the existing viewer/template rules.
7. Confirm production push is hidden or disabled.
8. Log in as admin.
9. Confirm simulation remains available.
10. Confirm production push is visible.
11. Cancel the confirmation dialog and verify no request is sent.
12. In a test or mocked environment, accept the dialog and confirm the request reaches the existing push workflow.

Do not use a production device for this acceptance test.

---

## Definition of done

Phase 1 is complete only when all of the following are true:

- Backend live deployment is admin-only.
- Viewer direct API calls receive `403`.
- Unauthenticated direct API calls receive `401`.
- Denied calls cannot reach Ansible.
- Viewer simulation still works.
- Admin simulation and push behavior remain available.
- Frontend accurately reflects the server policy.
- Existing streaming behavior is preserved.
- Tests cover the authorization boundary.
- Safe local checks have been run and honestly reported.
- No secrets were added.
- No unrelated refactor was performed.
- No Git commit or push was performed.

---

## Required completion report

When implementation is finished, respond with this structure:

### Summary

A concise description of the implemented security boundary.

### Files changed

For each file:

- Path
- What changed
- Why it changed

### Authorization behavior

Show the resulting unauthenticated/viewer/admin behavior for generate, simulate, and push.

### Tests added

List each new or modified test and what it proves.

### Commands executed

For every command:

- Exact command
- Pass/fail status
- Relevant output summary

### Manual test procedure

Provide exact steps and safe sample API commands.

### Risks and compatibility notes

Mention any behavior change, especially the loss of viewer production deployment.

### Deferred findings

List relevant issues deliberately left for later phases.

### Git status

Show:

```bash
git status --short
git diff --stat
```

Do not commit or push.

---

## Suggested future commit message

After human review and testing pass:

```text
security: restrict live configuration deployment to admins
```
