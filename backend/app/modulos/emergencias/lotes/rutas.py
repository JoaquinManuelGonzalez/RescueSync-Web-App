"""Endpoints de gestión de lotes de necesidad.

Permite al Centro Coordinador Regional:
- Ver el formulario de alta de lotes para una emergencia.
- Persistir los lotes enviados desde el formulario.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import LOTES_CREAR, LOTES_LISTAR
from app.core.errores import ErrorDeAplicacion
from app.core.interfaz.vistas import pide_json, redirigir
from app.modulos.emergencias.modelos import EstadoLote
from app.modulos.emergencias.lotes import servicios
from app.core.acceso.permisos import LOTES_CREAR, LOTES_LISTAR


blueprint_lotes = Blueprint("lotes", __name__)


def _contexto_de_formulario(emergencia) -> dict[str, Any]:
    return {
        "emergencia": emergencia,
        "items_catalogo": servicios.listar_items(),
        "estados_lote": list(EstadoLote),
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
        "lotes/formulario.html",
        error_mensaje=error.mensaje,
        errores_por_campo=errores_por_campo,
        valores=request.form,
        **_contexto_de_formulario(emergencia),
    )


def _extraer_items_del_formulario() -> list[dict]:
    """Extrae las filas de ítems desde el form.

    El template envía arrays con nombres:
        items[0][item_id], items[0][cantidad_solicitada], items[0][observaciones]
        items[1][item_id], ...
    """
    items: list[dict] = []
    indice = 0
    while True:
        prefijo = f"items[{indice}]"
        item_id = request.form.get(f"{prefijo}[item_id]")
        if item_id is None:
            break
        items.append(
            {
                "item_id": item_id,
                "cantidad_solicitada": request.form.get(f"{prefijo}[cantidad_solicitada]"),
                "observaciones": request.form.get(f"{prefijo}[observaciones]"),
            }
        )
        indice += 1
    return items


@blueprint_lotes.get("/emergencias/<int:emergencia_id>/lotes/nuevo")
@requiere_permiso(LOTES_CREAR)
def formulario_de_alta(emergencia_id: int):
    """Pantalla para cargar los ítems del nuevo lote."""
    emergencia = servicios.obtener_emergencia(emergencia_id)
    return render_template(
        "lotes/formulario.html",
        valores={},
        errores_por_campo={},
        **_contexto_de_formulario(emergencia),
    )


@blueprint_lotes.post("/emergencias/<int:emergencia_id>/lotes/nuevo")
@requiere_permiso(LOTES_CREAR)
def crear_desde_formulario(emergencia_id: int):
    """Persiste los lotes enviados desde el formulario."""
    emergencia = servicios.obtener_emergencia(emergencia_id)
    try:
        lotes = servicios.crear_lotes(
            emergencia_id=emergencia_id,
            descripcion=request.form.get("descripcion", ""),
            items=_extraer_items_del_formulario(),
        )
    except ErrorDeAplicacion as error:
        if pide_json():
            raise
        return _formulario_con_error(emergencia, error)

    if pide_json():
        return jsonify(
            {
                "lotes": [
                    {"id": lote.id, "descripcion": lote.descripcion, "estado": lote.estado.value}
                    for lote in lotes
                ]
            }
        ), 201

    return redirigir(
        "emergencias.obtener",
        "Lote(s) de necesidades generado(s).",
        emergencia_id=emergencia_id,
    )


@blueprint_lotes.get("/emergencias/<int:emergencia_id>/lotes")
@requiere_permiso(LOTES_LISTAR)
def listar_por_emergencia(emergencia_id: int):
    """Listado de lotes de una emergencia (JSON o vista)."""
    emergencia = servicios.obtener_emergencia(emergencia_id)
    lotes = servicios.listar_lotes_por_emergencia(emergencia_id)
    if pide_json():
        return jsonify(
            {
                "lotes": [
                    {
                        "id": lote.id,
                        "descripcion": lote.descripcion,
                        "estado": lote.estado.value,
                        "items": [
                            {
                                "item_id": li.item_id,
                                "nombre": li.item.nombre,
                                "cantidad_solicitada": float(li.cantidad_solicitada),
                                "unidad_medida": li.item.unidad_medida,
                                "observaciones": li.observaciones,
                            }
                            for li in lote.lote_items
                        ],
                    }
                    for lote in lotes
                ]
            }
        )
    return render_template("lotes/listado.html", emergencia=emergencia, lotes=lotes)