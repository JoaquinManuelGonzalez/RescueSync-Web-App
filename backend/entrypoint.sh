#!/bin/sh
# Punto de entrada del contenedor web.
#
# "set -e" hace que una migracion fallida termine el contenedor
# con codigo distinto de cero en vez de dejarlo sirviendo peticiones contra un esquema a medias.
set -e

echo "[entrypoint] Aplicando migraciones pendientes..."
flask db upgrade
echo "[entrypoint] Migraciones al dia. Iniciando la aplicacion..."

exec "$@"
