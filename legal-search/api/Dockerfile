FROM node:22-alpine@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f AS build

WORKDIR /app

COPY legal-search/api/package*.json ./
RUN npm ci

COPY legal-search/api/ ./
RUN npm run build

FROM node:22-alpine@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f AS runtime

ENV NODE_ENV=production \
    PORT=8080

WORKDIR /app

COPY legal-search/api/package*.json ./
RUN npm ci --omit=dev

COPY --from=build /app/dist ./dist

# Vocabularies needed at runtime (/contracts/vocabularies/*)
COPY contracts /contracts

EXPOSE 8080

CMD ["node", "dist/main.js"]
