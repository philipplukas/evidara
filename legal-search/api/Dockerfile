FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . ./
RUN npm run build

FROM node:22-alpine AS runtime

ENV NODE_ENV=production \
    PORT=8080

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY --from=build /app/dist ./dist

# Vocabularies needed at runtime (/contracts/vocabularies/*)
COPY contracts /contracts

EXPOSE 8080

CMD ["node", "dist/main.js"]
