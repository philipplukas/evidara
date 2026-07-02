FROM node:22-alpine@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f

# Build context is the repo root so shared modules under /styles/ (design
# tokens plus the @evidara/ui shared module consumed by admin's Pill) can be
# copied alongside the app. See ADR-0028.
WORKDIR /workspace

# Copy shared tokens first so that changes to the app don't invalidate the
# token layer (and vice versa).
COPY styles/tokens ./styles/tokens
COPY styles/ui ./styles/ui
# postinstall (in package.json) symlinks /workspace/node_modules -> the
# surface's node_modules so styles/ui's bare imports (clsx, tailwind-merge)
# resolve during `next build`. Copy the script into the build context so
# `npm ci` doesn't fail looking for it.
COPY scripts/ensure-monorepo-shared-modules.mjs ./scripts/ensure-monorepo-shared-modules.mjs

COPY platform-control/admin/package*.json ./platform-control/admin/
WORKDIR /workspace/platform-control/admin
RUN npm ci

COPY platform-control/admin ./

ENV PLATFORM_CONTROL_API_URL=http://platform-control-api:8000
# Default the operator role so authorized users (gated by the ingress BasicAuth /
# SSO front door) don't need the localStorage override. NEXT_PUBLIC_* is baked at build.
ENV NEXT_PUBLIC_USER_ROLE=admin
RUN npm run build

EXPOSE 8080

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]
