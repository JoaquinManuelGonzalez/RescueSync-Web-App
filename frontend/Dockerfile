# syntax=docker/dockerfile:1.9
# Compilador de Tailwind CSS. Corre en modo watch durante el desarrollo y deja el CSS
# compilado en frontend/estaticos/css/app.css, que es lo que sirve Flask.

FROM node:22-alpine

# Las dependencias se instalan en la RAIZ del contenedor, no dentro de /frontend
WORKDIR /
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

ENV PATH="/node_modules/.bin:$PATH"

# El bucle de recompilacion se copia a la imagen en vez de ejecutarse desde el bind mount,
# para que la imagen funcione por si sola.
COPY observar.sh /usr/local/bin/observar.sh
RUN chmod +x /usr/local/bin/observar.sh

WORKDIR /frontend

CMD ["/usr/local/bin/observar.sh"]
