"""Carga y validacion de la configuracion de la aplicacion.

Implementa docs/contratos/configuracion.md. La fuente de verdad de que variable existe, si es
obligatoria y cual es su valor por defecto es la tabla de la seccion 1 de ese documento: este
modulo la refleja y no la reinterpreta.
"""

from __future__ import annotations

import logging
import os
import sys

from app.core.logging import configurar_logging, registrar_evento

# Variables obligatorias: sin valor por defecto. Si falta una sola, la aplicacion no arranca.
VARIABLES_OBLIGATORIAS: tuple[str, ...] = (
    "SECRET_KEY",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "BONITA_BASE_URL",
    "BONITA_USER",
    "BONITA_PASSWORD",
    "BONITA_CALLBACK_TOKEN",
    "API_NACIONAL_BASE_URL",
    "API_NACIONAL_CLIENT_ID",
    "API_NACIONAL_CLIENT_SECRET",
)

VARIABLES_OPCIONALES: dict[str, str] = {
    "APP_ENV": "local",
    "APP_PORT": "5000",
    "LOG_LEVEL": "INFO",
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "rescuesync",
    "BONITA_PROCESO_NOMBRE": "GestionDeEmergencia",
    "BONITA_PROCESO_VERSION": "1.0",
    "BONITA_TIMEOUT_S": "10",
    "API_NACIONAL_TIMEOUT_S": "10",
    "API_NACIONAL_REINTENTOS": "2",
    "API_NACIONAL_BACKOFF_MS": "500",
}


VARIABLES_ENTERAS: tuple[str, ...] = (
    "APP_PORT",
    "POSTGRES_PORT",
    "BONITA_TIMEOUT_S",
    "API_NACIONAL_TIMEOUT_S",
    "API_NACIONAL_REINTENTOS",
    "API_NACIONAL_BACKOFF_MS",
)

MENSAJE_FALTANTE = "Falta la variable de entorno obligatoria: {nombre}"
MENSAJE_NO_ENTERA = "La variable de entorno {nombre} debe ser un numero entero"


def _leer(nombre: str) -> str:
    """Lee una variable tratando la cadena vacia y los espacios como ausencia."""
    return (os.environ.get(nombre) or "").strip()


def obtener_faltantes() -> list[str]:
    """Nombres de las variables obligatorias ausentes o vacias, en el orden del contrato."""
    return [nombre for nombre in VARIABLES_OBLIGATORIAS if not _leer(nombre)]


def _terminar(mensajes: list[str]) -> None:
    """Loguea el fallo y corta el proceso con codigo distinto de cero.

    Se emite en dos formatos a proposito:
    - una linea JSON por problema, porque lo exige el contrato de logging;
    - la misma linea en texto plano a stderr, para que sea legible en `docker compose logs`
      sin tener que parsear JSON.

    Nunca se loguea el *valor* de ninguna variable: podrian ser secretos a medio completar.
    """
    configurar_logging(_leer("LOG_LEVEL") or "INFO")
    for mensaje in mensajes:
        registrar_evento(logging.ERROR, "configuracion_invalida", mensaje)
        print(mensaje, file=sys.stderr, flush=True)
    sys.exit(1)


def construir_configuracion() -> dict[str, object]:
    """Arma el diccionario de configuracion listo para `app.config.update()`.

    Asume que la validacion ya paso: llamar siempre despues de `validar_o_terminar()`.
    """
    valores: dict[str, object] = {nombre: _leer(nombre) for nombre in VARIABLES_OBLIGATORIAS}

    for nombre, defecto in VARIABLES_OPCIONALES.items():
        valores[nombre] = _leer(nombre) or defecto

    no_enteras = []
    for nombre in VARIABLES_ENTERAS:
        try:
            valores[nombre] = int(str(valores[nombre]))
        except ValueError:
            no_enteras.append(MENSAJE_NO_ENTERA.format(nombre=nombre))
    if no_enteras:
        _terminar(no_enteras)

    # Claves que Flask y Flask-SQLAlchemy leen con nombre propio.
    valores["SQLALCHEMY_DATABASE_URI"] = valores["DATABASE_URL"]
    valores["SQLALCHEMY_ENGINE_OPTIONS"] = {
        # En desarrollo el contenedor db se reinicia seguido y deja conexiones muertas en el pool.
        "pool_pre_ping": True,
    }
    valores["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    return valores


def validar_o_terminar() -> None:
    """Aplica la politica de fail-fast de la seccion 2 del contrato de configuracion.

    Se invoca una unica vez durante la construccion de la aplicacion (app factory), antes de
    registrar los modulos de dominio, de modo que el proceso muera sin llegar a levantar el
    servidor HTTP si la configuracion esta incompleta.
    """
    faltantes = obtener_faltantes()
    if not faltantes:
        return
    _terminar([MENSAJE_FALTANTE.format(nombre=nombre) for nombre in faltantes])
