# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM dependencies AS build
ARG VITE_API_URL=/
ARG VITE_VERSION=container
ARG VITE_APP_TITLE="AW Center"
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_VERSION=${VITE_VERSION} \
    VITE_APP_TITLE=${VITE_APP_TITLE}
COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine AS static
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
