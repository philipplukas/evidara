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

## Role-aware admin access

The admin surface now renders an explicit `403 Forbidden` state for non-admin roles, including a
"Return to legal search" recovery link.

Environment variables:

- `NEXT_PUBLIC_ADMIN_ALLOWED_ROLES`: comma-separated roles allowed to open the admin surface
  (default: `admin`)
- `NEXT_PUBLIC_USER_ROLE`: fallback current role for local/dev
- `NEXT_PUBLIC_LEGAL_SEARCH_URL`: recovery link target for denied users, and the origin
  a run's `document_id` deep-links to (`/?item=<document_id>`)
- `NEXT_PUBLIC_MINIO_CONSOLE_URL`: MinIO console origin, used to deep-link a raw
  artifact's `storage_path` to the object. **No default** — unset means the column
  renders plain `s3://…` text instead of a link

All `NEXT_PUBLIC_*` vars are read in exactly one place, `src/config/publicConfig.ts`, and
must be inlined at **build** time (a runtime Deployment env does not reach the browser).
A test in `publicConfig.test.ts` fails if any other module reads `process.env.NEXT_PUBLIC_*`
directly.

Both deep-link targets degrade to plain text when unconfigured rather than falling back to a
default origin — a link that asserts a target is reachable when it is not is worse than the
text it replaced. See `src/resources/runs/runDeepLinks.ts`.

Local override for acceptance testing:

- set `localStorage["evidara_user_role"]` in the browser to simulate admin vs non-admin behavior

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
- deep links out of those diagnostics to the system each row names:
  - `document_id` (processing status, document lifecycle) → the document in legal-search
  - `storage_path` (raw artifacts) → the object in the MinIO console
  - both require their base URL to be configured; unset renders plain text

There is deliberately **no** run-scoped log link: the cluster runs kube-prometheus-stack
with no Loki, so no such query exists to link to.
