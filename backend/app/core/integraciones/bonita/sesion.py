from __future__ import annotations

import os
import threading

import httpx

from app.core.errores import RespuestaExternaInvalida, SistemaExternoRechazo
from app.core.integraciones.cliente_http import (
    COMPONENTE_BONITA,
    TIMEOUT_LECTURA_S,
    ejecutar_solicitud,
)

BONITA_BASE_URL = os.environ["BONITA_BASE_URL"].rstrip("/")
BONITA_USER = os.environ["BONITA_USER"]
BONITA_PASSWORD = os.environ["BONITA_PASSWORD"]
# Timeout de lectura hacia Bonita (configuracion.py lo valida como entero; 10 por defecto).
BONITA_TIMEOUT_S = float(os.environ.get("BONITA_TIMEOUT_S", TIMEOUT_LECTURA_S))

NOMBRE_COOKIE_TOKEN = "X-Bonita-API-Token"

_clientes: dict[str, httpx.Client] = {}
_lock = threading.Lock()


def iniciar_sesion(username: str) -> httpx.Client:
    cliente = httpx.Client()

    try:
        ejecutar_solicitud(
            cliente,
            componente=COMPONENTE_BONITA,
            metodo="POST",
            endpoint_normalizado="/loginservice",
            url=f"{BONITA_BASE_URL}/loginservice",
            idempotente=False,
            timeout_lectura_s=BONITA_TIMEOUT_S,
            data={
                "username": username,
                "password": BONITA_PASSWORD,
                "redirect": "false",
            },
        )
    except SistemaExternoRechazo:
        cliente.close()

        if username == BONITA_USER:
            raise

        return iniciar_sesion(BONITA_USER)

    token = cliente.cookies.get(NOMBRE_COOKIE_TOKEN)

    if not token:
        # Bonita acepto el login pero no devolvio X-Bonita-API-Token.
        cliente.close()
        raise RespuestaExternaInvalida(
            detalle={"componente": "bonita", "falta": NOMBRE_COOKIE_TOKEN}
        )

    cliente.headers[NOMBRE_COOKIE_TOKEN] = token

    return cliente


def obtener_cliente(username: str) -> httpx.Client:
    cliente = _clientes.get(username)

    if cliente is not None:
        return cliente

    with _lock:
        cliente = _clientes.get(username)

        if cliente is None:
            cliente = iniciar_sesion(username)
            _clientes[username] = cliente

        return cliente


def invalidar_sesion(username: str) -> None:
    with _lock:
        cliente = _clientes.pop(username, None)

        if cliente is not None:
            cliente.close()


def ejecutar_solicitud_bonita(
    *,
    username: str,
    metodo: str,
    endpoint_normalizado: str,
    url: str,
    idempotente: bool,
    **kwargs,
) -> httpx.Response:
    cliente = obtener_cliente(username)

    try:
        return ejecutar_solicitud(
            cliente,
            componente=COMPONENTE_BONITA,
            metodo=metodo,
            endpoint_normalizado=endpoint_normalizado,
            url=url,
            idempotente=idempotente,
            timeout_lectura_s=BONITA_TIMEOUT_S,
            **kwargs,
        )
    except SistemaExternoRechazo as exc:
        if exc.detalle.get("codigo_estado") != 401:
            raise

        # Descartar la sesión vencida.
        invalidar_sesion(username)

        # No repetir automáticamente operaciones no idempotentes.
        if not idempotente:
            raise

        # Renovar la sesión y reintentar operaciones idempotentes.
        cliente = obtener_cliente(username)

        return ejecutar_solicitud(
            cliente,
            componente=COMPONENTE_BONITA,
            metodo=metodo,
            endpoint_normalizado=endpoint_normalizado,
            url=url,
            idempotente=idempotente,
            timeout_lectura_s=BONITA_TIMEOUT_S,
            **kwargs,
        )
