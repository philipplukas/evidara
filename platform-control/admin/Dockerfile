FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
ENV PLATFORM_CONTROL_API_URL=http://platform-control-api:8000
RUN npm run build

EXPOSE 8080

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]
