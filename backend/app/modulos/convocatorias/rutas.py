"""Endpoints de gestión de convocatorias."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import CONVOCATORIAS_CERRAR, CONVOCATORIAS_CREAR, CONVOCATORIAS_LISTAR
from app.core.errores import ErrorDeAplicacion, RecursoNoEncontrado, SolicitudInvalida
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.plantillas import ZONA_HORARIA_DE_LA_INTERFAZ
from app.core.interfaz.vistas import pide_json, redirigir
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.convocatorias.servicios import (
    cerrar_convocatoria,
    cerrar_convocatorias_vencidas,
    crear_convocatoria,
)
from app.modulos.emergencias import servicios as servicios_emergencias
from app.modulos.emergencias.modelos import EstadoEmergencia

blueprint_convocatorias = Blueprint("convocatorias", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="convocatorias.listar",
    titulo="Convocatorias",
    permiso=CONVOCATORIAS_LISTAR,
    descripcion="Publicación de convocatorias por emergencia",
    icono="lista",
    orden=40,
)


def _contexto_de_formulario(emergencia) -> dict:
    lotes = list(emergencia.lotes or [])
    hay_convocatoria_abierta = any(
        convocatoria.estado == EstadoConvocatoria.abierta
        for convocatoria in (emergencia.convocatorias or [])
    )
    return {
        "emergencia": emergencia,
        "lotes": lotes,
        "hay_lotes": bool(lotes),
        "hay_convocatoria_abierta": hay_convocatoria_abierta,
        "emergencia_en_evaluacion": emergencia.estado == EstadoEmergencia.en_evaluacion,
    }


def _formulario_con_error(emergencia, error: ErrorDeAplicacion):
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
        "convocatorias/formulario.html",
        error_mensaje=error.mensaje,
        errores_por_campo=errores_por_campo,
        valores=request.form,
        **_contexto_de_formulario(emergencia),
    )


def _parsear_fecha_cierre(fecha_valor: str | None, hora_valor: str | None) -> datetime:
    if not fecha_valor or not fecha_valor.strip():
        raise SolicitudInvalida(
            "La fecha límite es obligatoria y debe ingresarse como día/mes/año.",
            detalle={"campo": "fecha_cierre"},
        )
    if not hora_valor or not hora_valor.strip():
        raise SolicitudInvalida(
            "La hora límite para presentar ofertas es obligatoria.",
            detalle={"campo": "hora_cierre"},
        )
    try:
        fecha = datetime.strptime(
            f"{fecha_valor.strip()} {hora_valor.strip()}", "%Y-%m-%d %H:%M"
        )
    except ValueError as error:
        raise SolicitudInvalida(
            "Ingresá una fecha y una hora válidas.",
            detalle={"campo": "fecha_cierre"},
        ) from error
    return fecha.replace(tzinfo=ZONA_HORARIA_DE_LA_INTERFAZ).astimezone(UTC)


@blueprint_convocatorias.get("")
@requiere_permiso(CONVOCATORIAS_LISTAR)
def listar():
    """Listado de convocatorias publicadas."""
    cerrar_convocatorias_vencidas()
    convocatorias = db.session.execute(
        db.select(Convocatoria).order_by(Convocatoria.fecha_cierre.desc(), Convocatoria.id.desc())
    ).scalars().all()
    es_representante_ong = current_user.tiene_rol("representante_ong")
    if es_representante_ong:
        convocatorias = [
            convocatoria for convocatoria in convocatorias if convocatoria.esta_vigente()
        ]
    if pide_json():
        return jsonify({
            "convocatorias": [
                {
                    "id": convocatoria.id,
                    "emergencia_id": convocatoria.emergencia_id,
                    "fecha_inicio": convocatoria.fecha_inicio.isoformat(),
                    "fecha_cierre": convocatoria.fecha_cierre.isoformat(),
                    "estado": convocatoria.estado.value,
                    "resumen_situacion": convocatoria.resumen_situacion,
                }
                for convocatoria in convocatorias
            ]
        })
    return render_template(
        "convocatorias/listado.html",
        convocatorias=convocatorias,
        es_representante_ong=es_representante_ong,
    )


@blueprint_convocatorias.get("/emergencias/<int:emergencia_id>/nueva")
@requiere_permiso(CONVOCATORIAS_CREAR)
def formulario_de_alta(emergencia_id: int):
    """Pantalla para abrir una convocatoria sobre una emergencia."""
    cerrar_convocatorias_vencidas(emergencia_id=emergencia_id)
    emergencia = servicios_emergencias.obtener_emergencia_por_id(emergencia_id)
    return render_template(
        "convocatorias/formulario.html",
        **_contexto_de_formulario(emergencia),
        errores_por_campo={},
        valores={},
    )


@blueprint_convocatorias.post("/emergencias/<int:emergencia_id>/nueva")
@requiere_permiso(CONVOCATORIAS_CREAR)
def crear_desde_formulario(emergencia_id: int):
    """Persiste una convocatoria vinculada a la emergencia seleccionada."""
    emergencia = servicios_emergencias.obtener_emergencia_por_id(emergencia_id)
    try:
        convocatoria = crear_convocatoria(
            emergencia_id=emergencia.id,
            coordinador_id=current_user.id,
            resumen_situacion=request.form.get("resumen_situacion", ""),
            fecha_cierre=_parsear_fecha_cierre(
                request.form.get("fecha_cierre"), request.form.get("hora_cierre")
            ),
            observaciones=request.form.get("observaciones") or None,
        )
    except ErrorDeAplicacion as error:
        if pide_json():
            raise
        return _formulario_con_error(emergencia, error)

    return redirigir(
        "convocatorias.obtener",
        "Convocatoria publicada correctamente.",
        convocatoria_id=convocatoria.id,
    )


@blueprint_convocatorias.get("/<int:convocatoria_id>")
@requiere_permiso(CONVOCATORIAS_LISTAR)
def obtener(convocatoria_id: int):
    """Detalle de una convocatoria."""
    cerrar_convocatorias_vencidas()
    convocatoria = db.session.get(Convocatoria, convocatoria_id)
    if not convocatoria:
        raise RecursoNoEncontrado(f"Convocatoria con id {convocatoria_id} no encontrada.")
    if pide_json():
        return jsonify(
            {
                "id": convocatoria.id,
                "emergencia_id": convocatoria.emergencia_id,
                "coordinador_id": convocatoria.coordinador_id,
                "fecha_inicio": convocatoria.fecha_inicio.isoformat(),
                "fecha_cierre": convocatoria.fecha_cierre.isoformat(),
                "resumen_situacion": convocatoria.resumen_situacion,
                "estado": convocatoria.estado.value,
                "observaciones": convocatoria.observaciones,
            }
        )
    return render_template("convocatorias/detalle.html", convocatoria=convocatoria)


@blueprint_convocatorias.post("/<int:convocatoria_id>/cerrar")
@requiere_permiso(CONVOCATORIAS_CERRAR)
def cerrar(convocatoria_id: int):
    """Cierra la ventana de ofertas para habilitar una revisión de necesidades."""
    convocatoria = cerrar_convocatoria(convocatoria_id)
    if pide_json():
        return jsonify(
            {
                "id": convocatoria.id,
                "estado": convocatoria.estado.value,
                "emergencia_id": convocatoria.emergencia_id,
            }
        )
    return redirigir(
        "convocatorias.obtener",
        "Convocatoria cerrada. Podés revisar las necesidades y preparar otra ronda.",
        convocatoria_id=convocatoria.id,
    )
