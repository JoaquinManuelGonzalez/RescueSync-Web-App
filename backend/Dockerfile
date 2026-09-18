# syntax=docker/dockerfile:1.9
# Imagen de la aplicacion web de RescueSync.
#
# Dos targets:
#   desarrollo -> incluye el grupo dev (ruff, pytest) y arranca el servidor de Flask con recarga
#   produccion -> sin dependencias de desarrollo, arranca gunicorn
#
# docker-compose.yml usa "target: desarrollo". El target "produccion" queda listo para la Entrega 3.

ARG PYTHON_IMAGE=python:3.14-slim-trixie
ARG UV_VERSION=0.12.13

# ---------------------------------------------------------------------------
# base: interprete + uv + variables comunes
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

# UV_PROJECT_ENVIRONMENT apunta FUERA de /app a proposito: en desarrollo /app es un
# bind mount y un entorno virtual creado ahi dentro quedaria tapado por la carpeta del host.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.wsgi:app

# El uid/gid por defecto coincide con el primer usuario de la mayoria de los escritorios Linux,
# para que los archivos que el contenedor escriba en el bind mount (por ejemplo una migracion
# nueva) queden a nombre del usuario del host. En Windows y macOS es indistinto.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" rescuesync \
    && useradd --uid "${UID}" --gid "${GID}" --create-home rescuesync

WORKDIR /app

# ---------------------------------------------------------------------------
# dependencias: capa cacheada, independiente del codigo fuente
# ---------------------------------------------------------------------------
FROM base AS dependencias-desarrollo
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-install-project

FROM base AS dependencias-produccion
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-install-project --no-dev

# ---------------------------------------------------------------------------
# desarrollo
# ---------------------------------------------------------------------------
FROM dependencias-desarrollo AS desarrollo

COPY --chown=rescuesync:rescuesync entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# El codigo llega por bind mount desde docker-compose.yml. Se copia igual para que la imagen
# sirva por si sola si alguien la corre sin compose.
COPY --chown=rescuesync:rescuesync . /app

USER rescuesync
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["sh", "-c", "flask run --debug --host 0.0.0.0 --port ${APP_PORT:-5000}"]

# ---------------------------------------------------------------------------
# produccion
# ---------------------------------------------------------------------------
FROM dependencias-produccion AS produccion

COPY --chown=rescuesync:rescuesync entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
COPY --chown=rescuesync:rescuesync . /app

USER rescuesync
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${APP_PORT:-5000} --access-logfile - app.wsgi:app"]
