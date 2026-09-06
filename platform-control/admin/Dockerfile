FROM node:22-alpine@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f

# Build context is the repo root so shared modules under /styles/ (design
# tokens plus the @evidara/ui shared module consumed by admin's Pill) can be
# copied alongside the app. See ADR-0028.
WORKDIR /workspace

# Copy shared tokens first so that changes to the app don't invalidate the
# token layer (and vice versa).
COPY styles/tokens ./styles/tokens
COPY styles/ui ./styles/ui
# @evidara/shell (shared BrandMark) resolves via the tsconfig path alias to
# ../../styles/shell; it must exist in the image or `next build` fails with
# "Can't resolve '@evidara/shell'". See #547.
COPY styles/shell ./styles/shell
# styles/ui's bare imports (clsx, lucide-react, tailwind-merge) resolve during
# `next build` via `turbopack.resolveAlias` in next.config.ts, which pins them
# to THIS surface's node_modules. No repo-root node_modules is involved. See #588.

# playwright.config.ts imports the shared run-identity helper from
# scripts/e2e/ (another module outside any package, same shape as styles/).
# `next build` type-checks it because tsconfig's include is `**/*.ts`, so the
# file must exist in the image or the build fails with "Cannot find module
# '../../scripts/e2e/playwright-server-identity.mjs'". See #719.
COPY scripts/e2e ./scripts/e2e

COPY platform-control/admin/package*.json ./platform-control/admin/
WORKDIR /workspace/platform-control/admin
RUN npm ci

COPY platform-control/admin ./

ENV PLATFORM_CONTROL_API_URL=http://platform-control-api:8000
# Default the operator role so authorized users (gated by the ingress BasicAuth /
# SSO front door) don't need the localStorage override. NEXT_PUBLIC_* is baked at build.
ENV NEXT_PUBLIC_USER_ROLE=admin
# Public legal-search URL for the "Back to legal search" cross-surface link.
# AdminShell is a client component, so this NEXT_PUBLIC_* must be inlined at
# BUILD time to reach the browser — a runtime Deployment env would not (same
# client-inlining constraint as NEXT_PUBLIC_USER_ROLE above). Unset, it falls
# back to the localhost:3101 dev default and sends real operators to their own
# machine. Override at build for other environments via --build-arg if needed.
ENV NEXT_PUBLIC_LEGAL_SEARCH_URL=https://search.evidara.veyo.dev
# MinIO console origin, used to deep-link a raw artifact's `storage_path` to the
# object itself. Same build-time inlining constraint as the two above.
#
# This host is tailnet-only, and that is deliberate rather than an oversight: the
# console needs its own credentials, so the audience for the link is exactly the
# operator who already has both. Leaving this UNSET is a fully supported
# configuration — `runDeepLinks` returns `null` and the column renders the same
# plain `s3://…` text it did before deep links existed. Do not substitute a
# default origin here; a link that asserts an object is reachable when it is not
# is worse than the text it replaced.
ENV NEXT_PUBLIC_MINIO_CONSOLE_URL=https://minio-evidara.ts.veyo.dev
RUN npm run build

EXPOSE 8080

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]
