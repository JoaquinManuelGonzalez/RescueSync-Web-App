"""Healthcheck del contenedor web, usado por docker-compose.yml.

Vive como script y no como un one-liner dentro del YAML para que se pueda leer y probar.
"""

from __future__ import annotations

import os
import sys
import urllib.request

PUERTO = os.environ.get("APP_PORT", "5000")
URL = f"http://127.0.0.1:{PUERTO}/health"

try:
    with urllib.request.urlopen(URL, timeout=3) as respuesta:
        sys.exit(0 if respuesta.status == 200 else 1)
except Exception:
    sys.exit(1)
