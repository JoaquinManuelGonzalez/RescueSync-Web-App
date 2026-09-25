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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.core.errores import (
    ConflictoDeEstado,
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.emergencias.modelos import LoteItem
from app.modulos.ofertas.modelos import (
    EstadoOferta,
    Oferta,
    OfertaLinea,
    OfertaOrganizacion,
    OfertaVersion,
)
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion


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
        if li.lote.emergencia_id != convocatoria.emergencia_id:
            raise ReglaDeNegocioIncumplida(
                f"El ítem {li_id} no pertenece a la emergencia atendida por esta convocatoria.",
                detalle={"lote_item_id": li_id, "emergencia_id": convocatoria.emergencia_id},
            )

        cantidad = item_dato.get("cantidad_ofrecida")
        if cantidad is None or Decimal(str(cantidad)) <= 0:
            raise SolicitudInvalida(
                f"La cantidad ofrecida para el ítem {li_id} debe ser mayor a 0.",
                detalle={"lote_item_id": li_id, "cantidad_ofrecida": cantidad},
            )

        if Decimal(str(cantidad)) > li.cantidad_solicitada:
            raise ReglaDeNegocioIncumplida(
                f"La cantidad ofrecida ({cantidad}) supera la cantidad requerida "
                f"({li.cantidad_solicitada}) para el ítem {li_id}.",
                detalle={
                    "lote_item_id": li_id,
                    "cantidad_ofrecida": float(cantidad),
                    "cantidad_solicitada": float(li.cantidad_solicitada),
                },
            )

    return items_datos


def crear_oferta(
    *,
    convocatoria_id: int,
    usuario_id: int,
    organizacion_id: int,
    items: list[dict[str, Any]],
    observaciones: str | None = None,
) -> Oferta:
    """Registra una nueva oferta simple para una convocatoria activa.

    Args:
        convocatoria_id: ID de la convocatoria sobre la que se presenta.
        usuario_id: ID del usuario (representante ONG) que carga la oferta.
        organizacion_id: ID de la ONG que presenta la oferta.
        items: Lista de dicts `{"lote_item_id": int, "cantidad_ofrecida": float,
            "observaciones": str | None}`.
        observaciones: Notas adicionales sobre la oferta.

    Returns:
        Oferta: La entidad persistida con sus relaciones.
    """
    convocatoria = db.session.get(Convocatoria, convocatoria_id)
    if not convocatoria:
        raise RecursoNoEncontrado(f"Convocatoria con id {convocatoria_id} no encontrada.")

    _validar_ventana_convocatoria(convocatoria)
    org_validada = _validar_y_obtener_organizacion(organizacion_id)
    items_validados = _validar_y_procesar_items(items, convocatoria)

    oferta = Oferta(
        convocatoria_id=convocatoria.id,
        usuario_id=usuario_id,
        version=1,
        estado=EstadoOferta.presentada,
        observaciones=observaciones,
    )
    db.session.add(oferta)
    db.session.flush()  # Para obtener oferta.id

    oferta_org = OfertaOrganizacion(
        oferta_id=oferta.id,
        organizacion_id=org_validada.id,
        rol_consorcio="lider",
    )
    db.session.add(oferta_org)

    for item_dato in items_validados:
        linea = OfertaLinea(
            oferta_id=oferta.id,
            lote_item_id=item_dato["lote_item_id"],
            cantidad_ofrecida=Decimal(str(item_dato["cantidad_ofrecida"])),
            observaciones=item_dato.get("observaciones"),
        )
        db.session.add(linea)

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
            "cantidad_ofrecida": float(linea.cantidad_ofrecida),
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


def _guardar_snapshot_version(
    oferta: Oferta, usuario_id: int | None = None
) -> OfertaVersion:
    """Registra una snapshot histórica en OfertaVersion antes de aplicar modificaciones."""
    estado_str = (
        oferta.estado.value if hasattr(oferta.estado, "value") else str(oferta.estado)
    )
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


def modificar_oferta(
    oferta_id: int,
    *,
    items: list[dict[str, Any]] | None = None,
    observaciones: str | None = None,
    organizacion_id: int | None = None,
    usuario_id: int | None = None,
) -> Oferta:
    """Modifica una oferta existente, incrementando su versión.

    Solo es posible si la convocatoria se encuentra aún vigente y la oferta
    no fue retirada ni adjudicada.
    """
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")

    _validar_ventana_convocatoria(oferta.convocatoria)

    if oferta.estado == EstadoOferta.retirada:
        raise ConflictoDeEstado("No se puede modificar una oferta que ya ha sido retirada.")
    if oferta.estado in (EstadoOferta.adjudicada, EstadoOferta.rechazada):
        raise ConflictoDeEstado(
            f"No se puede modificar una oferta en estado final '{oferta.estado.value}'."
        )

    # Guardar snapshot de la versión que se va a reemplazar
    _guardar_snapshot_version(oferta, usuario_id=usuario_id)

    # Actualizar cabecera
    oferta.version += 1
    oferta.estado = EstadoOferta.modificada
    if observaciones is not None:
        oferta.observaciones = observaciones

    # Actualizar organización oferente si fue enviada
    if organizacion_id is not None:
        org_validada = _validar_y_obtener_organizacion(organizacion_id)
        for org_asoc in list(oferta.organizaciones_consorcio):
            db.session.delete(org_asoc)
        db.session.flush()

        oferta_org = OfertaOrganizacion(
            oferta_id=oferta.id,
            organizacion_id=org_validada.id,
            rol_consorcio="lider",
        )
        db.session.add(oferta_org)

    # Actualizar ítems si fueron enviados
    if items is not None:
        items_validados = _validar_y_procesar_items(items, oferta.convocatoria)
        for linea in list(oferta.items):
            db.session.delete(linea)
        db.session.flush()

        for item_dato in items_validados:
            linea = OfertaLinea(
                oferta_id=oferta.id,
                lote_item_id=item_dato["lote_item_id"],
                cantidad_ofrecida=Decimal(str(item_dato["cantidad_ofrecida"])),
                observaciones=item_dato.get("observaciones"),
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


def retirar_oferta(oferta_id: int) -> Oferta:
    """Marca una oferta como retirada por parte de la ONG.

    Solo puede retirarse si la convocatoria sigue abierta.
    """
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")

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


def obtener_oferta_por_id(oferta_id: int) -> Oferta:
    """Obtiene una oferta por su clave primaria o levanta RecursoNoEncontrado."""
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")
    return oferta


def listar_ofertas_por_convocatoria(
    convocatoria_id: int, *, incluir_retiradas: bool = False
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

    # Solo ofertas activas (no retiradas ni rechazadas)
    consulta = (
        select(Oferta)
        .where(
            Oferta.convocatoria_id == convocatoria_id,
            Oferta.estado.notin_([EstadoOferta.retirada, EstadoOferta.rechazada]),
        )
        .order_by(Oferta.id.asc())
    )
    ofertas_activas = db.session.execute(consulta).scalars().all()

    ofertas_json: list[dict[str, Any]] = []

    for oferta in ofertas_activas:
        lider = oferta.organizacion_lider
        lider_id = lider.id if lider else None
        lider_nombre = lider.nombre if lider else "Sin Organización"
        fecha_creacion_iso = _formatear_fecha_iso(oferta.creado_en)

        for linea in oferta.items:
            item = linea.lote_item.item
            dato_oferta: dict[str, Any] = {
                "oferta_id": oferta.id,
                "ong_id": lider_id,
                "ong_nombre": lider_nombre,
                "tipo_recurso": item.categoria.value,
                "cantidad": float(linea.cantidad_ofrecida),
                "unidad": item.unidad_medida,
                "es_consorcio": False,
                "fecha_creacion": fecha_creacion_iso,
            }
            ofertas_json.append(dato_oferta)

    return {
        "convocatoria_id": convocatoria.id,
        "emergencia_id": convocatoria.emergencia_id,
        "ventana_cerrada_en": _formatear_fecha_iso(convocatoria.fecha_cierre),
        "ofertas": ofertas_json,
    }


def obtener_historial_de_oferta(oferta_id: int) -> list[OfertaVersion]:
    """Obtiene el historial de versiones anteriores archivadas de una oferta, ordenadas por versión."""
    oferta = db.session.get(Oferta, oferta_id)
    if not oferta:
        raise RecursoNoEncontrado(f"Oferta con id {oferta_id} no encontrada.")

    consulta = (
        select(OfertaVersion)
        .where(OfertaVersion.oferta_id == oferta_id)
        .order_by(OfertaVersion.version.asc())
    )
    return list(db.session.execute(consulta).scalars().all())
