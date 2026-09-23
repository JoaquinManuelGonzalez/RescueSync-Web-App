#!/bin/sh
# Recompila Tailwind cuando cambia una plantilla o el CSS fuente.
#
# Este bucle compara marcas de tiempo cada pocos segundos.
set -e

ENTRADA="./src/input.css"
SALIDA="./estaticos/css/app.css"
MARCA="/tmp/marca-tailwind"
INTERVALO="${INTERVALO_WATCH_S:-2}"

mkdir -p "$(dirname "$SALIDA")"

echo "[tailwind] compilacion inicial..."
tailwindcss -i "$ENTRADA" -o "$SALIDA"
touch "$MARCA"
echo "[tailwind] vigilando ./src, ./plantillas y ./estaticos/js cada ${INTERVALO}s"

while true; do
    sleep "$INTERVALO"

    # -newer detecta tanto archivos modificados como archivos nuevos.
    if [ -n "$(find ./src ./plantillas ./estaticos/js -type f -newer "$MARCA" 2>/dev/null)" ]; then
        touch "$MARCA"
        echo "[tailwind] cambio detectado, recompilando..."
        tailwindcss -i "$ENTRADA" -o "$SALIDA"
    fi
done
