"""Endpoints de gestión de ofertas simples.

Permite:
- Crear una oferta simple para una convocatoria activa (ONG).
- Obtener el detalle de una oferta.
- Modificar una oferta dentro de la ventana de la convocatoria.
- Retirar una oferta antes del cierre de la convocatoria.
- Listar ofertas de una convocatoria.
- Consolidar ofertas para el motor Bonita (Integración #4).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import (
    OFERTAS_CREAR,
    OFERTAS_EDITAR,
    OFERTAS_LISTAR,
    OFERTAS_RETIRAR,
)
from app.core.errores import NoAutenticado, SolicitudInvalida
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.vistas import pide_json, redirigir
from app.core.logging import registrar_evento
from app.extensiones import csrf, db
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.ofertas import servicios
from app.modulos.ofertas.modelos import Oferta
from app.modulos.ofertas.servicios import _formatear_fecha_iso

blueprint_ofertas = Blueprint("ofertas", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="ofertas.listar",
    titulo="Ofertas de ayuda",
    permiso=OFERTAS_LISTAR,
    descripcion="Propuestas, versiones y trazabilidad de las ONG",
    icono="carpeta",
    orden=30,
)


def _contexto_de_formulario(convocatoria_id: int, oferta: Oferta | None = None) -> dict[str, Any]:
    convocatoria = db.session.get(Convocatoria, convocatoria_id)
    if not convocatoria:
        raise SolicitudInvalida("La convocatoria indicada no existe.")
    lotes = [item for lote in convocatoria.emergencia.lotes for item in lote.lote_items]
    cantidades = {linea.lote_item_id: linea for linea in oferta.items} if oferta else {}
    return {
        "convocatoria": convocatoria,
        "lote_items": lotes,
        "oferta": oferta,
        "cantidades": cantidades,
    }


def _items_desde_formulario(convocatoria: Convocatoria) -> list[dict[str, Any]]:
    items = []
    for lote in convocatoria.emergencia.lotes:
        for lote_item in lote.lote_items:
            valor = request.form.get(f"item_{lote_item.id}", "").strip()
            if not valor:
                continue
            try:
                cantidad = float(valor)
            except ValueError as error:
                raise SolicitudInvalida(
                    "Las cantidades ofrecidas deben ser números válidos.",
                    detalle={f"item_{lote_item.id}": "Ingresá un número válido."},
                ) from error
            if cantidad <= 0:
                continue
            items.append(
                {
                    "lote_item_id": lote_item.id,
                    "cantidad_ofrecida": cantidad,
                    "observaciones": request.form.get(f"item_obs_{lote_item.id}") or None,
                }
            )
    if not items:
        raise SolicitudInvalida("Indicá al menos un recurso o una cantidad ofrecida.")
    return items


@blueprint_ofertas.get("")
@requiere_permiso(OFERTAS_LISTAR)
def listar():
    """Pantalla de ofertas, opcionalmente filtrada por convocatoria."""
    convocatoria_id = request.args.get("convocatoria_id", type=int)
    consulta = db.select(Oferta).order_by(Oferta.actualizado_en.desc(), Oferta.id.desc())
    if convocatoria_id:
        consulta = consulta.where(Oferta.convocatoria_id == convocatoria_id)
    ofertas = list(db.session.execute(consulta).scalars().all())
    if pide_json():
        return jsonify(
            {
                "convocatoria_id": convocatoria_id,
                "ofertas": [_serializar_oferta(oferta) for oferta in ofertas],
            }
        )
    return render_template(
        "ofertas/listado.html",
        ofertas=ofertas,
        convocatoria_id=convocatoria_id,
    )


@blueprint_ofertas.get("/nueva")
@requiere_permiso(OFERTAS_CREAR)
def formulario_de_alta():
    """Pantalla para cargar una oferta sobre una convocatoria."""
    convocatoria_id = request.args.get("convocatoria_id", type=int)
    if convocatoria_id is None:
        raise SolicitudInvalida("Seleccioná una convocatoria antes de cargar la oferta.")
    return render_template(
        "ofertas/formulario.html",
        modo="alta",
        **_contexto_de_formulario(convocatoria_id),
    )


@blueprint_ofertas.post("/nueva")
@requiere_permiso(OFERTAS_CREAR)
def crear_desde_formulario():
    """Persiste una oferta enviada desde la pantalla web."""
    convocatoria_id = request.form.get("convocatoria_id", type=int)
    if convocatoria_id is None:
        raise SolicitudInvalida("La convocatoria es obligatoria.")
    convocatoria = db.session.get(Convocatoria, convocatoria_id)
    if not convocatoria:
        raise SolicitudInvalida("La convocatoria indicada no existe.")
    oferta = servicios.crear_oferta(
        convocatoria_id=convocatoria_id,
        usuario_id=current_user.id,
        organizacion_id=current_user.organizacion_id,
        items=_items_desde_formulario(convocatoria),
        observaciones=request.form.get("observaciones") or None,
    )
    return redirigir("ofertas.obtener", "Oferta registrada.", oferta_id=oferta.id)


def _serializar_oferta(oferta: Oferta) -> dict[str, Any]:
    """Serializa una entidad Oferta para respuestas JSON."""
    org = oferta.organizacion
    return {
        "id": oferta.id,
        "convocatoria_id": oferta.convocatoria_id,
        "usuario_id": oferta.usuario_id,
        "version": oferta.version,
        "estado": oferta.estado.value,
        "observaciones": oferta.observaciones,
        "organizacion": (
            {
                "id": org.id,
                "nombre": org.nombre,
                "identificador_nacional": org.identificador_nacional,
                "tipo": org.tipo.value,
            }
            if org
            else None
        ),
        "items": [
            {
                "id": linea.id,
                "lote_item_id": linea.lote_item_id,
                "cantidad_ofrecida": float(linea.cantidad_ofrecida),
                "observaciones": linea.observaciones,
                "recurso": (
                    {
                        "item_id": linea.lote_item.item.id,
                        "nombre": linea.lote_item.item.nombre,
                        "categoria": linea.lote_item.item.categoria.value,
                        "unidad_medida": linea.lote_item.item.unidad_medida,
                    }
                    if linea.lote_item and linea.lote_item.item
                    else None
                ),
            }
            for linea in oferta.items
        ],
        "creado_en": _formatear_fecha_iso(oferta.creado_en),
        "actualizado_en": _formatear_fecha_iso(oferta.actualizado_en),
    }


def _validar_token_bonita() -> None:
    """Verifica el token de servicio fijo configurado en BONITA_CALLBACK_TOKEN."""
    token_esperado = current_app.config.get("BONITA_CALLBACK_TOKEN")
    if not token_esperado:
        raise NoAutenticado("Token de autenticación de Bonita no configurado en el servidor.")

    token_recibido = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_recibido = auth_header[7:].strip()
    elif auth_header:
        token_recibido = auth_header.strip()
    else:
        token_recibido = request.headers.get("X-Bonita-Token")

    if not token_recibido or token_recibido != token_esperado:
        registrar_evento(
            logging.WARNING,
            "acceso_denegado_bonita",
            motivo="token_invalido_o_faltante",
            endpoint=request.path,
        )
        raise NoAutenticado("Token de autenticación de Bonita inválido o faltante.")


@blueprint_ofertas.post("")
@requiere_permiso(OFERTAS_CREAR)
def crear():
    """Registra una nueva oferta simple para una convocatoria activa."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise SolicitudInvalida("El cuerpo de la solicitud debe ser un JSON válido.")

    convocatoria_id = datos.get("convocatoria_id")
    if not convocatoria_id:
        raise SolicitudInvalida(
            "Debe especificarse el id de la convocatoria.",
            detalle={"campo": "convocatoria_id"},
        )

    items = datos.get("items")
    if not items or not isinstance(items, list):
        raise SolicitudInvalida(
            "La oferta debe incluir la lista de ítems ofrecidos.",
            detalle={"campo": "items"},
        )

    # Identificar el usuario
    usuario_id = datos.get("usuario_id")
    if not usuario_id and current_user.is_authenticated:
        usuario_id = getattr(current_user, "id", None)

    if not usuario_id:
        raise SolicitudInvalida(
            "Debe especificarse el usuario que presenta la oferta.",
            detalle={"campo": "usuario_id"},
        )

    # Identificar la organización oferente
    organizacion_id = datos.get("organizacion_id")
    if not organizacion_id and current_user.is_authenticated:
        organizacion_id = getattr(current_user, "organizacion_id", None)

    if not organizacion_id:
        raise SolicitudInvalida(
            "Debe especificarse la organización de la oferta.",
            detalle={"campo": "organizacion_id"},
        )

    observaciones = datos.get("observaciones")

    oferta = servicios.crear_oferta(
        convocatoria_id=int(convocatoria_id),
        usuario_id=int(usuario_id),
        organizacion_id=int(organizacion_id),
        items=items,
        observaciones=observaciones,
    )
    return jsonify(_serializar_oferta(oferta)), 201


@blueprint_ofertas.get("/<int:oferta_id>")
@requiere_permiso(OFERTAS_LISTAR)
def obtener(oferta_id: int):
    """Devuelve el detalle de una oferta simple."""
    oferta = servicios.obtener_oferta_por_id(oferta_id)
    if not pide_json():
        historial = []
        for version in servicios.obtener_historial_de_oferta(oferta_id):
            try:
                items = json.loads(version.items_snapshot)
            except (TypeError, json.JSONDecodeError):
                items = []
            historial.append(
                {
                    "version": version.version,
                    "items": items,
                    "fecha": version.registrado_en,
                    "observaciones": version.observaciones_anteriores,
                }
            )
        return render_template("ofertas/detalle.html", oferta=oferta, historial=historial)
    return jsonify(_serializar_oferta(oferta)), 200


@blueprint_ofertas.get("/<int:oferta_id>/edicion")
@requiere_permiso(OFERTAS_EDITAR)
def formulario_de_edicion(oferta_id: int):
    """Pantalla de edición de una oferta mientras la convocatoria siga abierta."""
    oferta = servicios.obtener_oferta_por_id(oferta_id)
    return render_template(
        "ofertas/formulario.html",
        modo="edicion",
        **_contexto_de_formulario(oferta.convocatoria_id, oferta),
    )


@blueprint_ofertas.post("/<int:oferta_id>/edicion")
@requiere_permiso(OFERTAS_EDITAR)
def editar_desde_formulario(oferta_id: int):
    """Guarda una nueva versión de una oferta enviada desde la pantalla web."""
    oferta = servicios.obtener_oferta_por_id(oferta_id)
    modificada = servicios.modificar_oferta(
        oferta_id,
        items=_items_desde_formulario(oferta.convocatoria),
        observaciones=request.form.get("observaciones") or None,
        usuario_id=current_user.id,
    )
    return redirigir("ofertas.obtener", "Versión actualizada.", oferta_id=modificada.id)


@blueprint_ofertas.put("/<int:oferta_id>")
@requiere_permiso(OFERTAS_EDITAR)
def modificar(oferta_id: int):
    """Modifica una oferta simple existente incrementando su versión."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise SolicitudInvalida("El cuerpo de la solicitud debe ser un JSON válido.")

    items = datos.get("items")
    observaciones = datos.get("observaciones")
    organizacion_id = datos.get("organizacion_id")
    usuario_id = datos.get("usuario_id")
    if not usuario_id and current_user.is_authenticated:
        usuario_id = getattr(current_user, "id", None)

    oferta = servicios.modificar_oferta(
        oferta_id,
        items=items,
        observaciones=observaciones,
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
    )
    return jsonify(_serializar_oferta(oferta)), 200


@blueprint_ofertas.post("/<int:oferta_id>/retirar")
@requiere_permiso(OFERTAS_RETIRAR)
def retirar(oferta_id: int):
    """Retira una oferta de ayuda de la convocatoria."""
    oferta = servicios.retirar_oferta(oferta_id)
    return jsonify(_serializar_oferta(oferta)), 200


@blueprint_ofertas.get("/<int:oferta_id>/historial")
@requiere_permiso(OFERTAS_LISTAR)
def obtener_historial(oferta_id: int):
    """Devuelve el historial cronológico de versiones anteriores de una oferta."""
    versiones = servicios.obtener_historial_de_oferta(oferta_id)
    resultado = []
    for v in versiones:
        items_data: list[Any] = []
        try:
            items_data = json.loads(v.items_snapshot)
        except Exception:
            pass
        resultado.append(
            {
                "id": v.id,
                "oferta_id": v.oferta_id,
                "version": v.version,
                "estado_anterior": v.estado_anterior,
                "observaciones_anteriores": v.observaciones_anteriores,
                "items": items_data,
                "modificado_por": v.modificado_por,
                "registrado_en": _formatear_fecha_iso(v.registrado_en),
            }
        )
    return jsonify({"oferta_id": oferta_id, "versiones": resultado}), 200


@blueprint_ofertas.get("/convocatoria/<int:convocatoria_id>")
@requiere_permiso(OFERTAS_LISTAR)
def listar_por_convocatoria(convocatoria_id: int):
    """Lista las ofertas registradas para una convocatoria."""
    incluir_retiradas = request.args.get("incluir_retiradas", "").lower() in (
        "true",
        "1",
        "si",
        "yes",
    )
    ofertas = servicios.listar_ofertas_por_convocatoria(
        convocatoria_id, incluir_retiradas=incluir_retiradas
    )
    return (
        jsonify(
            {
                "convocatoria_id": convocatoria_id,
                "ofertas": [_serializar_oferta(o) for o in ofertas],
            }
        ),
        200,
    )


@blueprint_ofertas.get("/consolidadas/<int:convocatoria_id>")
@csrf.exempt
def consolidadas_para_bonita(convocatoria_id: int):
    """Endpoint de integración #4 consumido por Bonita al cerrar la ventana temporal.

    Se autentica exclusivamente con BONITA_CALLBACK_TOKEN y no requiere sesión de usuario.
    """
    _validar_token_bonita()
    resultado = servicios.obtener_ofertas_consolidadas_para_bonita(convocatoria_id)
    return jsonify(resultado), 200
