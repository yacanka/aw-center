# syntax=docker/dockerfile:1.7
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=awcenter.settings

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libmagic1 \
        poppler-utils \
        libreoffice \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

COPY backend /app

RUN mkdir -p /app/media /app/static \
    && adduser --disabled-password --gecos "" awcenter \
    && chown -R awcenter:awcenter /app

USER awcenter
EXPOSE 8000

CMD ["gunicorn", "awcenter.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
