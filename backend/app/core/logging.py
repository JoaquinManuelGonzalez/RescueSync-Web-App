"""Logging estructurado de RescueSync.

Implementa docs/contratos/logging.md: una linea JSON por evento hacia stdout, sin archivos de
log dentro del contenedor. Los nombres de campo y de evento de este modulo son el contrato:
no se renombran sin actualizar primero ese documento.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from flask import Flask, Response, g, has_request_context, request

NOMBRE_LOGGER = "rescuesync"

# El contrato (seccion 6) nombra el nivel "WARN"; Python lo llama "WARNING".
NIVELES_CONTRATO: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "ERROR",
}
NIVELES_ACEPTADOS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

VALOR_REDACTADO = "***"

# Seccion 3 del contrato: que nunca se registra.
CABECERAS_SENSIBLES = frozenset({"authorization", "cookie", "set-cookie"})
CAMPOS_SENSIBLES = frozenset(
    {
        "password",
        "contrasena",
        "clave",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "dni",
        "cuit",
        "nombre",
        "apellido",
        "email",
        "correo",
        "telefono",
        "direccion",
    }
)

# El healthcheck del contenedor golpea /health cada pocos segundos; loguearlo ahogaria la salida.
RUTAS_SIN_LOG = frozenset({"/health"})


def marca_de_tiempo() -> str:
    """Devuelve el instante actual en ISO-8601 UTC con milisegundos, como pide el contrato."""
    ahora = datetime.now(UTC)
    return f"{ahora:%Y-%m-%dT%H:%M:%S}.{ahora.microsecond // 1000:03d}Z"


class FormateadorJsonLines(logging.Formatter):
    """Serializa cada registro como un unico objeto JSON en una sola linea."""

    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, Any] = {
            "timestamp": marca_de_tiempo(),
            "nivel": NIVELES_CONTRATO.get(record.levelno, record.levelname),
            "evento": getattr(record, "evento", "mensaje"),
        }

        mensaje = record.getMessage()
        if mensaje:
            evento["mensaje"] = mensaje

        campos = getattr(record, "campos", None)
        if campos:
            evento.update(campos)

        if record.exc_info:
            # El texto de la excepcion trae saltos de linea y romperia el formato JSON Lines.
            evento["excepcion"] = self.formatException(record.exc_info).replace("\n", " | ")

        return json.dumps(evento, ensure_ascii=False, default=str)


def redactar(valor: Any) -> Any:
    """Reemplaza por "***" todo campo sensible, incluso anidado dentro de listas o diccionarios."""
    if isinstance(valor, Mapping):
        return {
            clave: (
                VALOR_REDACTADO if str(clave).lower() in CAMPOS_SENSIBLES else redactar(contenido)
            )
            for clave, contenido in valor.items()
        }
    if isinstance(valor, list | tuple):
        return [redactar(elemento) for elemento in valor]
    return valor


def redactar_cabeceras(cabeceras: Mapping[str, str]) -> dict[str, str]:
    """Reemplaza enteras las cabeceras sensibles, sin dejar ni un prefijo del valor."""
    return {
        nombre: (VALOR_REDACTADO if nombre.lower() in CABECERAS_SENSIBLES else valor)
        for nombre, valor in cabeceras.items()
    }


def obtener_logger() -> logging.Logger:
    return logging.getLogger(NOMBRE_LOGGER)


def configurar_logging(nivel: str = "INFO") -> logging.Logger:
    """Deja stdout como unico destino, con el formateador JSON Lines.

    Se puede llamar antes de que exista la aplicacion: la validacion fail-fast de la
    configuracion necesita loguear aunque la app todavia no se haya construido.
    """
    numero = NIVELES_ACEPTADOS.get(str(nivel).upper(), logging.INFO)

    manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(FormateadorJsonLines())

    raiz = logging.getLogger()
    for existente in list(raiz.handlers):
        raiz.removeHandler(existente)
    raiz.addHandler(manejador)
    raiz.setLevel(numero)

    # El log de acceso de Werkzeug duplicaria "solicitud_completada" en texto plano.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    return obtener_logger()


def id_correlacion_actual() -> str:
    """UUID de la solicitud en curso. Fuera de una solicitud, genera uno nuevo."""
    if has_request_context():
        existente = g.get("id_correlacion")
        if existente:
            return str(existente)
    return str(uuid.uuid4())


def id_usuario_actual() -> str | None:
    """Identificador interno del usuario autenticado, o None si no hay sesion.

    Esta funcion solo enriquece un log: no puede hacer fallar una solicitud bajo ninguna
    circunstancia. Por eso atrapa cualquier excepcion al resolver `current_user`, que es un
    proxy perezoso capaz de explotar por motivos ajenos a quien esta logueando (por ejemplo,
    si todavia no hay un `user_loader` registrado).
    """
    if not has_request_context():
        return None
    try:
        from flask_login import current_user

        if not getattr(current_user, "is_authenticated", False):
            return None
        identificador = getattr(current_user, "id", None)
    except Exception:
        return None
    return None if identificador is None else str(identificador)


def registrar_evento(nivel: int, evento: str, mensaje: str = "", **campos: Any) -> None:
    """Emite un evento del contrato. Los campos van tal cual al objeto JSON."""
    obtener_logger().log(nivel, mensaje, extra={"evento": evento, "campos": campos})


def registrar_llamada_saliente(
    *,
    componente_destino: str,
    metodo: str,
    endpoint: str,
    codigo_estado: int | None,
    duracion_ms: int,
    intento: int,
    resultado: str,
    id_correlacion: str | None = None,
    id_usuario: str | None = None,
) -> None:
    """Emite el evento `llamada_saliente` de la seccion 2 del contrato.

    Lo usan los clientes HTTP de `core/integraciones/`. `endpoint` se pasa ya normalizado
    (por ejemplo `/emergencias/{id}/ofertas`), nunca con valores del dominio sustituidos.
    """
    # Seccion 6: un intento fallido que todavia tiene reintentos disponibles es WARN, no ERROR.
    # Quien agote los reintentos emite el ERROR por su cuenta, junto con el 503 al usuario.
    nivel = logging.INFO if resultado == "exito" else logging.WARNING

    registrar_evento(
        nivel,
        "llamada_saliente",
        componente_destino=componente_destino,
        metodo=metodo,
        endpoint=endpoint,
        codigo_estado=codigo_estado,
        duracion_ms=duracion_ms,
        intento=intento,
        resultado=resultado,
        id_correlacion=id_correlacion or id_correlacion_actual(),
        id_usuario=id_usuario if id_usuario is not None else id_usuario_actual(),
    )


def _nivel_por_estado(codigo_estado: int) -> int:
    if codigo_estado >= 500:
        return logging.ERROR
    if codigo_estado >= 400:
        return logging.WARNING
    return logging.INFO


def registrar_middleware(app: Flask) -> None:
    """Engancha la correlacion y los eventos de ciclo de vida de cada solicitud."""

    @app.before_request
    def _abrir_solicitud() -> None:
        g.id_correlacion = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        g.inicio_monotonico = time.perf_counter()

        if request.path in RUTAS_SIN_LOG:
            return

        registrar_evento(
            logging.INFO,
            "solicitud_entrante",
            metodo=request.method,
            endpoint=request.path,
            id_correlacion=g.id_correlacion,
            id_usuario=id_usuario_actual(),
        )

    @app.after_request
    def _cerrar_solicitud(respuesta: Response) -> Response:
        respuesta.headers["X-Correlation-Id"] = id_correlacion_actual()

        if request.path in RUTAS_SIN_LOG:
            return respuesta

        inicio = g.get("inicio_monotonico")
        duracion_ms = int((time.perf_counter() - inicio) * 1000) if inicio else 0

        registrar_evento(
            _nivel_por_estado(respuesta.status_code),
            "solicitud_completada",
            metodo=request.method,
            endpoint=request.path,
            codigo_estado=respuesta.status_code,
            duracion_ms=duracion_ms,
            id_correlacion=id_correlacion_actual(),
            id_usuario=id_usuario_actual(),
        )
        return respuesta
