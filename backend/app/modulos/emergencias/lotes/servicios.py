"""Servicios de negocio del módulo de lotes de necesidad.

Implementa el eslabón 2 del enunciado:
el Centro Coordinador Regional desglosa una emergencia en Lotes
compuestos por Items cuantificados (LoteItem).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.errores import (
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.emergencias.modelos import (
    Emergencia, EstadoEmergencia, EstadoLote, Item, LoteItem, LoteNecesidad,
)

def obtener_emergencia(emergencia_id: int) -> Emergencia:
    emergencia = db.session.get(Emergencia, emergencia_id)
    if not emergencia:
        raise RecursoNoEncontrado(
            f"No encontramos la emergencia con id {emergencia_id}."
        )
    return emergencia


def _validar_emergencia_para_lotes(emergencia: Emergencia) -> None:
    """Solo se pueden generar lotes sobre emergencias registradas o en evaluación."""
    estados_validos = {EstadoEmergencia.registrada, EstadoEmergencia.en_evaluacion}
    if emergencia.estado not in estados_validos:
        raise ReglaDeNegocioIncumplida(
            f"No se pueden generar lotes para una emergencia en estado "
            f"'{emergencia.estado.value}'.",
            detalle={"emergencia_id": emergencia.id, "estado": emergencia.estado.value},
        )


def listar_items() -> list[Item]:
    """Catálogo maestro de ítems, ordenado por categoría y nombre."""
    return list(
        db.session.scalars(
            select(Item).order_by(Item.categoria.asc(), Item.nombre.asc())
        )
    )


def _parsear_cantidad(valor: str | float | Decimal | None) -> Decimal:
    if valor is None or valor == "":
        raise SolicitudInvalida(
            "La cantidad es obligatoria.",
            detalle={"campo": "cantidad_solicitada"},
        )
    try:
        cantidad = Decimal(str(valor))
    except (InvalidOperation, ValueError) as error:
        raise SolicitudInvalida(
            "La cantidad debe ser un número válido.",
            detalle={"campo": "cantidad_solicitada"},
        ) from error
    if cantidad <= 0:
        raise SolicitudInvalida(
            "La cantidad debe ser mayor a cero.",
            detalle={"campo": "cantidad_solicitada"},
        )
    return cantidad



def crear_lotes(
    *,
    emergencia_id: int,
    descripcion: str | None,
    items: list[dict],
) -> list[LoteNecesidad]:
    """Crea uno o más lotes para una emergencia.

    Cada elemento de `items` debe tener la forma:
        {"item_id": int, "cantidad_solicitada": str|Decimal, "observaciones": str|None}

    Por simplicidad, todos los ítems enviados desde el formulario se agrupan
    en un único LoteNecesidad. Si más adelante querés soportar múltiples
    lotes en un mismo envío, cambiá la firma para recibir una lista de lotes.
    """
    emergencia = obtener_emergencia(emergencia_id)
    _validar_emergencia_para_lotes(emergencia)

    if not items:
        raise SolicitudInvalida(
            "Debés cargar al menos un ítem en el lote.",
            detalle={"campo": "items"},
        )

    descripcion = (descripcion or "").strip() or None
    if descripcion and len(descripcion) > 255:
        raise SolicitudInvalida(
            "La descripción del lote no puede superar los 255 caracteres.",
            detalle={"campo": "descripcion"},
        )

    # Validar ítems y armar los LoteItem
    lote_items: list[LoteItem] = []
    for indice, fila in enumerate(items):
        item_id = fila.get("item_id")
        if not item_id:
            raise SolicitudInvalida(
                f"Falta el ítem en la fila {indice + 1}.",
                detalle={"campo": f"items[{indice}].item_id"},
            )

        item = db.session.get(Item, int(item_id))
        if not item:
            raise RecursoNoEncontrado(
                f"No existe el ítem con id {item_id}.",
                detalle={"campo": f"items[{indice}].item_id"},
            )

        cantidad = _parsear_cantidad(fila.get("cantidad_solicitada"))
        observaciones = (fila.get("observaciones") or "").strip() or None

        lote_items.append(
            LoteItem(
                item_id=item.id,
                cantidad_solicitada=cantidad,
                observaciones=observaciones,
            )
        )

    # Crear el lote con sus ítems (cascade="all, delete-orphan" en LoteNecesidad.lote_items)
    lote = LoteNecesidad(
        emergencia_id=emergencia.id,
        descripcion=descripcion,
        estado=EstadoLote.pendiente,
        lote_items=lote_items,
    )
    db.session.add(lote)

    #
    #
    # Al generar el primer lote, la emergencia pasa a estar en_evaluación (sale de "registrada")
    if emergencia.estado == EstadoEmergencia.registrada:
        emergencia.estado = EstadoEmergencia.en_evaluacion
    #
    #
    # 

    db.session.commit()

    registrar_evento(
        logging.INFO,
        "lote_creado",
        emergencia_id=emergencia.id,
        lote_id=lote.id,
        cantidad_items=len(lote_items),
    )

    return [lote]


def listar_lotes_por_emergencia(emergencia_id: int) -> list[LoteNecesidad]:
    """Devuelve los lotes de una emergencia con sus ítems ya cargados."""
    return list(
        db.session.scalars(
            select(LoteNecesidad)
            .where(LoteNecesidad.emergencia_id == emergencia_id)
            .options(selectinload(LoteNecesidad.lote_items).selectinload(LoteItem.item))
            .order_by(LoteNecesidad.creado_en.asc())
        )
    )


def listar_lotes() -> list[LoteNecesidad]:
    """Devuelve todos los lotes con sus ítems ya cargados."""
    return list(
        db.session.scalars(
            select(LoteNecesidad)
            .where(LoteNecesidad.estado != EstadoLote.cancelado)
            .options(selectinload(LoteNecesidad.lote_items).selectinload(LoteItem.item))
            .order_by(LoteNecesidad.creado_en.asc())
        )
    )

