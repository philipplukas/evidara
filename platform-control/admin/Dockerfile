FROM node:22-alpine

# Build context is the repo root so shared design tokens at /styles/tokens/
# can be copied alongside the app.
WORKDIR /workspace

# Copy shared tokens first so that changes to the app don't invalidate the
# token layer (and vice versa).
COPY styles/tokens ./styles/tokens

COPY platform-control/admin/package*.json ./platform-control/admin/
WORKDIR /workspace/platform-control/admin
RUN npm ci

COPY platform-control/admin ./

ENV PLATFORM_CONTROL_API_URL=http://platform-control-api:8000
RUN npm run build

EXPOSE 8080

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]
