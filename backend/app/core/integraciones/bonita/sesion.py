from __future__ import annotations

import os

import httpx

import threading

from app.core.integraciones.cliente_http import (
    COMPONENTE_BONITA,
    ejecutar_solicitud,
)

BONITA_BASE_URL = os.environ["BONITA_BASE_URL"].rstrip("/")
BONITA_USER = os.environ["BONITA_USER"]
BONITA_PASSWORD = os.environ["BONITA_PASSWORD"]

NOMBRE_COOKIE_TOKEN = "X-Bonita-API-Token"

_cliente: httpx.Client | None = None
_lock = threading.Lock()

def iniciar_sesion() -> httpx.Client:
    cliente = httpx.Client()

    ejecutar_solicitud(
        cliente,
        componente=COMPONENTE_BONITA,
        metodo="POST",
        endpoint_normalizado="/loginservice",
        url=f"{BONITA_BASE_URL}/loginservice",
        idempotente=False,
        data={
            "username": BONITA_USER,
            "password": BONITA_PASSWORD,
            "redirect": "false",
        },
    )

    token = cliente.cookies.get(NOMBRE_COOKIE_TOKEN)

    if not token:
        cliente.close()
        raise RuntimeError(
            "Bonita inició sesión pero no devolvió X-Bonita-API-Token."
        )

    cliente.headers[NOMBRE_COOKIE_TOKEN] = token

    return cliente

def obtener_cliente() -> httpx.Client:
    global _cliente

    if _cliente is not None:
        return _cliente

    with _lock:
        # Otra request pudo haber iniciado sesión mientras esperábamos el lock.
        if _cliente is None:
            _cliente = iniciar_sesion()

        return _cliente