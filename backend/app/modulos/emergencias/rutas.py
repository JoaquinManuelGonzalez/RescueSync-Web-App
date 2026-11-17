"""Endpoints de gestión de emergencias.

Permite:
- Registrar una emergencia desde el formulario web (municipio afectado).
- Listar emergencias. (municipio y centro coordinador)
- Ver el detalle de una emergencia. (municipio y centro coordinador)
"""

from __future__ import annotations

import uuid
from typing import Any

from flask import Blueprint, flash, jsonify, render_template, request
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import (
    EMERGENCIAS_CREAR,
    EMERGENCIAS_LISTAR,
)
from app.core.errores import ErrorDeAplicacion, RecursoNoEncontrado
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.vistas import pide_json, redirigir
from app.modulos.convocatorias.servicios import cerrar_convocatorias_vencidas
from app.modulos.emergencias import servicios
from app.modulos.emergencias.modelos import Emergencia, NivelGravedad, TipoEmergencia

blueprint_emergencias = Blueprint("emergencias", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="emergencias.listar",
    titulo="Emergencias",
    permiso=EMERGENCIAS_LISTAR,
    descripcion="Registro y seguimiento de emergencias por municipio",
    icono="advertencia",
    orden=20,
)


def _es_operador_municipal() -> bool:
    return current_user.tiene_rol("operador_municipal")


def _contexto_de_formulario() -> dict[str, Any]:
    return {
        "niveles_gravedad": list(NivelGravedad),
        "tipos_emergencia": list(TipoEmergencia),
    }


def _formulario_con_error(error: ErrorDeAplicacion):
    flash(error.mensaje, "error")
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
        errores_por_campo=errores_por_campo,
        valores=request.form,
        **_contexto_de_formulario(),
    )


def _filtrar_emergencia_para_municipio(emergencia: Emergencia) -> None:
    if _es_operador_municipal() and emergencia.municipio_id != current_user.organizacion_id:
        raise RecursoNoEncontrado("No encontramos la emergencia solicitada.")


def _serializar_emergencia(emergencia: Emergencia) -> dict[str, Any]:
    return {
        # TODO agregar bonita_case_id
        "id": emergencia.id,
        "titulo": emergencia.titulo,
        "descripcion": emergencia.descripcion,
        "nivel_gravedad": emergencia.nivel_gravedad.value,
        "tipo_emergencia": emergencia.tipo_emergencia.value,
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
    """
    Pantalla de listado de emergencias.
    No se listan emergencias canceladas o finalizadas.
    """
    if _es_operador_municipal():
        # El listado que ve el Municipio, sólo cuenta con las emergencias propias.
        municipio_id = current_user.organizacion_id
        emergencias = servicios.listar_emergencias(municipio_id=municipio_id)
    else:
        emergencias = servicios.listar_emergencias()

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
        emergencia = servicios.crear_emergencia(
            titulo=request.form.get("titulo", ""),
            descripcion=request.form.get("descripcion", ""),
            nivel_gravedad=request.form.get("nivel_gravedad", ""),
            zona_afectada=request.form.get("zona_afectada", ""),
            municipio_id=current_user.organizacion_id,
            usuario_id=current_user.id,
            tipo_emergencia=request.form.get("tipo_emergencia", ""),
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


@blueprint_emergencias.get("/<uuid:emergencia_id>")
@requiere_permiso(EMERGENCIAS_LISTAR)
def obtener(emergencia_id: uuid.UUID):
    """Detalle de una emergencia."""
    cerrar_convocatorias_vencidas(emergencia_id=emergencia_id)
    emergencia = servicios.obtener_emergencia_por_id(emergencia_id)
    _filtrar_emergencia_para_municipio(emergencia)

    if not pide_json():
        return render_template("emergencias/detalle.html", emergencia=emergencia)

    return jsonify(_serializar_emergencia(emergencia))
