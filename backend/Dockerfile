# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

ARG VITE_API_URL=/
ARG VITE_VERSION=container
ARG VITE_APP_TITLE="AW Center"
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_VERSION=${VITE_VERSION} \
    VITE_APP_TITLE=${VITE_APP_TITLE}

RUN npm run build

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=awcenter.settings \
    FRONTEND_DIST_DIR=/app/frontend-dist \
    STATIC_ROOT=/app/static

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ffmpeg \
        libmagic1 \
        poppler-utils \
        libreoffice \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

COPY backend /app
COPY --from=frontend-build /frontend/dist /app/frontend-dist

RUN mkdir -p /app/media /app/models /app/private_media /app/static \
    && export DEBUG=True \
        IPV4_ADDRESS=127.0.0.1 \
        PORT=8000 \
        DOCPROOF_URL=http://localhost/docproof \
        DOORS_EXECUTABLE=/usr/bin/false \
        JIRA_LEGACY_URL=http://localhost/jira-legacy \
        JIRA_BTB_URL=http://localhost/jira-btb \
    && python manage.py collectstatic --noinput \
    && python manage.py verify_frontend_artifact \
    && adduser --disabled-password --gecos "" awcenter \
    && chown -R awcenter:awcenter /app

USER awcenter
EXPOSE 8000

CMD ["gunicorn", "awcenter.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
