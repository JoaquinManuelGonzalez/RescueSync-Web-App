"""Envelope unico de error y manejadores globales.

Implementa docs/contratos/errores.md. Todo error de la aplicacion, sin excepcion, sale con la
estructura `{"error": {codigo, mensaje, detalle, timestamp, id_correlacion}}`.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from app.core.logging import id_correlacion_actual, marca_de_tiempo, registrar_evento

# Seccion 2 del contrato: correspondencia entre codigo HTTP y codigo interno.
CODIGOS_POR_ESTADO: dict[int, str] = {
    400: "SOLICITUD_INVALIDA",
    401: "NO_AUTENTICADO",
    403: "PERMISO_DENEGADO",
    404: "RECURSO_NO_ENCONTRADO",
    409: "CONFLICTO_DE_ESTADO",
    422: "REGLA_DE_NEGOCIO_INCUMPLIDA",
    500: "ERROR_INTERNO",
    502: "RESPUESTA_EXTERNA_INVALIDA",
    503: "SERVICIO_EXTERNO_NO_DISPONIBLE",
    504: "TIEMPO_DE_ESPERA_AGOTADO",
}

# Mensajes por defecto, pensados para mostrarse al usuario final: en espanol y sin detalle tecnico.
MENSAJES_POR_CODIGO: dict[str, str] = {
    "SOLICITUD_INVALIDA": "El formulario tiene campos invalidos o incompletos.",
    "NO_AUTENTICADO": "Necesitas iniciar sesion para realizar esta accion.",
    "PERMISO_DENEGADO": "Tu rol no tiene permiso para realizar esta accion.",
    "RECURSO_NO_ENCONTRADO": "No encontramos lo que estabas buscando.",
    "CONFLICTO_DE_ESTADO": "La operacion no se puede realizar en el estado actual.",
    "REGLA_DE_NEGOCIO_INCUMPLIDA": "La operacion no cumple una regla de negocio.",
    "SISTEMA_EXTERNO_RECHAZO": "El sistema externo rechazo la operacion.",
    "ERROR_INTERNO": "Ocurrio un error inesperado. Volve a intentarlo en unos minutos.",
    "RESPUESTA_EXTERNA_INVALIDA": "El sistema externo respondio algo que no pudimos interpretar.",
    "SERVICIO_EXTERNO_NO_DISPONIBLE": (
        "El sistema externo no responde en este momento. Reintenta en unos minutos."
    ),
    "TIEMPO_DE_ESPERA_AGOTADO": "La operacion tardo demasiado. Reintenta en unos minutos.",
}


class ErrorDeAplicacion(Exception):
    """Error de negocio o transversal que se devuelve con el envelope del contrato.

    Los modulos de dominio la subclasifican fijando `codigo` y `estado_http`, por ejemplo:

        class OfertaFueraDeVentana(ErrorDeAplicacion):
            codigo = "OFERTA_FUERA_DE_VENTANA"
            estado_http = 422
    """

    codigo: str = "ERROR_INTERNO"
    estado_http: int = 500

    def __init__(
        self,
        mensaje: str | None = None,
        *,
        detalle: Any = None,
        codigo: str | None = None,
        estado_http: int | None = None,
    ) -> None:
        if codigo is not None:
            self.codigo = codigo
        if estado_http is not None:
            self.estado_http = estado_http
        generico = MENSAJES_POR_CODIGO["ERROR_INTERNO"]
        self.mensaje = mensaje or MENSAJES_POR_CODIGO.get(self.codigo, generico)
        self.detalle = detalle
        super().__init__(self.mensaje)


class SolicitudInvalida(ErrorDeAplicacion):
    codigo = "SOLICITUD_INVALIDA"
    estado_http = 400


class NoAutenticado(ErrorDeAplicacion):
    codigo = "NO_AUTENTICADO"
    estado_http = 401


class PermisoDenegado(ErrorDeAplicacion):
    codigo = "PERMISO_DENEGADO"
    estado_http = 403


class RecursoNoEncontrado(ErrorDeAplicacion):
    codigo = "RECURSO_NO_ENCONTRADO"
    estado_http = 404


class ConflictoDeEstado(ErrorDeAplicacion):
    codigo = "CONFLICTO_DE_ESTADO"
    estado_http = 409


class ReglaDeNegocioIncumplida(ErrorDeAplicacion):
    codigo = "REGLA_DE_NEGOCIO_INCUMPLIDA"
    estado_http = 422


class SistemaExternoRechazo(ErrorDeAplicacion):
    """El sistema externo respondio 4xx. No invita a reintentar: es un 422, no un 503."""

    codigo = "SISTEMA_EXTERNO_RECHAZO"
    estado_http = 422


class RespuestaExternaInvalida(ErrorDeAplicacion):
    codigo = "RESPUESTA_EXTERNA_INVALIDA"
    estado_http = 502


class ServicioExternoNoDisponible(ErrorDeAplicacion):
    """Se agotaron los reintentos contra el sistema externo. Invita a reintentar."""

    codigo = "SERVICIO_EXTERNO_NO_DISPONIBLE"
    estado_http = 503


class TiempoDeEsperaAgotado(ErrorDeAplicacion):
    codigo = "TIEMPO_DE_ESPERA_AGOTADO"
    estado_http = 504


def construir_envelope(codigo: str, mensaje: str, detalle: Any = None) -> dict[str, Any]:
    """Arma el cuerpo de error del contrato, con timestamp y correlacion ya resueltos."""
    return {
        "error": {
            "codigo": codigo,
            "mensaje": mensaje,
            "detalle": detalle,
            "timestamp": marca_de_tiempo(),
            "id_correlacion": id_correlacion_actual(),
        }
    }


def registrar_manejadores(app: Flask) -> None:
    """Engancha los manejadores globales para que ninguna excepcion escape del envelope."""

    @app.errorhandler(ErrorDeAplicacion)
    def _error_de_aplicacion(error: ErrorDeAplicacion):
        cuerpo = construir_envelope(error.codigo, error.mensaje, error.detalle)
        return jsonify(cuerpo), error.estado_http

    @app.errorhandler(HTTPException)
    def _error_http(error: HTTPException):
        estado = error.code or 500
        codigo = CODIGOS_POR_ESTADO.get(estado, "ERROR_INTERNO")
        cuerpo = construir_envelope(codigo, MENSAJES_POR_CODIGO.get(codigo, error.name))
        return jsonify(cuerpo), estado

    @app.errorhandler(Exception)
    def _error_no_contemplado(error: Exception):
        # Nivel ERROR segun la seccion 6 del contrato de logging. El detalle tecnico queda en
        # el log, nunca en la respuesta: el usuario solo ve el mensaje generico y el id.
        registrar_evento(
            logging.ERROR,
            "excepcion_no_contemplada",
            type(error).__name__,
            id_correlacion=id_correlacion_actual(),
        )
        app.logger.exception("excepcion_no_contemplada")
        cuerpo = construir_envelope("ERROR_INTERNO", MENSAJES_POR_CODIGO["ERROR_INTERNO"])
        return jsonify(cuerpo), 500
