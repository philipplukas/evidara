FROM node:22-alpine AS build

WORKDIR /app

COPY legal-search/api/package*.json ./
RUN npm ci

COPY legal-search/api/ ./
RUN npm run build

FROM node:22-alpine AS runtime

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
