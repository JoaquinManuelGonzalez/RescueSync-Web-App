"""Endpoints de gestión de convocatorias."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, flash, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import select

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import (
    COBERTURA_INSUFICIENTE_GESTIONAR,
    CONVOCATORIAS_CERRAR,
    CONVOCATORIAS_CREAR,
    CONVOCATORIAS_LISTAR,
)
from app.core.errores import ErrorDeAplicacion, RecursoNoEncontrado, SolicitudInvalida
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.paginacion import parametros_de_paginacion
from app.core.interfaz.plantillas import ZONA_HORARIA_DE_LA_INTERFAZ
from app.core.interfaz.vistas import ERROR, pide_json, redirigir
from app.extensiones import db
from app.modulos.convocatorias import servicios
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.convocatorias.servicios import (
    aceptar_cobertura_parcial,
    cerrar_convocatoria,
    cerrar_convocatorias_vencidas,
    crear_convocatoria,
    obtener_convocatoria_con_cobertura_insuficiente,
    puede_aceptar_cobertura_parcial,
    reabrir_convocatoria_por_cobertura_insuficiente,
)
from app.modulos.emergencias import servicios as servicios_emergencias
from app.modulos.emergencias.modelos import EstadoEmergencia
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, OfertaOrganizacion

blueprint_convocatorias = Blueprint("convocatorias", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="convocatorias.listar",
    titulo="Convocatorias",
    permiso=CONVOCATORIAS_LISTAR,
    descripcion="Publicación de convocatorias por emergencia",
    icono="lista",
    orden=40,
)


def _es_operador_municipal() -> bool:
    return current_user.tiene_rol("operador_municipal")


def _oferta_activa_de_ong(convocatoria: Convocatoria) -> Oferta | None:
    if not current_user.tiene_rol("representante_ong") or current_user.organizacion_id is None:
        return None
    return db.session.execute(
        select(Oferta)
        .join(OfertaOrganizacion, OfertaOrganizacion.oferta_id == Oferta.id)
        .where(
            Oferta.convocatoria_id == convocatoria.id,
            OfertaOrganizacion.organizacion_id == current_user.organizacion_id,
            Oferta.estado.notin_([EstadoOferta.retirada, EstadoOferta.rechazada]),
        )
        .limit(1)
    ).scalar_one_or_none()


def _ong_puede_presentar_oferta(convocatoria: Convocatoria) -> bool:
    return (
        current_user.tiene_rol("representante_ong")
        and convocatoria.esta_vigente()
        and _oferta_activa_de_ong(convocatoria) is None
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
        "convocatorias/formulario.html",
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
        fecha = datetime.strptime(f"{fecha_valor.strip()} {hora_valor.strip()}", "%Y-%m-%d %H:%M")
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
    estado = request.args.get("estado") or None
    texto = request.args.get("texto") or None
    municipio_id = current_user.organizacion_id if _es_operador_municipal() else None
    es_representante_ong = current_user.tiene_rol("representante_ong")
    if pide_json():
        convocatorias = servicios.listar_convocatorias(
            estado=estado, texto=texto, municipio_id=municipio_id
        )
    else:
        pagina, por_pagina = parametros_de_paginacion()
        resultado = servicios.paginar_convocatorias(
            pagina=pagina,
            por_pagina=por_pagina,
            estado=estado,
            texto=texto,
            municipio_id=municipio_id,
        )
        convocatorias = resultado.elementos
    if pide_json():
        return jsonify(
            {
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
            }
        )
    return render_template(
        "convocatorias/listado.html",
        convocatorias=convocatorias,
        es_representante_ong=es_representante_ong,
        convocatorias_con_oferta={
            convocatoria.id
            for convocatoria in convocatorias
            if not _ong_puede_presentar_oferta(convocatoria)
        },
        ofertas_de_ong={
            convocatoria.id: oferta
            for convocatoria in convocatorias
            if (oferta := _oferta_activa_de_ong(convocatoria)) is not None
        },
        pagina=resultado,
        filtros=request.args,
        opciones_de_estado=[
            ("abierta", "Abierta"),
            ("cerrada", "Cerrada"),
            ("adjudicada", "Adjudicada"),
            ("cancelada", "Cancelada"),
        ],
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
    if (
        _es_operador_municipal()
        and convocatoria.emergencia.municipio_id != current_user.organizacion_id
    ):
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
                "cobertura_completa": convocatoria.cobertura_completa,
                "cobertura_evaluada_en": (
                    convocatoria.cobertura_evaluada_en.isoformat()
                    if convocatoria.cobertura_evaluada_en
                    else None
                ),
                "porcentaje_cobertura": float(convocatoria.porcentaje_cobertura),
                "decision_cobertura": convocatoria.decision_cobertura,
            }
        )
    return render_template(
        "convocatorias/detalle.html",
        convocatoria=convocatoria,
        ong_puede_presentar_oferta=_ong_puede_presentar_oferta(convocatoria),
        oferta_de_ong=_oferta_activa_de_ong(convocatoria),
    )


@blueprint_convocatorias.get("/<int:convocatoria_id>/cobertura-insuficiente")
@requiere_permiso(COBERTURA_INSUFICIENTE_GESTIONAR)
def cobertura_insuficiente(convocatoria_id: int):
    """Panel de decisión disponible mientras la cobertura incompleta esté pendiente."""
    convocatoria = obtener_convocatoria_con_cobertura_insuficiente(convocatoria_id)
    aceptacion_parcial_habilitada = puede_aceptar_cobertura_parcial(convocatoria)
    if pide_json():
        return jsonify(
            {
                "convocatoria_id": convocatoria.id,
                "emergencia_id": convocatoria.emergencia_id,
                "porcentaje_cobertura": float(convocatoria.porcentaje_cobertura),
                "aceptacion_parcial_habilitada": aceptacion_parcial_habilitada,
                "ofertas": [
                    {
                        "id": oferta.id,
                        "estado": oferta.estado.value,
                        "items": [
                            {
                                "item": linea.lote_item.item.nombre,
                                "organizacion": linea.organizacion.nombre,
                                "cantidad": linea.cantidad_ofrecida,
                                "clasificacion": linea.tipo_asignacion.value,
                            }
                            for linea in oferta.items
                        ],
                    }
                    for oferta in convocatoria.ofertas
                ],
            }
        )
    return render_template(
        "convocatorias/cobertura_insuficiente.html",
        convocatoria=convocatoria,
        aceptacion_parcial_habilitada=aceptacion_parcial_habilitada,
    )


@blueprint_convocatorias.post("/<int:convocatoria_id>/cobertura-insuficiente/aceptar-parcial")
@requiere_permiso(COBERTURA_INSUFICIENTE_GESTIONAR)
def aceptar_cobertura_insuficiente(convocatoria_id: int):
    """Acepta la cobertura parcial si alcanza el mínimo y habilita la selección municipal."""
    try:
        convocatoria = aceptar_cobertura_parcial(convocatoria_id)
    except ErrorDeAplicacion as error:
        if pide_json():
            raise
        flash(error.mensaje, ERROR)
        return redirigir(
            "convocatorias.cobertura_insuficiente",
            convocatoria_id=convocatoria_id,
        )
    return redirigir(
        "convocatorias.obtener",
        "Cobertura parcial aceptada. El municipio ya puede seleccionar las ofertas.",
        convocatoria_id=convocatoria.id,
        datos_json={
            "mensaje": "Cobertura parcial aceptada.",
            "convocatoria_id": convocatoria.id,
        },
    )


@blueprint_convocatorias.post("/<int:convocatoria_id>/cobertura-insuficiente/reabrir")
@requiere_permiso(COBERTURA_INSUFICIENTE_GESTIONAR)
def reabrir_por_cobertura_insuficiente(convocatoria_id: int):
    """Devuelve la emergencia al registro sin modificar la convocatoria cerrada."""
    try:
        emergencia = reabrir_convocatoria_por_cobertura_insuficiente(convocatoria_id)
    except ErrorDeAplicacion as error:
        if pide_json():
            raise
        flash(error.mensaje, ERROR)
        return redirigir(
            "convocatorias.cobertura_insuficiente",
            convocatoria_id=convocatoria_id,
        )
    return redirigir(
        "emergencias.obtener",
        "Emergencia reabierta. Podés crear nuevos lotes para otra convocatoria.",
        datos_json={
            "mensaje": "Emergencia reabierta.",
            "emergencia_id": emergencia.id,
        },
        emergencia_id=emergencia.id,
    )


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
