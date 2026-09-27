"""Datos semilla de lotes y convocatorias para probar el flujo de ofertas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    Item,
    LoteItem,
    LoteNecesidad,
)
from app.modulos.usuarios_roles.modelos import Usuario

TITULO_EMERGENCIA_DEMO = "Temporal severo con voladura de techos en Chascomús"
DESCRIPCION_LOTE_DEMO = "Recursos iniciales para asistencia y evacuación"
MARCA_CONVOCATORIA_DEMO = "SEED_DEMO_OFERTAS"

ITEMS_DEL_LOTE: tuple[tuple[str, float], ...] = (
    ("Agua potable envasada", 1000),
    ("Raciones de alimento no perecedero", 500),
    ("Paramédicos", 5),
)


@registrar("convocatorias")
def sembrar_convocatorias() -> list[ResultadoSemilla]:
    """Crea el lote y la convocatoria abierta usados por la demo de ofertas."""
    emergencia = Emergencia.query.filter_by(titulo=TITULO_EMERGENCIA_DEMO).first()
    if emergencia is None:
        raise ValueError(f"Emergencia demo no encontrada: {TITULO_EMERGENCIA_DEMO!r}")

    lote, lote_creado = obtener_o_crear(
        LoteNecesidad,
        claves={"emergencia_id": emergencia.id, "descripcion": DESCRIPCION_LOTE_DEMO},
        valores={"estado": EstadoLote.en_convocatoria},
    )
    resultado_lote = ResultadoSemilla("lotes")
    resultado_lote.contar(lote_creado)

    resultado_items = ResultadoSemilla("lote_items")
    for nombre_item, cantidad in ITEMS_DEL_LOTE:
        item = Item.query.filter_by(nombre=nombre_item).first()
        if item is None:
            raise ValueError(f"Item demo no encontrado: {nombre_item!r}")
        _, item_creado = obtener_o_crear(
            LoteItem,
            claves={"lote_id": lote.id, "item_id": item.id},
            valores={"cantidad_solicitada": cantidad},
        )
        resultado_items.contar(item_creado)

    coordinador = Usuario.query.filter_by(email="coordinador@rescuesync.test").first()
    if coordinador is None:
        raise ValueError("Usuario coordinador demo no encontrado.")

    convocatoria, convocatoria_creada = obtener_o_crear(
        Convocatoria,
        claves={"emergencia_id": emergencia.id, "observaciones": MARCA_CONVOCATORIA_DEMO},
        valores={
            "coordinador_id": coordinador.id,
            "fecha_inicio": datetime.now(UTC) - timedelta(days=1),
            "fecha_cierre": datetime.now(UTC) + timedelta(days=30),
            "resumen_situacion": emergencia.descripcion,
            "estado": EstadoConvocatoria.abierta,
        },
    )
    resultado_convocatoria = ResultadoSemilla("convocatorias")
    resultado_convocatoria.contar(convocatoria_creada)
    lote.convocatoria = convocatoria
    emergencia.estado = EstadoEmergencia.activa

    return [resultado_lote, resultado_items, resultado_convocatoria]