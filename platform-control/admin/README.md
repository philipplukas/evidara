# Platform-Control Admin

Code-managed React-admin frontend for the Evidara control plane.

## Local development

1. Start the backend stack:

   ```bash
   bash ../../scripts/platform-control-demo.sh bootstrap
   bash ../../scripts/platform-control-demo.sh api
   ```

2. Install admin dependencies:

   ```bash
   cd platform-control/admin
   npm ci
   ```

3. Copy the local environment file:

   ```bash
   cp .env.example .env.local
   ```

4. Run the admin app:

   ```bash
   npm run dev
   ```

The Next.js app proxies `/api/platform-control/*` to `PLATFORM_CONTROL_API_URL`, so the browser
never needs direct database access or direct cross-origin calls to FastAPI.

## Runtime deployment

- Container image: `platform-control/admin/Dockerfile`
- Required runtime env var: `PLATFORM_CONTROL_API_URL`
- Cloud Run service key: `platform-control-admin` (dev/staging tfvars)

## Current coverage

The current React-admin slice includes:

- `Jurisdictions` list/create/edit
- `Authorities` list/create/edit
- `Sources` list/create/show
- jurisdiction-filtered authority selection during source creation
- embedded `Source Versions` management inside `Source` detail
- preview and production run creation from source-version rows
- dedicated `Preview Review` list/show flow for preview runs
- `Runs` list with `mode` and `status` filtering
- run creation directly from the `Runs` page
- run cancellation from the list and detail screens
- `Run Detail` summary
- `Preview Summary` review for preview runs
- `Run Detail` diagnostics for:
  - provider jobs
  - captured resources
  - raw artifacts
  - DI processing status
  - document lifecycle
