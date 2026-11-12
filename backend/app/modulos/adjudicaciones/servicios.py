"""Reglas de negocio para seleccionar ofertas evaluadas por el sistema nacional."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.errores import (
    ConflictoDeEstado,
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia
from app.modulos.notificaciones import servicios as servicios_de_notificaciones
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, TipoAsignacion


def obtener_convocatoria(convocatoria_id: int, municipio_id: int) -> Convocatoria:
    convocatoria = db.session.scalar(
        select(Convocatoria)
        .join(Emergencia)
        .where(Convocatoria.id == convocatoria_id, Emergencia.municipio_id == municipio_id)
        .options(
            selectinload(Convocatoria.emergencia),
            selectinload(Convocatoria.lotes),
            selectinload(Convocatoria.ofertas).selectinload(Oferta.items),
        ),
    )
    if not convocatoria:
        raise RecursoNoEncontrado("No encontramos la convocatoria solicitada.")
    if convocatoria.emergencia.estado != EstadoEmergencia.activa:
        raise ReglaDeNegocioIncumplida(
            "La emergencia ya no está pendiente de atención.",
            codigo="EMERGENCIA_NO_PENDIENTE",
        )
    if not convocatoria.cobertura_completa:
        raise ReglaDeNegocioIncumplida(
            "La selección solo está disponible cuando la cobertura fue completada.",
            codigo="COBERTURA_INCOMPLETA",
        )
    return convocatoria


def listar_convocatorias_pendientes(municipio_id: int) -> list[Convocatoria]:
    return list(
        db.session.scalars(
            select(Convocatoria)
            .join(Emergencia)
            .where(
                Emergencia.municipio_id == municipio_id,
                Emergencia.estado == EstadoEmergencia.activa,
                Convocatoria.cobertura_completa.is_(True),
                Convocatoria.estado == EstadoConvocatoria.cerrada,
            )
            .options(selectinload(Convocatoria.emergencia))
            .order_by(Convocatoria.cobertura_evaluada_en.desc(), Convocatoria.id.desc())
        )
    )


def _limite_con_margen(cantidad: int) -> int:
    return int((Decimal(cantidad) * Decimal("1.25")).to_integral_value(rounding=ROUND_CEILING))


def _cobertura_minima(cantidad: int) -> int:
    return int((Decimal(cantidad) * Decimal("0.75")).to_integral_value(rounding=ROUND_CEILING))


def seleccionar_lineas(convocatoria: Convocatoria, linea_ids: list[int]) -> list[Oferta]:
    if convocatoria.estado == EstadoConvocatoria.adjudicada:
        raise ConflictoDeEstado(
            "La selección de esta convocatoria ya fue confirmada y no puede modificarse."
        )
    if convocatoria.estado != EstadoConvocatoria.cerrada:
        raise ConflictoDeEstado("La convocatoria no está disponible para confirmar una selección.")
    if not isinstance(linea_ids, list) or any(type(linea_id) is not int for linea_id in linea_ids):
        raise SolicitudInvalida("La selección contiene líneas inválidas.")
    if not linea_ids:
        raise SolicitudInvalida("Seleccioná al menos una línea de oferta.")

    ofertas = list(
        db.session.scalars(
            select(Oferta)
            .where(Oferta.convocatoria_id == convocatoria.id)
            .options(selectinload(Oferta.items))
            .with_for_update()
        )
    )
    lineas = [linea for oferta in ofertas for linea in oferta.items]
    lineas_por_id = {linea.id: linea for linea in lineas}
    if len(set(linea_ids)) != len(linea_ids) or any(
        linea_id not in lineas_por_id for linea_id in linea_ids
    ):
        raise SolicitudInvalida("La selección contiene líneas que no pertenecen a la convocatoria.")

    linea_ids_seleccionadas = set(linea_ids)
    lineas_seleccionadas = [lineas_por_id[linea_id] for linea_id in linea_ids]
    cantidades_por_item: dict[int, int] = defaultdict(int)
    requeridas_por_item: dict[int, int] = {}
    limites = {
        lote_item.id: _limite_con_margen(int(lote_item.cantidad_solicitada))
        for lote in convocatoria.lotes
        for lote_item in lote.lote_items
    }
    for lote in convocatoria.lotes:
        for lote_item in lote.lote_items:
            requeridas_por_item[lote_item.id] = int(lote_item.cantidad_solicitada)

    for linea in lineas_seleccionadas:
        oferta = linea.oferta
        if oferta.estado not in (EstadoOferta.presentada, EstadoOferta.adjudicada):
            raise ConflictoDeEstado(
                "Solo se pueden seleccionar líneas de ofertas presentadas y evaluadas."
            )
        if linea.tipo_asignacion not in (TipoAsignacion.principal, TipoAsignacion.apoyo):
            raise ReglaDeNegocioIncumplida(
                "Solo se pueden seleccionar líneas habilitadas por el Sistema Nacional."
            )
        cantidades_por_item[linea.lote_item_id] += int(linea.cantidad_ofrecida)

    excedentes = [
        lote_item_id
        for lote_item_id, cantidad in cantidades_por_item.items()
        if cantidad > limites.get(lote_item_id, 0)
    ]
    if excedentes:
        raise ReglaDeNegocioIncumplida(
            "La selección supera el margen del 25% permitido para un lote de necesidad.",
            detalle={"lote_item_ids": excedentes},
            codigo="SELECCION_SUPERA_MARGEN",
        )

    faltantes = [
        lote_item_id
        for lote_item_id, requerida in requeridas_por_item.items()
        if cantidades_por_item[lote_item_id] < _cobertura_minima(requerida)
    ]
    if faltantes:
        raise ReglaDeNegocioIncumplida(
            "La selección debe cubrir al menos el 75% de cada ítem solicitado.",
            detalle={"lote_item_ids": faltantes},
            codigo="SELECCION_NO_CUBRE_MINIMO",
        )

    for linea in lineas:
        linea.seleccionada = linea.id in linea_ids_seleccionadas

    resultados: list[tuple[Oferta, bool]] = []
    for oferta in ofertas:
        tiene_lineas_seleccionadas = any(linea.seleccionada for linea in oferta.items)
        if tiene_lineas_seleccionadas:
            era_adjudicada = oferta.estado == EstadoOferta.adjudicada
            oferta.estado = EstadoOferta.adjudicada
            if not era_adjudicada:
                resultados.append((oferta, True))
        elif oferta.estado in (EstadoOferta.presentada, EstadoOferta.adjudicada):
            oferta.estado = EstadoOferta.rechazada
            resultados.append((oferta, False))

    for oferta, adjudicada in resultados:
        servicios_de_notificaciones.notificar_resultado_adjudicacion(oferta, adjudicada)
    convocatoria.estado = EstadoConvocatoria.adjudicada
    db.session.commit()
    return [oferta for oferta in ofertas if any(linea.seleccionada for linea in oferta.items)]


def construir_compromisos_json(convocatoria: Convocatoria) -> str:
    """Construye el JSON de compromisos para el Sistema Nacional."""

    aportes_agrupados = {}

    for oferta in convocatoria.ofertas:
        for linea in oferta.items:
            if not linea.seleccionada:
                continue

            organizacion = linea.organizacion
            recurso = linea.lote_item.item

            identificador = organizacion.identificador_nacional

            if not identificador:
                raise ReglaDeNegocioIncumplida(
                    "Una ONG seleccionada no tiene identificador nacional."
                )

            clave = (identificador, recurso.codigo_recurso)

            if clave not in aportes_agrupados:
                aportes_agrupados[clave] = {
                    "identificador_nacional": identificador,
                    "codigo_recurso": recurso.codigo_recurso,
                    "cantidad": 0,
                    "tipo_asignacion": linea.tipo_asignacion.value,
                }
            elif aportes_agrupados[clave]["tipo_asignacion"] != linea.tipo_asignacion.value:
                raise ReglaDeNegocioIncumplida(
                    "Un mismo recurso de una ONG tiene tipos de asignación diferentes."
                )

            aportes_agrupados[clave]["cantidad"] += linea.cantidad_ofrecida

    if not aportes_agrupados:
        raise ReglaDeNegocioIncumplida("No hay líneas seleccionadas para generar compromisos.")

    emergencia = convocatoria.emergencia

    compromisos = {
        "emergencia_externa_id": str(emergencia.id),
        "nivel_gravedad": emergencia.nivel_gravedad.name.upper(),
        "aportes": list(aportes_agrupados.values()),
    }

    return json.dumps(compromisos, ensure_ascii=False)


def obtener_datos_integracion_bonita(
    convocatoria: Convocatoria,
) -> tuple[str, str, str]:
    """Obtiene los datos necesarios para completar la tarea en Bonita."""

    case_id = convocatoria.emergencia.bonita_case_id

    if not case_id:
        raise ReglaDeNegocioIncumplida("La emergencia no tiene un proceso asociado en Bonita.")

    compromisos_json = construir_compromisos_json(convocatoria)

    ongs_no_seleccionadas_json = construir_ongs_no_seleccionadas_json(convocatoria)

    return case_id, compromisos_json, ongs_no_seleccionadas_json


def construir_ongs_no_seleccionadas_json(convocatoria: Convocatoria) -> str:
    """Obtiene los identificadores nacionales de las ONG rechazadas."""
    identificadores = set()

    for oferta in convocatoria.ofertas:
        if oferta.estado != EstadoOferta.rechazada:
            continue

        for linea in oferta.items:
            identificador = linea.organizacion.identificador_nacional

            if not identificador:
                raise ReglaDeNegocioIncumplida("Una ONG rechazada no tiene identificador nacional.")

            identificadores.add(identificador)

    return json.dumps(sorted(identificadores), ensure_ascii=False)
