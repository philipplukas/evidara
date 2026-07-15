FROM node:22-alpine@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f

# Build context is the repo root so shared modules under /styles/ (design
# tokens plus the @evidara/ui shared module consumed by the app's StatusBadge
# shims) can be copied alongside the app. See ADR-0028.
WORKDIR /workspace

COPY styles/tokens ./styles/tokens
COPY styles/ui ./styles/ui
# styles/ui's bare imports (clsx, lucide-react, tailwind-merge) resolve during
# `next build` via `turbopack.resolveAlias` in next.config.ts, which pins them
# to THIS surface's node_modules. No repo-root node_modules is involved. See #588.

COPY legal-search/frontend/package*.json ./legal-search/frontend/
WORKDIR /workspace/legal-search/frontend
RUN npm ci

COPY legal-search/frontend ./

RUN npm run build

EXPOSE 8080

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]
