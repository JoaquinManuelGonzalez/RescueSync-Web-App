"""Endpoints de gestión de emergencias.

Permite:
- Registrar una emergencia desde el formulario web (municipio afectado).
- Listar emergencias. (municipio y centro coordinador)
- Ver el detalle de una emergencia. (municipio y centro coordinador)
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import (
    EMERGENCIAS_CREAR,
    EMERGENCIAS_LISTAR,
)
from app.core.errores import ErrorDeAplicacion, RecursoNoEncontrado, SolicitudInvalida
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.vistas import pide_json, redirigir
from app.modulos.emergencias import servicios
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia, NivelGravedad

blueprint_emergencias = Blueprint("emergencias", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="emergencias.listar",
    titulo="Emergencias",
    permiso=EMERGENCIAS_LISTAR,
    descripcion="Registro y seguimiento de emergencias por municipio",
    icono="alerta",
    orden=20,
)


def _es_operador_municipal() -> bool:
    return current_user.tiene_rol("operador_municipal")


def _contexto_de_formulario() -> dict[str, Any]:
    return {"niveles_gravedad": list(NivelGravedad)}


def _formulario_con_error(error: ErrorDeAplicacion):
    if isinstance(error.detalle, dict):
        errores_por_campo = error.detalle
    elif isinstance(error.detalle, list):
        errores_por_campo = {
            d["campo"]: d.get("motivo", "Valor inválido")
            for d in error.detalle
            if isinstance(d, dict) and "campo" in d
        }
    else:
        errores_por_campo = {}

    return render_template(
        "emergencias/formulario.html",
        error_mensaje=error.mensaje,
        errores_por_campo=errores_por_campo,
        valores=request.form,
        **_contexto_de_formulario(),
    )


def _filtrar_emergencia_para_municipio(emergencia: Emergencia) -> None:
    if _es_operador_municipal() and emergencia.municipio_id != current_user.organizacion_id:
        raise RecursoNoEncontrado("No encontramos la emergencia solicitada.")


def _serializar_emergencia(emergencia: Emergencia) -> dict[str, Any]:
    return {
        "id": emergencia.id,
        "titulo": emergencia.titulo,
        "descripcion": emergencia.descripcion,
        "nivel_gravedad": emergencia.nivel_gravedad.value,
        "zona_afectada": emergencia.zona_afectada,
        "estado": emergencia.estado.value,
        "municipio_id": emergencia.municipio_id,
        "usuario_id": emergencia.usuario_id,
        "creado_en": emergencia.creado_en.isoformat() if emergencia.creado_en else None,
        "actualizado_en": (
            emergencia.actualizado_en.isoformat() if emergencia.actualizado_en else None
        ),
    }


@blueprint_emergencias.get("")
@requiere_permiso(EMERGENCIAS_LISTAR)
def listar():
    """Pantalla de emergencias, opcionalmente filtrada por estado."""
    estado_raw = request.args.get("estado")
    estado = None
    if estado_raw:
        try:
            estado = EstadoEmergencia(estado_raw)
        except ValueError as error:
            raise SolicitudInvalida(f"Estado inválido: {estado_raw}.") from error

    if _es_operador_municipal():
        # El listado que ve el Municipio, sólo cuenta con las emergencias propias.
        municipio_id = current_user.organizacion_id
        emergencias = servicios.listar_emergencias(municipio_id=municipio_id, estado=estado)
    else:
        # (Nota para mí, pienso en voz alta)
        # Si en cambio es centro coordinador regional deberia verlas todas
        # El listado que ve el Centro Coordinador Regional incluye a todas las emergencias pendientes.
        # ordenado por gravedad (descendente), y por fecha de alta (descendente).
        # Duda: el estado "registrada" implica que la emergencia está pendiente de revisión
        # Si alguien se la pone a "revisar" se debería poner en modo en_evaluacion
        # Entonces tocar el botón de generar lotes (en ver detalle de emergencia, no en el listado) debería cambiarle el estado
        # Y salir del formulario de alta de lotes sin guardar nada debería volver a dejarla en estado "registrada"
        # Pendiente para el controller de Lotes de Necesidades
        emergencias = servicios.listar_emergencias(estado=EstadoEmergencia.registrada)

    if pide_json():
        return jsonify({"emergencias": [_serializar_emergencia(e) for e in emergencias]})

    return render_template("emergencias/listado.html", emergencias=emergencias)


@blueprint_emergencias.get("/nueva")
@requiere_permiso(EMERGENCIAS_CREAR)
def formulario_de_alta():
    """Pantalla para registrar una emergencia."""
    return render_template(
        "emergencias/formulario.html",
        valores={},
        errores_por_campo={},
        **_contexto_de_formulario(),
    )


@blueprint_emergencias.post("/nueva")
@requiere_permiso(EMERGENCIAS_CREAR)
def crear_desde_formulario():
    """Persiste una emergencia enviada desde la pantalla web."""
    try:
        # CREO QUE FALTA EL CAMPO DE TIPO DE DESASTRE ZASSS
        # QUEDA PENDIENTE HACER UNA MIGRACION ENTONCES ZASSSS
        emergencia = servicios.crear_emergencia(
            titulo=request.form.get("titulo", ""),
            descripcion=request.form.get("descripcion", ""),
            nivel_gravedad=request.form.get("nivel_gravedad", ""),
            zona_afectada=request.form.get("zona_afectada", ""),
            municipio_id=current_user.organizacion_id,
            usuario_id=current_user.id,
        )
    except ErrorDeAplicacion as error:
        if pide_json():
            raise
        return _formulario_con_error(error)

    return redirigir(
        "emergencias.obtener",
        "Emergencia registrada.",
        emergencia_id=emergencia.id,
    )


@blueprint_emergencias.get("/<int:emergencia_id>")
@requiere_permiso(EMERGENCIAS_LISTAR)
def obtener(emergencia_id: int):
    """Detalle de una emergencia."""
    emergencia = servicios.obtener_emergencia_por_id(emergencia_id)
    _filtrar_emergencia_para_municipio(emergencia)

    if not pide_json():
        return render_template("emergencias/detalle.html", emergencia=emergencia)

    return jsonify(_serializar_emergencia(emergencia))

#
#@blueprint_emergencias.post("")
#@requiere_permiso(EMERGENCIAS_CREAR)
#def crear():
#    """Alta vía API JSON."""
#    datos = request.get_json(silent=True)
#    if not isinstance(datos, dict):
#        raise SolicitudInvalida("El cuerpo de la solicitud debe ser un JSON válido.")
#
#    emergencia = servicios.crear_emergencia(
#        titulo=datos.get("titulo", ""),
#        descripcion=datos.get("descripcion", ""),
#        nivel_gravedad=datos.get("nivel_gravedad", ""),
#        zona_afectada=datos.get("zona_afectada", ""),
#        municipio_id=current_user.organizacion_id,
#        usuario_id=current_user.id,
#    )
#    return jsonify(_serializar_emergencia(emergencia)), 201