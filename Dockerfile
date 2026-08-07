FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system pharmagent && useradd --system --gid pharmagent pharmagent

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

RUN chown -R pharmagent:pharmagent /app
USER pharmagent

EXPOSE 8000

# Forma shell (no exec) a propósito: expande `${PORT:-8000}` — Render/Cloud Run inyectan
# `PORT` y esperan que el contenedor escuche ahí; en local (docker-compose, sin `PORT`
# definido) cae al 8000 de siempre. Aplica las migraciones antes de arrancar Uvicorn —
# antes vivía como `command:` en docker-compose.yml; se centraliza aquí para que cualquier
# plataforma que solo sepa ejecutar la imagen (Render, Cloud Run) migre igual que local, sin
# tener que replicar el comando en cada sitio.
CMD sh -c "alembic upgrade head && uvicorn src.infrastructure.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
