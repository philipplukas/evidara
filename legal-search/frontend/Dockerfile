FROM node:22-alpine

# Build context is the repo root so shared design tokens at /styles/tokens/
# can be copied alongside the app.
WORKDIR /workspace

COPY styles/tokens ./styles/tokens

COPY legal-search/frontend/package*.json ./legal-search/frontend/
WORKDIR /workspace/legal-search/frontend
RUN npm ci

COPY legal-search/frontend ./

RUN npm run build

EXPOSE 8080

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]
