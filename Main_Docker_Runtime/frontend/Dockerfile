# Stage 1: Node.js 22 환경에서 Vite로 빌드
FROM node:22-alpine AS build-stage
WORKDIR /app

COPY frontend/package*.json ./frontend/
WORKDIR /app/frontend
RUN npm install

WORKDIR /app
COPY frontend ./frontend
COPY setting ./setting

WORKDIR /app/frontend
RUN npm run build

# Stage 2: Nginx에 배포
FROM nginx:alpine
COPY --from=build-stage /app/frontend/dist /usr/share/nginx/html