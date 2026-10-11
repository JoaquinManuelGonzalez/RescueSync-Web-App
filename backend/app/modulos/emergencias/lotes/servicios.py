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
from app.modulos.convocatorias.modelos import EstadoConvocatoria
from app.modulos.convocatorias.servicios import cerrar_convocatorias_vencidas
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    Item,
    LoteItem,
    LoteNecesidad,
)
from app.modulos.notificaciones import servicios as servicios_de_notificaciones


def obtener_emergencia(emergencia_id: int) -> Emergencia:
    cerrar_convocatorias_vencidas(emergencia_id=emergencia_id)
    emergencia = db.session.get(Emergencia, emergencia_id)
    if not emergencia:
        raise RecursoNoEncontrado(f"No encontramos la emergencia con id {emergencia_id}.")
    return emergencia


def _validar_emergencia_para_lotes(emergencia: Emergencia) -> None:
    """Solo se pueden generar lotes mientras la emergencia está registrada."""
    if emergencia.estado != EstadoEmergencia.registrada:
        raise ReglaDeNegocioIncumplida(
            "Solo se pueden generar lotes mientras la emergencia está registrada.",
            detalle={"emergencia_id": emergencia.id, "estado": emergencia.estado.value},
        )


def listar_items() -> list[Item]:
    """Catálogo maestro de ítems, ordenado por categoría y nombre."""
    return list(db.session.scalars(select(Item).order_by(Item.categoria.asc(), Item.nombre.asc())))


def _parsear_cantidad(valor: str | int | float | Decimal | None) -> int:
    if valor is None or valor == "":
        raise SolicitudInvalida(
            "La cantidad es obligatoria.",
            detalle={"campo": "cantidad_solicitada"},
        )
    try:
        cantidad = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError) as error:
        raise SolicitudInvalida(
            "La cantidad debe ser un número válido.",
            detalle={"campo": "cantidad_solicitada"},
        ) from error
    if not cantidad.is_finite() or cantidad != cantidad.to_integral_value():
        raise SolicitudInvalida(
            "La cantidad debe ser un número entero.",
            detalle={"campo": "cantidad_solicitada"},
        )
    if cantidad <= 0:
        raise SolicitudInvalida(
            "La cantidad debe ser mayor a cero.",
            detalle={"campo": "cantidad_solicitada"},
        )
    return int(cantidad)


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

    estado_anterior = emergencia.estado
    emergencia.estado = EstadoEmergencia.en_evaluacion
    servicios_de_notificaciones.notificar_cambio_estado_emergencia(emergencia, estado_anterior)

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


def obtener_lote(lote_id: int) -> LoteNecesidad:
    """
    Recupera un lote con sus ítems cargados.
    """
    lote = db.session.scalar(
        select(LoteNecesidad)
        .where(LoteNecesidad.id == lote_id)
        .options(selectinload(LoteNecesidad.lote_items).selectinload(LoteItem.item))
    )
    if not lote:
        raise RecursoNoEncontrado(f"No encontramos el lote con id {lote_id}.")
    return lote


def _validar_edicion_permitida(lote: LoteNecesidad) -> None:
    """
    Reglas de negocio para permitir la edición de un lote:
    1. La Emergencia debe seguir en un estado editable.
    2. El Lote debe estar en estado pendiente.
    3. Lote debe tener su Convocatoria en estado "borrador", o no tener Convocatoria asignada.
    """

    # Regla 1
    if lote.emergencia.estado in (
        EstadoEmergencia.cancelada,
        EstadoEmergencia.finalizada,
    ):
        raise ReglaDeNegocioIncumplida(
            "No se pueden editar lotes de una emergencia finalizada o cancelada.",
            detalle={"emergencia_id": lote.emergencia_id, "estado": lote.emergencia.estado.value},
        )

    # Regla 2
    if lote.estado != EstadoLote.pendiente:
        if lote.estado == EstadoLote.en_convocatoria:
            raise ReglaDeNegocioIncumplida(
                "No se puede editar un lote que ya está vinculado a una convocatoria.",
                detalle={"lote_id": lote.id},
            )
        elif lote.estado in (EstadoLote.adjudicado_parcial, EstadoLote.adjudicado_total):
            raise ReglaDeNegocioIncumplida(
                "No se puede editar un lote ya adjudicado.",
                detalle={"lote_id": lote.id},
            )
        elif lote.estado == EstadoLote.cancelado:
            raise ReglaDeNegocioIncumplida(
                "No se puede editar un lote cancelado.",
                detalle={"lote_id": lote.id},
            )

    # Regla 3
    if lote.convocatoria_id is not None and lote.convocatoria.estado != EstadoConvocatoria.borrador:
        raise ReglaDeNegocioIncumplida(
            "Existe una convocatoria abierta para esta emergencia; no se pueden editar sus lotes.",
            detalle={"emergencia_id": lote.emergencia_id},
        )


def editar_lote(
    *,
    lote_id: int,
    descripcion: str | None,
    items: list[dict],
) -> LoteNecesidad:
    """
    Actualiza un lote existente (descripción + ítems) validando ciertas reglas.
    Reemplaza por completo los LoteItem del lote.(*)
    """
    lote = obtener_lote(lote_id)
    _validar_edicion_permitida(lote)

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

    nuevos_items: list[LoteItem] = []
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

        nuevos_items.append(
            LoteItem(
                item_id=item.id,
                cantidad_solicitada=cantidad,
                observaciones=observaciones,
            )
        )

    # Reemplazo total de los ítems(*)
    lote.descripcion = descripcion
    lote.lote_items = nuevos_items

    db.session.commit()

    registrar_evento(
        logging.INFO,
        "lote_editado",
        emergencia_id=lote.emergencia_id,
        lote_id=lote.id,
        cantidad_items=len(nuevos_items),
    )

    return lote
