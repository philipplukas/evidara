FROM node:22-alpine@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f

# Build context is the repo root so shared design tokens at /styles/tokens/
# can be copied alongside the app.
WORKDIR /workspace

COPY styles/tokens ./styles/tokens

# Copy the shared `@evidara/brand-shell` package — it is declared as a
# `file:../../packages/brand-shell` dependency in the frontend's package.json,
# so `npm ci` needs the directory present before it can symlink it under
# `node_modules/@evidara/brand-shell`.
COPY packages/brand-shell ./packages/brand-shell

COPY legal-search/frontend/package*.json ./legal-search/frontend/
WORKDIR /workspace/legal-search/frontend
RUN npm ci

COPY legal-search/frontend ./

RUN npm run build

EXPOSE 8080

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]
