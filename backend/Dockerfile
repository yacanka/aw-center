# syntax=docker/dockerfile:1.7
# Docker Official Image multi-platform digests resolved on 2026-08-17. Updating a
# runtime requires an explicit, reviewed digest change instead of a mutable tag pull.
FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend-build

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

FROM python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7 AS python-deps

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install -r /tmp/requirements.txt \
    && python -m pip check

FROM python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    DJANGO_SETTINGS_MODULE=awcenter.settings \
    FRONTEND_DIST_DIR=/app/frontend-dist \
    STATIC_ROOT=/app/static

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ffmpeg \
        libmagic1 \
        poppler-utils \
        libreoffice \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-deps /opt/venv /opt/venv
COPY requirements.txt /app/requirements.txt

COPY backend /app
COPY --from=frontend-build /frontend/dist /app/frontend-dist

RUN mkdir -p /app/ai-models /app/document-templates /app/private_media /app/static \
    && export DEBUG=True \
        IPV4_ADDRESS=127.0.0.1 \
        PORT=8000 \
        DOCPROOF_URL=http://localhost/docproof \
        DOORS_EXECUTABLE=/usr/bin/false \
        JIRA_URL=http://localhost/jira-btb \
    && python manage.py collectstatic --clear --noinput \
    && python manage.py verify_frontend_artifact \
    && addgroup --system --gid 10001 awcenter \
    && adduser --system --uid 10001 --ingroup awcenter --home /nonexistent --no-create-home awcenter \
    && chmod -R a-w /app \
    && chown -R awcenter:awcenter /app/private_media \
    && chmod -R u+rwX /app/private_media

USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "awcenter.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--graceful-timeout", "30", "--error-logfile", "-"]
