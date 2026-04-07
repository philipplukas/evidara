FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 8080

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]
