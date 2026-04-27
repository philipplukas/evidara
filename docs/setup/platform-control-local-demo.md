# Platform-Control Local Demo Setup

## Purpose

Set up the `platform-control` API and the code-managed `platform-control/admin` app for a local
demo, using the repo's local Postgres service so the API and admin UI read from the same backend
state.

## Prerequisites

| Requirement | Version | How to install |
|------------|---------|---------------|
| Python | 3.12+ | Use your preferred Python installer |
| `uv` | recent | `python -m pip install uv` |
| Node.js + npm | 22+ recommended | Needed for `platform-control/admin` |
| Docker | recent | Needed for the local Postgres service |
| Docker Compose | recent | Used through `docker compose` |
| Postgres database | 16+ recommended | Provided by the repo's Compose file |

## Local Demo Model

The recommended local demo path is now:

1. start Postgres via the repo's root Compose file
2. run `platform-control` on the host with auto-reload
3. run `platform-control/admin` as the primary code-managed UI

This keeps the Python edit loop fast while moving the operator UI toward the React-admin target
defined in ADR-0015.

## Steps

### 1. Install dependencies

Start the shared local services from the repo root:

```bash
bash scripts/platform-control-demo.sh up
```

Then install Python dependencies:

```bash
bash scripts/platform-control-demo.sh sync
```

### 2. Configure the local API

Start from the checked-in example:

```bash
cp platform-control/.env.example platform-control/.env
```

The checked-in `.env.example` now targets the Compose-backed local Postgres instance:

```text
PLATFORM_CONTROL_DATABASE_URL=postgresql+asyncpg://platform_control:platform_control@127.0.0.1:5432/platform_control
PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=local
PLATFORM_CONTROL_RAW_ARTIFACT_LOCAL_DIR=.data/raw-artifacts
PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=noop
```

### 3. Run database migrations

```bash
bash scripts/platform-control-demo.sh migrate
```

### 4. Seed reference data

```bash
bash scripts/platform-control-demo.sh seed-dry-run
bash scripts/platform-control-demo.sh seed
```

### 5. Start the API

```bash
bash scripts/platform-control-demo.sh api
```

### 6. Verify the local API

In a second terminal:

```bash
bash scripts/platform-control-demo.sh health
```

**Expected output:**

```json
{"status":"ok","service":"platform-control"}
```

### 7. Choose the demo path

#### API and DB local demo

Use the backend directly and rely on the smoke-tested flows already in the repo.

Recommended verification:

```bash
bash scripts/check-platform-control.sh
```

This validates:

- preview success and preview summary
- preview failure handling
- production run creation
- downstream DI processing-status visibility
- document lifecycle visibility

#### React-admin-backed demo

Install and start the admin app:

```bash
bash scripts/platform-control-demo.sh admin-sync
bash scripts/platform-control-demo.sh admin
```

The admin app runs on `http://127.0.0.1:3100` by default and proxies
`/api/platform-control/*` to the local FastAPI backend.

Today the code-managed admin covers the main operator slice:

- `Jurisdictions` and `Authorities`
- `Sources`
- embedded `Source Versions` create/edit/approve/reject actions
- preview and production run creation from source-version rows
- dedicated `Preview approvals` page for preview-run triage
- `Runs` list
- direct run creation from the `Runs` page
- run cancellation
- `Run Detail`
- `Preview Summary` review for preview runs
- API-backed filtering by run mode and status
- `Run Detail` diagnostics for provider jobs, captured resources, raw artifacts, DI status, and document lifecycle

#### Retool artifacts reference

Retool is no longer part of the primary operator setup. If you need historical context while
retiring the old workflow, the archived artifacts remain under:

- `platform-control/retool/control-panel.manifest.yaml`
- `platform-control/retool/SETUP.md`
- `platform-control/retool/sql/`
- `platform-control/retool/workflows/run_firecrawl_preview.yaml`
- `platform-control/retool/agents/source-setup-copilot.md`

## Demo Script

### Preview approvals

1. Create or select reference data in `Jurisdictions` and `Authorities` if needed.
2. Create a source in `Sources`.
3. Create or edit a source version and confirm the detail shows `extractor_profile_id` and acquisition config.
4. Approve or reject the source version from the `Source` detail screen when appropriate.
5. Trigger a preview run from the source-version row.
6. Open the created run and review the `Preview Summary` heuristics and drift checks.
7. Inspect captured resources, raw artifacts, and provider-job state in `Run Detail`.

### Production run and DI monitoring

1. Approve a source version.
2. Trigger a production run from the source-version row.
3. Open `Runs` or the created run detail.
4. Cancel the run from the list or detail screen if needed while it is still pending/running.
5. Confirm provider jobs, captured resources, and raw artifacts are visible when present.
6. Confirm DI processing-status and document lifecycle sections are visible.

## Common Issues

| Problem | Solution |
|---------|---------|
| Postgres is not reachable | Start it from the repo root with `bash scripts/platform-control-demo.sh up`. |
| API starts but tables are missing | Run `bash scripts/platform-control-demo.sh migrate` before starting the demo. |
| Seed command fails | Check that `.env` points at the intended database and rerun the dry-run first. |
| Admin app cannot reach the API | Confirm `bash scripts/platform-control-demo.sh api` is running and `platform-control/admin/.env.local` points at `http://127.0.0.1:8000` if overridden. |
| Preview runs do not complete locally | A real interactive preview demo needs Firecrawl credentials, webhook secret, and a reachable webhook URL. |

## Next Steps

After setup is complete:

- Use `platform-control/admin/README.md` for admin app commands and local proxy behavior
- Use [Firecrawl Preview Run](../runbooks/firecrawl-preview-run.md) when debugging preview execution
- Use `bash scripts/platform-control-demo.sh bootstrap` when you want the shortest local bring-up path
- Use `platform-control/retool/` only as archived reference material while the remaining Retool docs are retired
