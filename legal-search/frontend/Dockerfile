FROM node:22-alpine AS deps
WORKDIR /app

COPY package*.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app

ENV NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=8080

COPY --from=builder /app ./
RUN addgroup -g 1001 -S app && adduser -S -u 1001 -G app app && chown -R app:app /app
USER app

EXPOSE 8080
CMD ["npm", "run", "start", "--", "-p", "8080", "-H", "0.0.0.0"]
