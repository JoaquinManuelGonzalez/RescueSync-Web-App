"""Envelope unico de error y manejadores globales.

Implementa docs/contratos/errores.md. Todo error de la aplicacion, sin excepcion, sale con la
estructura `{"error": {codigo, mensaje, detalle, timestamp, id_correlacion}}` para los clientes
JSON.

Al navegador el envelope no le sirve: una persona no puede leer JSON crudo. Cuando la solicitud
viene de la interfaz (ver `app.core.interfaz.vistas.pide_json`), el mismo error se traduce a algo
navegable, siempre con el mismo codigo HTTP y el mismo mensaje:

1. Si la vista declaro `@plantilla_ante_error`, se vuelve a mostrar su formulario con los
   mensajes al lado de cada campo.
2. Si el error tiene `redirigir_a` (sin sesion, contrasena pendiente de cambio), se redirige a
   esa pantalla con el mensaje como aviso.
3. Si no, se muestra la pagina de error con el mensaje y el id de correlacion.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from app.core.interfaz.vistas import (
    ADVERTENCIA,
    origen_propio,
    pide_json,
    respuesta_de_formulario_con_errores,
)
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
    "SOLICITUD_INVALIDA": "El formulario tiene campos inválidos o incompletos.",
    "NO_AUTENTICADO": "Necesitás iniciar sesión para realizar esta acción.",
    "PERMISO_DENEGADO": "Tu rol no tiene permiso para realizar esta acción.",
    "RECURSO_NO_ENCONTRADO": "No encontramos lo que estabas buscando.",
    "CONFLICTO_DE_ESTADO": "La operación no se puede realizar en el estado actual.",
    "REGLA_DE_NEGOCIO_INCUMPLIDA": "La operación no cumple una regla de negocio.",
    "SISTEMA_EXTERNO_RECHAZO": "El sistema externo rechazó la operación.",
    "ERROR_INTERNO": "Ocurrió un error inesperado. Volvé a intentarlo en unos minutos.",
    "RESPUESTA_EXTERNA_INVALIDA": "El sistema externo respondió algo que no pudimos interpretar.",
    "SERVICIO_EXTERNO_NO_DISPONIBLE": (
        "El sistema externo no responde en este momento. Reintentá en unos minutos."
    ),
    "TIEMPO_DE_ESPERA_AGOTADO": "La operación tardó demasiado. Reintentá en unos minutos.",
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
    # Endpoint al que se manda al navegador ante este error, en vez de mostrarle la pagina de
    # error. Solo lo usan los errores que tienen una pantalla que los resuelve.
    redirigir_a: str | None = None

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
    redirigir_a = "sesion.formulario_de_ingreso"


class PermisoDenegado(ErrorDeAplicacion):
    codigo = "PERMISO_DENEGADO"
    estado_http = 403


class SeccionAjenaAlRol(PermisoDenegado):
    """La seccion entera pertenece a otro perfil, como el panel de auditoria.

    Para un cliente JSON es un 403 PERMISO_DENEGADO como cualquier otro; al navegador se lo
    devuelve a su portal con un aviso, en vez de dejarlo frente a la pagina de error de una
    pantalla que nunca va a poder usar.
    """

    redirigir_a = "inicio.panel"


class RecursoNoEncontrado(ErrorDeAplicacion):
    codigo = "RECURSO_NO_ENCONTRADO"
    estado_http = 404


class ConflictoDeEstado(ErrorDeAplicacion):
    codigo = "CONFLICTO_DE_ESTADO"
    estado_http = 409


class ContrasenaPendienteDeCambio(ConflictoDeEstado):
    """La cuenta tiene que cambiar su contrasena antes de operar.

    Para un cliente JSON es un 409 CONFLICTO_DE_ESTADO como cualquier otro; al navegador se lo
    lleva a la pantalla de cambio de contrasena.
    """

    redirigir_a = "sesion.formulario_de_contrasena"


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


# --- Respuesta en el navegador ------------------------------------------------

MENSAJE_FORMULARIO_VENCIDO = "El formulario venció o no es válido. Volvé a completarlo y enviarlo."

TITULOS_POR_ESTADO: dict[int, str] = {
    400: "No pudimos procesar la solicitud",
    401: "Necesitás iniciar sesión",
    403: "No tenés acceso a esta sección",
    404: "No encontramos esta página",
    405: "Operación no permitida",
    409: "No se puede realizar la operación",
    422: "No se puede realizar la operación",
    500: "Algo salió mal",
    502: "El sistema externo respondió con un error",
    503: "Un sistema externo no responde",
    504: "Un sistema externo no responde",
}

ICONOS_POR_ESTADO: dict[int, str] = {403: "candado", 404: "buscar", 401: "candado"}


def _pagina_de_error(codigo: str, mensaje: str, estado: int, detalle: Any = None):
    """La pagina de error del navegador, con los mismos datos que llevaria el envelope.

    Si la propia pagina falla al renderizarse (por ejemplo, porque el error de fondo es la base
    de datos y el navbar la consulta), se cae al envelope JSON: una respuesta fea es mejor que
    un error dentro del manejador de errores.
    """
    try:
        html = render_template(
            "errores/error.html",
            estado=estado,
            codigo=codigo,
            titulo=TITULOS_POR_ESTADO.get(estado, TITULOS_POR_ESTADO[500]),
            icono_nombre=ICONOS_POR_ESTADO.get(estado, "advertencia"),
            mensaje=mensaje,
            id_correlacion=id_correlacion_actual(),
        )
    except Exception:
        return jsonify(construir_envelope(codigo, mensaje, detalle)), estado
    return html, estado


def _redirigir_por_error(error: ErrorDeAplicacion):
    """Lleva al navegador a la pantalla que resuelve el error, con el mensaje como aviso.

    Ante la falta de sesion se conserva a donde iba la persona (`?next=`), para devolverla ahi
    despues de ingresar. Solo en un GET: repetir un POST despues del ingreso no tiene sentido.
    """
    flash(error.mensaje, ADVERTENCIA)
    valores: dict[str, str] = {}
    if isinstance(error, NoAutenticado) and request.method == "GET":
        valores["next"] = request.full_path.rstrip("?")
    return redirect(url_for(str(error.redirigir_a), **valores))


def _responder_en_navegador(error: ErrorDeAplicacion):
    formulario = respuesta_de_formulario_con_errores(
        error.mensaje, error.detalle, error.estado_http
    )
    if formulario is not None:
        return formulario
    if error.redirigir_a:
        return _redirigir_por_error(error)
    return _pagina_de_error(error.codigo, error.mensaje, error.estado_http, error.detalle)


def registrar_manejadores(app: Flask) -> None:
    """Engancha los manejadores globales para que ninguna excepcion escape del envelope."""

    @app.errorhandler(ErrorDeAplicacion)
    def _error_de_aplicacion(error: ErrorDeAplicacion):
        if not pide_json():
            return _responder_en_navegador(error)
        cuerpo = construir_envelope(error.codigo, error.mensaje, error.detalle)
        return jsonify(cuerpo), error.estado_http

    @app.errorhandler(HTTPException)
    def _error_http(error: HTTPException):
        estado = error.code or 500
        codigo = CODIGOS_POR_ESTADO.get(estado, "ERROR_INTERNO")
        mensaje = MENSAJES_POR_CODIGO.get(codigo, error.name)
        if not pide_json():
            return _pagina_de_error(codigo, mensaje, estado)
        return jsonify(construir_envelope(codigo, mensaje)), estado

    @app.errorhandler(CSRFError)
    def _error_csrf(error: CSRFError):
        """Token CSRF faltante o vencido.

        En el navegador casi siempre es un formulario que quedo abierto mas que la sesion: se
        vuelve a la pantalla de origen para que lo envie de nuevo, en vez de mostrar un error.
        """
        if pide_json():
            return _error_http(error)
        flash(MENSAJE_FORMULARIO_VENCIDO, ADVERTENCIA)
        return redirect(origen_propio() or url_for("inicio.raiz"))

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
        mensaje = MENSAJES_POR_CODIGO["ERROR_INTERNO"]
        if not pide_json():
            return _pagina_de_error("ERROR_INTERNO", mensaje, 500)
        return jsonify(construir_envelope("ERROR_INTERNO", mensaje)), 500
