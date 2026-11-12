"""Pantallas municipales de selección de ofertas."""

from __future__ import annotations

from flask import Blueprint, flash, render_template, request
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import ADJUDICACIONES_SELECCIONAR
from app.core.errores import ErrorDeAplicacion
from app.core.integraciones.bonita.proceso import confirmar_seleccion_ofertas
from app.core.integraciones.bonita.sesion import BONITA_USER
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.vistas import ERROR, redirigir
from app.modulos.adjudicaciones import servicios

blueprint_adjudicaciones = Blueprint("adjudicaciones", __name__)
ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="adjudicaciones.listar",
    titulo="Selección de ofertas",
    permiso=ADJUDICACIONES_SELECCIONAR,
    descripcion="Elegí ofertas evaluadas para atender emergencias cubiertas",
    icono="activar",
    orden=35,
)


@blueprint_adjudicaciones.get("")
@requiere_permiso(ADJUDICACIONES_SELECCIONAR)
def listar():
    convocatorias = servicios.listar_convocatorias_pendientes(current_user.organizacion_id)
    return render_template("adjudicaciones/listado.html", convocatorias=convocatorias)


@blueprint_adjudicaciones.get("/convocatoria/<int:convocatoria_id>")
@requiere_permiso(ADJUDICACIONES_SELECCIONAR)
def seleccionar(convocatoria_id: int):
    convocatoria = servicios.obtener_convocatoria(convocatoria_id, current_user.organizacion_id)
    ofertas = [
        oferta
        for oferta in convocatoria.ofertas
        if any(linea.tipo_asignacion.value in ("principal", "apoyo") for linea in oferta.items)
    ]
    return render_template(
        "adjudicaciones/seleccion.html",
        convocatoria=convocatoria,
        ofertas=ofertas,
        solo_lectura=convocatoria.estado.value == "adjudicada",
    )


@blueprint_adjudicaciones.post("/convocatoria/<int:convocatoria_id>")
@requiere_permiso(ADJUDICACIONES_SELECCIONAR)
def confirmar(convocatoria_id: int):
    convocatoria = servicios.obtener_convocatoria(convocatoria_id, current_user.organizacion_id)
    try:
        linea_ids = [int(valor) for valor in request.form.getlist("linea_id")]
        servicios.seleccionar_lineas(convocatoria, linea_ids)

        case_id, compromisos_json = servicios.obtener_datos_integracion_bonita(convocatoria)

        confirmar_seleccion_ofertas(
            username=BONITA_USER,
            case_id=case_id,
            adjudicacion_id=convocatoria.id,
            compromisos_json=compromisos_json,
        )
    except (ValueError, ErrorDeAplicacion) as error:
        flash(
            error.mensaje
            if isinstance(error, ErrorDeAplicacion)
            else "La selección contiene ofertas inválidas.",
            ERROR,
        )
        return redirigir("adjudicaciones.seleccionar", convocatoria_id=convocatoria_id)
    return redirigir("adjudicaciones.listar", "Ofertas seleccionadas correctamente.")
