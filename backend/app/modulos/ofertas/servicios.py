"""Servicios de negocio del módulo de ofertas colaborativas.

Implementa la lógica del eslabón 3 del TP:
- Carga de ofertas simples de ayuda durante la ventana temporal de la convocatoria.
- Modificación de ofertas con versionado incremental.
- Retiro de ofertas.
- Consolidación de ofertas para la integración #4 con Bonita.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Select, case, func, select

from app.core.errores import (
    ConflictoDeEstado,
    PermisoDenegado,
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, DecisionCobertura
from app.modulos.convocatorias.servicios import cerrar_convocatorias_vencidas
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    LoteItem,
    LoteNecesidad,
    TipoNecesidad,
)
from app.modulos.notificaciones import servicios as servicios_de_notificaciones
from app.modulos.ofertas.modelos import (
    EstadoOferta,
    Oferta,
    OfertaLinea,
    OfertaOrganizacion,
    OfertaVersion,
    TipoAsignacion,
)
from app.modulos.organizaciones.modelos import (
    Inventario,
    InventarioItem,
    Organizacion,
    TipoOrganizacion,
)

# Clasificaciones del Sistema Nacional que habilitan un aporte: lo que cubre la necesidad.
ASIGNACIONES_HABILITADAS = (TipoAsignacion.principal, TipoAsignacion.apoyo)

# Ofertas que ya no comprometen nada: sus lineas no cubren necesidades aunque esten habilitadas.
ESTADOS_DE_OFERTA_SIN_COMPROMISO = (EstadoOferta.retirada, EstadoOferta.rechazada)


def _formatear_fecha_iso(fecha: datetime | None) -> str | None:
    """Devuelve una fecha en formato ISO-8601 UTC con sufijo Z."""
    if fecha is None:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=UTC)
    else:
        fecha = fecha.astimezone(UTC)
    return fecha.strftime("%Y-%m-%dT%H:%M:%SZ")


def _validar_ventana_convocatoria(convocatoria: Convocatoria) -> None:
    """Verifica que la convocatoria esté abierta y dentro de la ventana de recepción."""
    cerrar_convocatorias_vencidas(emergencia_id=convocatoria.emergencia_id)
    if not convocatoria.esta_vigente():
        fecha_cierre_str = _formatear_fecha_iso(convocatoria.fecha_cierre)
        registrar_evento(
            logging.WARNING,
            "oferta_rechazada_fuera_de_ventana",
            convocatoria_id=convocatoria.id,
            estado_convocatoria=convocatoria.estado.value,
            fecha_cierre=fecha_cierre_str,
        )
        raise ReglaDeNegocioIncumplida(
            "La ventana de recepción de ofertas está cerrada.",
            codigo="OFERTA_FUERA_DE_VENTANA",
            detalle=[
                {
                    "campo": "convocatoria_id",
                    "motivo": f"Convocatoria no vigente o cerrada el {fecha_cierre_str}",
                }
            ],
        )


def _validar_y_obtener_organizacion(organizacion_id: int) -> Organizacion:
    """Valida y obtiene la organización para una oferta simple."""
    if not organizacion_id:
        raise SolicitudInvalida(
            "Debe especificarse la organización de la oferta.",
            detalle={"campo": "organizacion_id"},
        )

    org = db.session.get(Organizacion, organizacion_id)
    if not org:
        raise RecursoNoEncontrado(f"Organización con id {organizacion_id} no encontrada.")

    if not org.activo:
        raise ReglaDeNegocioIncumplida(
            f"La organización '{org.nombre}' no se encuentra activa.",
            detalle={"organizacion_id": org.id},
        )

    if org.tipo != TipoOrganizacion.ong:
        raise ReglaDeNegocioIncumplida(
            f"La organización '{org.nombre}' debe ser de tipo ONG para presentar ofertas.",
            detalle={"organizacion_id": org.id, "tipo": org.tipo.value},
        )

    return org


def _validar_y_procesar_items(
    items_datos: list[dict[str, Any]], convocatoria: Convocatoria
) -> list[dict[str, Any]]:
    """Valida que los ítems pertenezcan a los lotes de la emergencia de la convocatoria."""
    if not items_datos:
        raise SolicitudInvalida(
            "La oferta debe incluir al menos un ítem ofrecido.",
            detalle={"campo": "items"},
        )

    lote_item_ids = [d.get("lote_item_id") for d in items_datos]
    if any(lid is None for lid in lote_item_ids):
        raise SolicitudInvalida("Cada ítem de la oferta debe incluir su 'lote_item_id'.")

    if len(lote_item_ids) != len(set(lote_item_ids)):
        raise SolicitudInvalida("No se puede ofertar dos veces el mismo ítem en una sola oferta.")

    # Consultar lote_items
    consulta = select(LoteItem).where(LoteItem.id.in_(lote_item_ids))
    lote_items = db.session.execute(consulta).scalars().all()
    lote_item_dict = {li.id: li for li in lote_items}

    for item_dato in items_datos:
        li_id = item_dato["lote_item_id"]
        if li_id not in lote_item_dict:
            raise RecursoNoEncontrado(f"El ítem de lote con id {li_id} no existe.")

        li = lote_item_dict[li_id]
        if li.lote.convocatoria_id != convocatoria.id:
            raise ReglaDeNegocioIncumplida(
                f"El ítem {li_id} no pertenece a esta convocatoria.",
                detalle={"lote_item_id": li_id, "convocatoria_id": convocatoria.id},
            )

        cantidad = item_dato.get("cantidad_ofrecida")
        try:
            cantidad_decimal = Decimal(str(cantidad)) if cantidad is not None else None
        except InvalidOperation:
            cantidad_decimal = None
        if cantidad_decimal is None or not cantidad_decimal.is_finite():
            raise SolicitudInvalida(
                f"La cantidad ofrecida para el ítem {li_id} debe ser un número válido.",
                detalle={"lote_item_id": li_id, "cantidad_ofrecida": cantidad},
            )
        if cantidad_decimal != cantidad_decimal.to_integral_value():
            raise SolicitudInvalida(
                f"La cantidad ofrecida para el ítem {li_id} debe ser un número entero.",
                detalle={"lote_item_id": li_id, "cantidad_ofrecida": cantidad},
            )
        if cantidad_decimal <= 0:
            raise SolicitudInvalida(
                f"La cantidad ofrecida para el ítem {li_id} debe ser mayor a 0.",
                detalle={"lote_item_id": li_id, "cantidad_ofrecida": cantidad},
            )
        cantidad = int(cantidad_decimal)
        item_dato["cantidad_ofrecida"] = cantidad

        if cantidad > li.cantidad_solicitada:
            raise ReglaDeNegocioIncumplida(
                f"La cantidad ofrecida ({cantidad}) supera la cantidad requerida "
                f"({li.cantidad_solicitada}) para el ítem {li_id}.",
                detalle={
                    "lote_item_id": li_id,
                    "cantidad_ofrecida": cantidad,
                    "cantidad_solicitada": int(li.cantidad_solicitada),
                },
            )

    return items_datos


def _validar_disponibilidad_en_inventario(
    organizacion_id: int,
    items_datos: list[dict[str, Any]],
) -> None:
    """Verifica que la ONG tenga stock local suficiente para cada ítem ofertado."""
    lote_item_ids = [item["lote_item_id"] for item in items_datos]
    lote_items = db.session.execute(
        select(LoteItem).where(LoteItem.id.in_(lote_item_ids))
    ).scalars()
    item_id_por_lote = {lote_item.id: lote_item.item_id for lote_item in lote_items}

    inventario_items = db.session.execute(
        select(InventarioItem)
        .join(Inventario)
        .where(
            Inventario.organizacion_id == organizacion_id,
            InventarioItem.item_id.in_(item_id_por_lote.values()),
        )
    ).scalars()
    stock_por_item = {item.item_id: item for item in inventario_items}

    for dato in items_datos:
        item_id = item_id_por_lote[dato["lote_item_id"]]
        inventario_item = stock_por_item.get(item_id)
        if inventario_item is None:
            raise ReglaDeNegocioIncumplida(
                "La organización no tiene este recurso en su inventario.",
                detalle={"lote_item_id": dato["lote_item_id"]},
            )

        cantidad = Decimal(str(dato["cantidad_ofrecida"]))
        disponible = Decimal(str(inventario_item.cantidad_disponible))
        if cantidad > disponible:
            raise ReglaDeNegocioIncumplida(
                f"La cantidad ofrecida ({cantidad}) supera el stock disponible ({disponible}).",
                detalle={
                    "lote_item_id": dato["lote_item_id"],
                    "cantidad_ofrecida": int(cantidad),
                    "cantidad_disponible": int(disponible),
                },
            )


def _validar_totales_del_consorcio(
    oferta: Oferta | None,
    items_datos: list[dict[str, Any]],
    organizacion_id: int,
) -> None:
    """Impide que la suma de aportes del consorcio supere cada necesidad."""
    aportes_existentes: dict[int, Decimal] = {}
    if oferta is not None:
        for linea in oferta.items:
            if linea.organizacion_id != organizacion_id:
                aportes_existentes[linea.lote_item_id] = aportes_existentes.get(
                    linea.lote_item_id, Decimal("0")
                ) + Decimal(str(linea.cantidad_ofrecida))

    lote_items = db.session.execute(
        select(LoteItem).where(LoteItem.id.in_([item["lote_item_id"] for item in items_datos]))
    ).scalars()
    lote_item_por_id = {lote_item.id: lote_item for lote_item in lote_items}
    for item_dato in items_datos:
        lote_item_id = item_dato["lote_item_id"]
        total = aportes_existentes.get(lote_item_id, Decimal("0")) + Decimal(
            str(item_dato["cantidad_ofrecida"])
        )
        cantidad_requerida = Decimal(str(lote_item_por_id[lote_item_id].cantidad_solicitada))
        if total > cantidad_requerida:
            raise ReglaDeNegocioIncumplida(
                f"El aporte acumulado ({total}) supera la cantidad requerida "
                f"({cantidad_requerida}) para el ítem {lote_item_id}.",
                codigo="OFERTA_CONJUNTA_SUPERA_NECESIDAD",
                detalle={
                    "lote_item_id": lote_item_id,
                    "cantidad_acumulada": int(total),
                    "cantidad_solicitada": int(cantidad_requerida),
                },
            )


def _validar_organizaciones_conjuntas(
    organizaciones_ids: list[int], organizacion_lider_id: int
) -> list[Organizacion]:
    """Valida las organizaciones ONG que participarán junto a la líder."""
    organizaciones = []
    ids_vistos = set()
    for organizacion_id in organizaciones_ids:
        if organizacion_id in ids_vistos or organizacion_id == organizacion_lider_id:
            continue
        ids_vistos.add(organizacion_id)
        organizaciones.append(_validar_y_obtener_organizacion(organizacion_id))
    return organizaciones


def _validar_organizaciones_sin_oferta(convocatoria_id: int, organizaciones_ids: list[int]) -> None:
    """Impide que una organización participe en más de una oferta activa."""
    if not organizaciones_ids:
        return

    organizaciones_ocupadas = set(
        db.session.execute(
            select(OfertaOrganizacion.organizacion_id)
            .join(Oferta, Oferta.id == OfertaOrganizacion.oferta_id)
            .where(
                Oferta.convocatoria_id == convocatoria_id,
                OfertaOrganizacion.organizacion_id.in_(organizaciones_ids),
                Oferta.estado.notin_([EstadoOferta.retirada, EstadoOferta.rechazada]),
            )
        ).scalars()
    )
    if organizaciones_ocupadas:
        raise ReglaDeNegocioIncumplida(
            "Una organización no puede tener más de una oferta activa en la misma convocatoria.",
            codigo="ORGANIZACION_YA_TIENE_OFERTA",
            detalle={"organizacion_ids": sorted(organizaciones_ocupadas)},
        )


def _actualizar_estado_por_invitaciones(oferta: Oferta) -> None:
    """Deriva el estado de la oferta a partir de las respuestas del consorcio."""
    if any(m.estado_participacion == "rechazada" for m in oferta.organizaciones_consorcio):
        oferta.estado = EstadoOferta.rechazada
    elif any(m.estado_participacion == "pendiente" for m in oferta.organizaciones_consorcio):
        oferta.estado = EstadoOferta.pendiente
    else:
        oferta.estado = EstadoOferta.presentada


def crear_oferta(
    *,
    convocatoria_id: int,
    usuario_id: int,
    organizacion_id: int,
    items: list[dict[str, Any]],
    observaciones: str | None = None,
    organizaciones_ids: list[int] | None = None,
) -> Oferta:
    """Registra una nueva oferta simple para una convocatoria activa.
        organizacion_id: ID de la ONG que presenta la oferta.
        items: Lista de dicts `{"lote_item_id": int, "cantidad_ofrecida": float,
            "observaciones": str | None}`.
        observaciones: Notas adicionales sobre la oferta.
        organizaciones_ids: IDs de las ONG participantes además de la líder.
    Returns:
        Oferta: La entidad persistida con sus relaciones.
    """
    convocatoria = db.session.get(Convocatoria, convocatoria_id)
    if not convocatoria:
        raise RecursoNoEncontrado(f"Convocatoria con id {convocatoria_id} no encontrada.")

    _validar_ventana_convocatoria(convocatoria)
    org_validada = _validar_y_obtener_organizacion(organizacion_id)
    organizaciones_validas = _validar_organizaciones_conjuntas(
        organizaciones_ids or [], org_validada.id
    )
    _validar_organizaciones_sin_oferta(
        convocatoria.id,
        [org_validada.id, *(organizacion.id for organizacion in organizaciones_validas)],
    )
    items_validados = _validar_y_procesar_items(items, convocatoria)
    _validar_disponibilidad_en_inventario(org_validada.id, items_validados)
    _validar_totales_del_consorcio(None, items_validados, org_validada.id)

    oferta = Oferta(
        convocatoria_id=convocatoria.id,
        usuario_id=usuario_id,
        version=1,
        estado=EstadoOferta.pendiente if organizaciones_validas else EstadoOferta.presentada,
        observaciones=observaciones,
    )
    db.session.add(oferta)
    db.session.flush()  # Para obtener oferta.id

    oferta_org = OfertaOrganizacion(
        oferta_id=oferta.id,
        organizacion_id=org_validada.id,
        rol_consorcio="lider",
        estado_participacion="aceptada",
    )
    db.session.add(oferta_org)
    for organizacion in organizaciones_validas:
        db.session.add(
            OfertaOrganizacion(
                oferta_id=oferta.id,
                organizacion_id=organizacion.id,
                rol_consorcio="aportante",
                estado_participacion="pendiente",
            )
        )

    for item_dato in items_validados:
        linea = OfertaLinea(
            oferta_id=oferta.id,
            lote_item_id=item_dato["lote_item_id"],
            cantidad_ofrecida=item_dato["cantidad_ofrecida"],
            observaciones=item_dato.get("observaciones"),
            organizacion_id=org_validada.id,
        )
        db.session.add(linea)

    db.session.commit()

    for organizacion in organizaciones_validas:
        servicios_de_notificaciones.crear(
            organizacion_id=organizacion.id,
            titulo="Invitación a una oferta conjunta",
            mensaje=(
                f"La ONG {org_validada.nombre} te invitó a participar en una oferta conjunta "
                f"para la emergencia «{convocatoria.emergencia.titulo}»."
            ),
            enlace=f"/ofertas/{oferta.id}",
        )
    if organizaciones_validas:
        db.session.commit()

    registrar_evento(
        logging.INFO,
        "oferta_creada",
        oferta_id=oferta.id,
        convocatoria_id=convocatoria.id,
        organizacion_id=org_validada.id,
        total_items=len(items_validados),
    )
    return oferta


def _serializar_items_para_snapshot(oferta: Oferta) -> str:
    """Serializa las líneas actuales de la oferta a JSON para guardar en la versión histórica."""
    items = []
    for linea in oferta.items:
        dato: dict[str, Any] = {
            "id": linea.id,
            "lote_item_id": linea.lote_item_id,
            "cantidad_ofrecida": int(linea.cantidad_ofrecida),
            "observaciones": linea.observaciones,
        }
        if linea.lote_item and linea.lote_item.item:
            dato["recurso"] = {
                "item_id": linea.lote_item.item.id,
                "nombre": linea.lote_item.item.nombre,
                "categoria": linea.lote_item.item.categoria.value,
                "unidad_medida": linea.lote_item.item.unidad_medida,
            }
        items.append(dato)
    return json.dumps(items, ensure_ascii=False)


def _guardar_snapshot_version(oferta: Oferta, usuario_id: int | None = None) -> OfertaVersion:
    """Registra una snapshot histórica en OfertaVersion antes de aplicar modificaciones."""
    estado_str = oferta.estado.value if hasattr(oferta.estado, "value") else str(oferta.estado)
    version_hist = OfertaVersion(
        oferta_id=oferta.id,
        version=oferta.version,
        estado_anterior=estado_str,
        observaciones_anteriores=oferta.observaciones,
        items_snapshot=_serializar_items_para_snapshot(oferta),
        modificado_por=usuario_id,
    )
    db.session.add(version_hist)
    db.session.flush()
    return version_hist


def _validar_organizacion_de_oferta(
    oferta: Oferta,
    organizacion_id: int | None,
) -> None:
    """Impide que una organizacion opere una oferta ajena."""
    if organizacion_id is None:
        return
    miembro = next(
        (
            miembro
            for miembro in oferta.organizaciones_consorcio
            if miembro.organizacion_id == organizacion_id
        ),
        None,
    )
    if miembro is None:
        raise PermisoDenegado("No puedes operar una oferta de otra organización.")
    if miembro.estado_participacion != "aceptada":
        raise ConflictoDeEstado("Debes aceptar la invitación antes de aportar a la oferta.")


def modificar_oferta(
    oferta_id: int,
    *,
    items: list[dict[str, Any]] | None = None,
    observaciones: str | None = None,
    organizacion_id: int | None = None,
    organizaciones_ids: list[int] | None = None,
    usuario_id: int | None = None,
) -> Oferta:
    """Modifica una oferta existente, incrementando su versión.

    Solo es posible si la convocatoria se encuentra aún vigente y la oferta
    no fue retirada ni adjudicada.
    """
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")

    _validar_organizacion_de_oferta(oferta, organizacion_id)
    _validar_ventana_convocatoria(oferta.convocatoria)
    if organizaciones_ids is not None:
        raise PermisoDenegado(
            "La composición de la oferta no puede modificarse durante la edición."
        )

    if oferta.estado == EstadoOferta.retirada:
        raise ConflictoDeEstado("No se puede modificar una oferta que ya ha sido retirada.")
    if oferta.estado in (EstadoOferta.adjudicada, EstadoOferta.rechazada):
        raise ConflictoDeEstado(
            f"No se puede modificar una oferta en estado final '{oferta.estado.value}'."
        )

    items_validados = None
    hubo_cambios = False
    if items is not None:
        items_validados = _validar_y_procesar_items(items, oferta.convocatoria)
        _validar_disponibilidad_en_inventario(
            organizacion_id or oferta.organizacion_lider.id, items_validados
        )
        _validar_totales_del_consorcio(
            oferta,
            items_validados,
            organizacion_id or oferta.organizacion_lider.id,
        )

        items_actuales = {
            linea.lote_item_id: {
                "cantidad_ofrecida": linea.cantidad_ofrecida,
                "observaciones": linea.observaciones,
            }
            for linea in oferta.items
            if linea.organizacion_id == (organizacion_id or oferta.organizacion_lider.id)
        }
        if len(items_validados) != len(items_actuales):
            hubo_cambios = True
        else:
            for item_dato in items_validados:
                lote_item_id = item_dato["lote_item_id"]
                linea_actual = items_actuales.get(lote_item_id)
                if linea_actual is None:
                    hubo_cambios = True
                    break
                cantidad_nueva = Decimal(str(item_dato["cantidad_ofrecida"]))
                observaciones_nueva = item_dato.get("observaciones") or None
                if (
                    linea_actual["cantidad_ofrecida"] != cantidad_nueva
                    or (linea_actual["observaciones"] or None) != observaciones_nueva
                ):
                    hubo_cambios = True
                    break

    if observaciones is not None and (oferta.observaciones or "") != (observaciones or ""):
        hubo_cambios = True

    if not hubo_cambios:
        return oferta

    # Guardar snapshot de la versión que se va a reemplazar
    _guardar_snapshot_version(oferta, usuario_id=usuario_id)

    # Actualizar cabecera
    oferta.version += 1
    _actualizar_estado_por_invitaciones(oferta)
    if observaciones is not None:
        oferta.observaciones = observaciones

    # Actualizar ítems si fueron enviados
    if items_validados is not None:
        organizacion_editora = organizacion_id or oferta.organizacion_lider.id
        for linea in list(oferta.items):
            if linea.organizacion_id == organizacion_editora:
                db.session.delete(linea)
        db.session.flush()

        for item_dato in items_validados:
            linea = OfertaLinea(
                oferta_id=oferta.id,
                lote_item_id=item_dato["lote_item_id"],
                cantidad_ofrecida=item_dato["cantidad_ofrecida"],
                observaciones=item_dato.get("observaciones"),
                organizacion_id=organizacion_editora,
            )
            db.session.add(linea)

    db.session.commit()

    registrar_evento(
        logging.INFO,
        "oferta_modificada",
        oferta_id=oferta.id,
        nueva_version=oferta.version,
    )
    return oferta


def retirar_oferta(oferta_id: int, *, organizacion_id: int | None = None) -> Oferta:
    """Marca una oferta como retirada por parte de la ONG.

    Solo puede retirarse si la convocatoria sigue abierta.
    """
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")

    _validar_organizacion_de_oferta(oferta, organizacion_id)
    _validar_ventana_convocatoria(oferta.convocatoria)

    if oferta.estado == EstadoOferta.retirada:
        raise ConflictoDeEstado("La oferta ya se encuentra retirada.")
    if oferta.estado in (EstadoOferta.adjudicada, EstadoOferta.rechazada):
        raise ConflictoDeEstado(
            f"No se puede retirar una oferta en estado final '{oferta.estado.value}'."
        )

    oferta.estado = EstadoOferta.retirada
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "oferta_retirada",
        oferta_id=oferta.id,
        convocatoria_id=oferta.convocatoria_id,
    )
    return oferta


def aceptar_invitacion(
    oferta_id: int,
    *,
    organizacion_id: int,
    usuario_id: int,
    items: list[dict[str, Any]],
) -> Oferta:
    """Acepta una invitación y agrega el aporte de la ONG al consorcio."""
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")
    organizacion = _validar_y_obtener_organizacion(organizacion_id)
    _validar_ventana_convocatoria(oferta.convocatoria)
    if oferta.estado in (
        EstadoOferta.retirada,
        EstadoOferta.rechazada,
        EstadoOferta.adjudicada,
    ):
        raise ConflictoDeEstado(
            f"No se puede aceptar una invitación de una oferta en estado '{oferta.estado.value}'."
        )
    miembro = next(
        (m for m in oferta.organizaciones_consorcio if m.organizacion_id == organizacion_id),
        None,
    )
    if miembro is None:
        raise PermisoDenegado("Tu organización no fue invitada a esta oferta.")
    if miembro.estado_participacion != "pendiente":
        raise ConflictoDeEstado("La invitación ya no está pendiente de aceptación.")

    items_validados = _validar_y_procesar_items(items, oferta.convocatoria)
    _validar_disponibilidad_en_inventario(organizacion_id, items_validados)
    _validar_totales_del_consorcio(oferta, items_validados, organizacion_id)
    for item_dato in items_validados:
        db.session.add(
            OfertaLinea(
                oferta_id=oferta.id,
                lote_item_id=item_dato["lote_item_id"],
                cantidad_ofrecida=item_dato["cantidad_ofrecida"],
                observaciones=item_dato.get("observaciones"),
                organizacion_id=organizacion_id,
            )
        )
    miembro.estado_participacion = "aceptada"
    _actualizar_estado_por_invitaciones(oferta)
    oferta.version += 1
    servicios_de_notificaciones.crear(
        organizacion_id=oferta.organizacion_lider.id,
        titulo="Invitación aceptada",
        mensaje=(
            f"La ONG {organizacion.nombre} aceptó tu invitación a participar "
            f"en la oferta conjunta para la emergencia "
            f"«{oferta.convocatoria.emergencia.titulo}»."
        ),
        enlace=f"/ofertas/{oferta.id}",
    )
    db.session.commit()
    registrar_evento(
        logging.INFO,
        "invitacion_oferta_aceptada",
        oferta_id=oferta.id,
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
    )
    return oferta


def rechazar_invitacion(
    oferta_id: int,
    *,
    organizacion_id: int,
    usuario_id: int,
) -> Oferta:
    """Rechaza una invitación pendiente al consorcio."""
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")
    organizacion = _validar_y_obtener_organizacion(organizacion_id)
    _validar_ventana_convocatoria(oferta.convocatoria)
    if oferta.estado in (
        EstadoOferta.retirada,
        EstadoOferta.rechazada,
        EstadoOferta.adjudicada,
    ):
        raise ConflictoDeEstado(
            f"No se puede responder una invitación de una oferta en estado '{oferta.estado.value}'."
        )
    miembro = next(
        (m for m in oferta.organizaciones_consorcio if m.organizacion_id == organizacion_id),
        None,
    )
    if miembro is None:
        raise PermisoDenegado("Tu organización no fue invitada a esta oferta.")
    if miembro.estado_participacion != "pendiente":
        raise ConflictoDeEstado("La invitación ya no está pendiente de respuesta.")

    miembro.estado_participacion = "rechazada"
    _actualizar_estado_por_invitaciones(oferta)
    oferta.version += 1
    servicios_de_notificaciones.crear(
        organizacion_id=oferta.organizacion_lider.id,
        titulo="Invitación rechazada",
        mensaje=(
            f"La ONG {organizacion.nombre} rechazó tu invitación a participar "
            f"en la oferta conjunta para la emergencia "
            f"«{oferta.convocatoria.emergencia.titulo}»."
        ),
        enlace=f"/ofertas/{oferta.id}",
    )
    db.session.commit()
    registrar_evento(
        logging.INFO,
        "invitacion_oferta_rechazada",
        oferta_id=oferta.id,
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
    )
    return oferta


def obtener_oferta_por_id(oferta_id: int) -> Oferta:
    """Obtiene una oferta por su clave primaria o levanta RecursoNoEncontrado."""
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")
    return oferta


def listar_ofertas_por_convocatoria(
    convocatoria_id: int,
    *,
    incluir_retiradas: bool = False,
    organizacion_id: int | None = None,
) -> list[Oferta]:
    """Lista las ofertas asociadas a una convocatoria."""
    convocatoria = db.session.get(Convocatoria, convocatoria_id)
    if not convocatoria:
        raise RecursoNoEncontrado(f"Convocatoria con id {convocatoria_id} no encontrada.")

    consulta = (
        select(Oferta)
        .where(Oferta.convocatoria_id == convocatoria_id)
        .order_by(Oferta.creado_en.asc())
    )
    if organizacion_id is not None:
        consulta = consulta.join(OfertaOrganizacion).where(
            OfertaOrganizacion.organizacion_id == organizacion_id
        )
    if not incluir_retiradas:
        consulta = consulta.where(Oferta.estado != EstadoOferta.retirada)

    return list(db.session.execute(consulta).scalars().all())


def obtener_ofertas_consolidadas_para_bonita(convocatoria_id: int) -> dict[str, Any]:
    """Genera la carga útil consolidada de ofertas para el motor de procesos Bonita.

    Corresponde a la integración #4 descripta en `docs/arquitectura/componentes.md`.
    Se dispara típicamente al vencer el temporizador de la ventana de recepción.
    """
    convocatoria = db.session.get(Convocatoria, convocatoria_id)
    if not convocatoria:
        raise RecursoNoEncontrado(f"Convocatoria con id {convocatoria_id} no encontrada.")

    # Solo ofertas presentadas: las invitaciones pendientes aún no son compromisos.
    consulta = (
        select(Oferta)
        .where(
            Oferta.convocatoria_id == convocatoria_id,
            Oferta.estado == EstadoOferta.presentada,
        )
        .order_by(Oferta.id.asc())
    )
    ofertas_activas = db.session.execute(consulta).scalars().all()

    ofertas_json: list[dict[str, Any]] = []

    for oferta in ofertas_activas:
        fecha_creacion_iso = _formatear_fecha_iso(oferta.creado_en)

        organizaciones_json = [
            {
                "id": miembro.organizacion_id,
                "nombre": miembro.organizacion.nombre,
                "identificador_nacional": miembro.organizacion.identificador_nacional,
                "rol": miembro.rol_consorcio,
            }
            for miembro in sorted(
                oferta.organizaciones_consorcio,
                key=lambda miembro: (
                    miembro.rol_consorcio.lower() != "lider",
                    miembro.organizacion_id,
                ),
            )
            if miembro.estado_participacion == "aceptada"
        ]

        # Mantener la oferta como unidad y consolidar cada necesidad sin perder quién aporta.
        items_consolidados: dict[int, dict[str, Any]] = {}
        for linea in oferta.items:
            lote_item_id = linea.lote_item_id
            if lote_item_id not in items_consolidados:
                item = linea.lote_item.item
                items_consolidados[lote_item_id] = {
                    "item": item,
                    "cantidad_total": 0,
                    "aportes": [],
                }
            organizacion = linea.organizacion
            cantidad = int(linea.cantidad_ofrecida)
            datos_item = items_consolidados[lote_item_id]
            datos_item["cantidad_total"] += cantidad
            datos_item["aportes"].append(
                {
                    "cantidad": cantidad,
                    "identificador_nacional": organizacion.identificador_nacional,
                    "organizacion_id": organizacion.id,
                }
            )

        items_json = []
        for lote_item_id, datos in sorted(items_consolidados.items()):
            item = datos["item"]
            items_json.append(
                {
                    "aportes": sorted(
                        datos["aportes"],
                        key=lambda aporte: aporte["organizacion_id"],
                    ),
                    "cantidad_total": datos["cantidad_total"],
                    "codigo_recurso": item.codigo_recurso,
                    "lote_item_id": lote_item_id,
                    "tipo_recurso": item.categoria.value,
                    "unidad": item.unidad_medida,
                }
            )

        dato_oferta = {
            "fecha_creacion": fecha_creacion_iso,
            "items": items_json,
            "oferta_id": oferta.id,
            "organizaciones": organizaciones_json,
            "version": oferta.version,
        }
        ofertas_json.append(dato_oferta)

    return {
        "convocatoria_id": convocatoria.id,
        "emergencia_id": convocatoria.emergencia_id,
        "nivel_gravedad": convocatoria.emergencia.nivel_gravedad.value.upper(),
        "ventana_cerrada_en": _formatear_fecha_iso(convocatoria.fecha_cierre),
        "ofertas": ofertas_json,
    }


def obtener_historial_de_oferta(oferta_id: int) -> list[OfertaVersion]:
    """Obtiene el historial archivado de una oferta, ordenado por versión."""
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")

    consulta = (
        select(OfertaVersion)
        .where(OfertaVersion.oferta_id == oferta_id)
        .order_by(OfertaVersion.version.asc())
    )
    return list(db.session.execute(consulta).scalars().all())


def registrar_evaluacion_y_calcular_cobertura(datos: dict) -> dict:
    """Registra los aportes evaluados y calcula la cobertura de la convocatoria."""
    convocatoria_id = datos.get("convocatoria_id")
    evaluacion = datos.get("resultado_evaluacion")

    if (
        type(convocatoria_id) is not int
        or not isinstance(evaluacion, dict)
        or type(evaluacion.get("emergencia_id")) is not int
        or not isinstance(evaluacion.get("ofertas"), list)
    ):
        raise SolicitudInvalida("La evaluación recibida es inválida.")

    emergencia_id = evaluacion["emergencia_id"]
    convocatoria = db.session.get(Convocatoria, convocatoria_id)

    if convocatoria is None:
        raise SolicitudInvalida("La convocatoria no existe.")

    if convocatoria.emergencia_id != emergencia_id:
        raise SolicitudInvalida("La convocatoria no pertenece a la emergencia indicada.")

    lote_items = db.session.scalars(
        db.select(LoteItem)
        .join(LoteNecesidad)
        .where(
            LoteNecesidad.convocatoria_id == convocatoria_id,
            LoteNecesidad.emergencia_id == emergencia_id,
        )
    ).all()

    if not lote_items:
        raise SolicitudInvalida("La convocatoria no tiene necesidades registradas.")

    ids_lote = {item.id for item in lote_items}

    ofertas = db.session.scalars(
        db.select(Oferta).where(
            Oferta.convocatoria_id == convocatoria_id,
            Oferta.estado == EstadoOferta.presentada,
        )
    ).all()

    ofertas_por_id = {oferta.id: oferta for oferta in ofertas}
    ids_recibidos = set()
    actualizaciones = {}
    cantidades_habilitadas = defaultdict(int)

    for oferta_evaluada in evaluacion["ofertas"]:
        if not isinstance(oferta_evaluada, dict):
            raise SolicitudInvalida("Una oferta evaluada es inválida.")

        oferta_id = oferta_evaluada.get("oferta_id")
        if oferta_id not in ofertas_por_id or oferta_id in ids_recibidos:
            raise SolicitudInvalida("La evaluación contiene ofertas desconocidas o duplicadas.")

        ids_recibidos.add(oferta_id)
        oferta = ofertas_por_id[oferta_id]

        items = oferta_evaluada.get("items")
        if not isinstance(items, list):
            raise SolicitudInvalida("La oferta evaluada no contiene ítems válidos.")

        lineas_por_clave = {}
        for linea in oferta.items:
            clave = (linea.lote_item_id, linea.organizacion_id)
            if clave in lineas_por_clave:
                raise SolicitudInvalida("Existen aportes duplicados en la oferta original.")
            lineas_por_clave[clave] = linea

        claves_recibidas = set()

        for item in items:
            if not isinstance(item, dict):
                raise SolicitudInvalida("Ítem evaluado inválido.")

            lote_item_id = item.get("lote_item_id")
            aportes = item.get("aportes")

            if lote_item_id not in ids_lote or not isinstance(aportes, list):
                raise SolicitudInvalida("Ítem ajeno o aportes inválidos.")

            for aporte in aportes:
                if not isinstance(aporte, dict):
                    raise SolicitudInvalida("Aporte evaluado inválido.")

                clave = (lote_item_id, aporte.get("organizacion_id"))
                linea = lineas_por_clave.get(clave)

                if linea is None or clave in claves_recibidas:
                    raise SolicitudInvalida("Aporte inexistente o duplicado en la evaluación.")

                if (
                    type(aporte.get("cantidad")) is not int
                    or aporte["cantidad"] != linea.cantidad_ofrecida
                ):
                    raise SolicitudInvalida("La cantidad evaluada no coincide con la ofrecida.")

                try:
                    clasificacion = TipoAsignacion(aporte["clasificacion"])
                except (KeyError, ValueError, TypeError) as error:
                    raise SolicitudInvalida(
                        "Clasificación del Sistema Nacional inválida."
                    ) from error

                if clasificacion == TipoAsignacion.pendiente:
                    raise SolicitudInvalida("El Sistema Nacional devolvió un aporte pendiente.")

                claves_recibidas.add(clave)
                actualizaciones[linea.id] = (linea, clasificacion)

                if clasificacion in ASIGNACIONES_HABILITADAS:
                    cantidades_habilitadas[lote_item_id] += linea.cantidad_ofrecida

        if claves_recibidas != set(lineas_por_clave):
            raise SolicitudInvalida("La evaluación no contiene todos los aportes de la oferta.")

    if ids_recibidos != set(ofertas_por_id):
        raise SolicitudInvalida("La evaluación no contiene todas las ofertas presentadas.")

    detalle = []

    for item in lote_items:
        requerida = int(item.cantidad_solicitada)
        habilitada = cantidades_habilitadas[item.id]

        detalle.append(
            {
                "lote_item_id": item.id,
                "cantidad_requerida": requerida,
                "cantidad_habilitada": habilitada,
                "cantidad_faltante": max(0, requerida - habilitada),
            }
        )

    for linea, clasificacion in actualizaciones.values():
        linea.tipo_asignacion = clasificacion

    cobertura_previa = convocatoria.cobertura_completa
    evaluacion_previa = convocatoria.cobertura_evaluada_en is not None
    cobertura_completa = all(item["cantidad_faltante"] == 0 for item in detalle)
    cobertura_se_completo = cobertura_completa and not cobertura_previa
    cobertura_se_volvio_insuficiente = not cobertura_completa and (
        not evaluacion_previa or cobertura_previa
    )
    cantidad_total_solicitada = sum(item["cantidad_requerida"] for item in detalle)
    cantidad_total_cubierta = sum(
        min(item["cantidad_habilitada"], item["cantidad_requerida"]) for item in detalle
    )
    porcentaje_cobertura = (
        (
            Decimal(cantidad_total_cubierta) * Decimal("100") / Decimal(cantidad_total_solicitada)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if cantidad_total_solicitada
        else Decimal("0.00")
    )
    convocatoria.cobertura_completa = cobertura_completa
    convocatoria.cobertura_evaluada_en = datetime.now(UTC)
    convocatoria.porcentaje_cobertura = porcentaje_cobertura
    emergencia = db.session.get(Emergencia, emergencia_id)
    estado_anterior = emergencia.estado
    if emergencia.estado in (EstadoEmergencia.activa, EstadoEmergencia.registrada):
        emergencia.estado = (
            EstadoEmergencia.activa if cobertura_completa else EstadoEmergencia.registrada
        )
        if emergencia.estado != estado_anterior:
            servicios_de_notificaciones.notificar_cambio_estado_emergencia(
                emergencia, estado_anterior
            )
    if cobertura_se_completo:
        servicios_de_notificaciones.notificar_cobertura_completa(convocatoria)
    elif (
        cobertura_se_volvio_insuficiente
        and convocatoria.decision_cobertura == DecisionCobertura.pendiente
    ):
        servicios_de_notificaciones.notificar_cobertura_insuficiente(convocatoria)
    db.session.commit()

    return {
        "emergencia_id": emergencia_id,
        "convocatoria_id": convocatoria_id,
        "cobertura_completa": cobertura_completa,
        "porcentaje_cobertura": float(porcentaje_cobertura),
        "lotes": detalle,
    }


# --- Lectura agregada (panel de auditoria) ---------------------------------------


def consultar_unidades_habilitadas(*, lote_item_ids: Select[tuple[int]]) -> Select[tuple[int, int]]:
    """Subconsulta con las unidades habilitadas por el Sistema Nacional para cada item de lote.

    Columnas: `lote_item_id` y `cantidad_habilitada`, la suma de lo ofrecido en las lineas
    clasificadas como principal o apoyo, de ofertas que siguen en pie. Un item sin aportes
    habilitados no aparece. Es un `Select` para combinarla en una sola consulta.
    """
    return (
        select(
            OfertaLinea.lote_item_id.label("lote_item_id"),
            func.sum(OfertaLinea.cantidad_ofrecida).label("cantidad_habilitada"),
        )
        .join(Oferta, OfertaLinea.oferta_id == Oferta.id)
        .where(
            OfertaLinea.lote_item_id.in_(lote_item_ids),
            OfertaLinea.tipo_asignacion.in_(ASIGNACIONES_HABILITADAS),
            Oferta.estado.not_in(ESTADOS_DE_OFERTA_SIN_COMPROMISO),
        )
        .group_by(OfertaLinea.lote_item_id)
    )


def consultar_unidades_seleccionadas(
    *, lote_item_ids: Select[tuple[int]]
) -> Select[tuple[int, int]]:
    """Subconsulta con las unidades adjudicadas a cada item de lote.

    Columnas: `lote_item_id` y `cantidad_seleccionada`, la suma de lo ofrecido en las lineas que
    el municipio selecciono de ofertas adjudicadas. Un item sin lineas seleccionadas no aparece.
    """
    return (
        select(
            OfertaLinea.lote_item_id.label("lote_item_id"),
            func.sum(OfertaLinea.cantidad_ofrecida).label("cantidad_seleccionada"),
        )
        .join(Oferta, OfertaLinea.oferta_id == Oferta.id)
        .where(
            OfertaLinea.lote_item_id.in_(lote_item_ids),
            OfertaLinea.seleccionada.is_(True),
            Oferta.estado == EstadoOferta.adjudicada,
        )
        .group_by(OfertaLinea.lote_item_id)
    )


def consultar_ofertas_adjudicadas(
    *, convocatoria_ids: Select[tuple[int]]
) -> Select[tuple[int, int]]:
    """Subconsulta con las ofertas adjudicadas de esas convocatorias.

    Columnas: `oferta_id` y `convocatoria_id`.
    """
    return select(
        Oferta.id.label("oferta_id"),
        Oferta.convocatoria_id.label("convocatoria_id"),
    ).where(
        Oferta.convocatoria_id.in_(convocatoria_ids),
        Oferta.estado == EstadoOferta.adjudicada,
    )


# Participacion de una ONG que acepto sumarse a la oferta: la lider nace aceptada.
PARTICIPACION_ACEPTADA = "aceptada"


def consultar_participantes_aceptados(*, oferta_ids: Select[tuple[int]]) -> Select[tuple[int, int]]:
    """Subconsulta con las organizaciones que participan aceptadas de esas ofertas.

    Columnas: `oferta_id` y `organizacion_id`. Una oferta con mas de un participante aceptado es
    de consorcio.
    """
    return select(
        OfertaOrganizacion.oferta_id.label("oferta_id"),
        OfertaOrganizacion.organizacion_id.label("organizacion_id"),
    ).where(
        OfertaOrganizacion.oferta_id.in_(oferta_ids),
        OfertaOrganizacion.estado_participacion == PARTICIPACION_ACEPTADA,
    )


def consultar_lineas_seleccionadas(
    *, oferta_ids: Select[tuple[int]]
) -> Select[tuple[int, int, int, int]]:
    """Subconsulta con las lineas seleccionadas de esas ofertas.

    Columnas: `oferta_id`, `lote_item_id`, `organizacion_id` (la ONG que aporta la linea) y
    `cantidad`.
    """
    return select(
        OfertaLinea.oferta_id.label("oferta_id"),
        OfertaLinea.lote_item_id.label("lote_item_id"),
        OfertaLinea.organizacion_id.label("organizacion_id"),
        OfertaLinea.cantidad_ofrecida.label("cantidad"),
    ).where(
        OfertaLinea.oferta_id.in_(oferta_ids),
        OfertaLinea.seleccionada.is_(True),
    )


# Lo que el Sistema Nacional ya clasifico: habilitado (principal o apoyo) o no habilitado.
ASIGNACIONES_EVALUADAS = (*ASIGNACIONES_HABILITADAS, TipoAsignacion.rechazada)


@dataclass(frozen=True, slots=True)
class DemandaDeCategoria:
    """Unidades que piden los lotes de un rubro y como evaluo el Sistema Nacional lo ofertado.

    `evaluadas` son las unidades ofertadas que el Sistema Nacional clasifico y `no_habilitadas`
    las que de esas no habilito. Con `evaluadas` en 0 no hay tasa que calcular.
    """

    categoria: TipoNecesidad
    demandadas: int
    evaluadas: int
    no_habilitadas: int


def listar_demanda_e_inhabilitacion_por_categoria(
    *, emergencia_ids: Select[tuple[int]]
) -> list[DemandaDeCategoria]:
    """Demanda y evaluacion por rubro de los lotes de esas emergencias, en una sola consulta.

    Solo aparecen los rubros con alguna unidad pedida. Las ofertas retiradas no cuentan: lo que
    se retiro no es oferta de la red.
    """
    requeridas = servicios_de_emergencias.consultar_unidades_requeridas(
        emergencia_ids=emergencia_ids
    ).subquery()

    demanda = (
        select(
            requeridas.c.categoria.label("categoria"),
            func.sum(requeridas.c.cantidad_requerida).label("demandadas"),
        )
        .group_by(requeridas.c.categoria)
        .subquery()
    )
    no_habilitada = OfertaLinea.tipo_asignacion == TipoAsignacion.rechazada
    evaluacion = (
        select(
            requeridas.c.categoria.label("categoria"),
            func.sum(OfertaLinea.cantidad_ofrecida).label("evaluadas"),
            func.sum(case((no_habilitada, OfertaLinea.cantidad_ofrecida), else_=0)).label(
                "no_habilitadas"
            ),
        )
        .select_from(OfertaLinea)
        .join(requeridas, OfertaLinea.lote_item_id == requeridas.c.lote_item_id)
        .join(Oferta, OfertaLinea.oferta_id == Oferta.id)
        .where(
            OfertaLinea.tipo_asignacion.in_(ASIGNACIONES_EVALUADAS),
            Oferta.estado != EstadoOferta.retirada,
        )
        .group_by(requeridas.c.categoria)
        .subquery()
    )

    filas = db.session.execute(
        select(
            demanda.c.categoria,
            demanda.c.demandadas,
            func.coalesce(evaluacion.c.evaluadas, 0),
            func.coalesce(evaluacion.c.no_habilitadas, 0),
        ).outerjoin(evaluacion, evaluacion.c.categoria == demanda.c.categoria)
    ).all()
    return [
        DemandaDeCategoria(
            categoria=categoria,
            demandadas=int(demandadas),
            evaluadas=int(evaluadas),
            no_habilitadas=int(no_habilitadas),
        )
        for categoria, demandadas, evaluadas, no_habilitadas in filas
    ]
