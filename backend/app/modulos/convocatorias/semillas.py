"""Datos semilla de lotes y convocatorias para probar el flujo de ofertas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.convocatorias.modelos import (
    Convocatoria,
    DecisionCobertura,
    EstadoConvocatoria,
)
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    Item,
    LoteItem,
    LoteNecesidad,
)
from app.modulos.emergencias.semillas_emergencias import (
    TITULO_EMERGENCIA_COBERTURA_INSUFICIENTE,
)
from app.modulos.usuarios_roles.modelos import Usuario

TITULO_EMERGENCIA_DEMO = "Temporal severo con voladura de techos en Chascomús"
DESCRIPCION_LOTE_DEMO = "Recursos iniciales para asistencia y evacuación"
MARCA_CONVOCATORIA_DEMO = "SEED_DEMO_OFERTAS"
TITULO_EMERGENCIA_PRUEBA = "PRUEBA - Selección municipal de ofertas en Pergamino"
DESCRIPCION_LOTE_PRUEBA = "PRUEBA - Recursos para validar selección por línea"
MARCA_CONVOCATORIA_PRUEBA = "SEED_PRUEBA_SELECCION_SIN_BONITA"
DESCRIPCION_LOTE_COBERTURA_INSUFICIENTE = "PRUEBA - Necesidad con cobertura parcial"
MARCA_CONVOCATORIA_COBERTURA_INSUFICIENTE = "SEED_PRUEBA_COBERTURA_INSUFICIENTE"

ITEMS_DEL_LOTE: tuple[tuple[str, float], ...] = (
    ("Agua potable envasada", 1000),
    ("Raciones de alimento no perecedero", 500),
    ("Paramédicos", 5),
)


@registrar("convocatorias")
def sembrar_convocatorias() -> list[ResultadoSemilla]:
    """Crea convocatorias demo y casos de prueba para ofertas y cobertura parcial."""
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

    emergencia_prueba = Emergencia.query.filter_by(titulo=TITULO_EMERGENCIA_PRUEBA).first()
    if emergencia_prueba is None:
        raise ValueError(f"Emergencia de prueba no encontrada: {TITULO_EMERGENCIA_PRUEBA!r}")

    lote_prueba, lote_prueba_creado = obtener_o_crear(
        LoteNecesidad,
        claves={"emergencia_id": emergencia_prueba.id, "descripcion": DESCRIPCION_LOTE_PRUEBA},
        valores={"estado": EstadoLote.en_convocatoria},
    )
    resultado_lote_prueba = ResultadoSemilla("lotes_prueba")
    resultado_lote_prueba.contar(lote_prueba_creado)

    for nombre_item, cantidad in (("Agua potable envasada", 1000), ("Paramédicos", 8)):
        item = Item.query.filter_by(nombre=nombre_item).first()
        if item is None:
            raise ValueError(f"Item de prueba no encontrado: {nombre_item!r}")
        _, item_creado = obtener_o_crear(
            LoteItem,
            claves={"lote_id": lote_prueba.id, "item_id": item.id},
            valores={"cantidad_solicitada": cantidad},
        )
        resultado_lote_prueba.contar(item_creado)

    coordinador = Usuario.query.filter_by(email="coordinador@rescuesync.test").first()
    if coordinador is None:
        raise ValueError("Usuario coordinador demo no encontrado.")
    convocatoria_prueba, convocatoria_prueba_creada = obtener_o_crear(
        Convocatoria,
        claves={
            "emergencia_id": emergencia_prueba.id,
            "observaciones": MARCA_CONVOCATORIA_PRUEBA,
        },
        valores={
            "coordinador_id": coordinador.id,
            "fecha_inicio": datetime.now(UTC) - timedelta(days=3),
            "fecha_cierre": datetime.now(UTC) - timedelta(days=1),
            "resumen_situacion": emergencia_prueba.descripcion,
            "estado": EstadoConvocatoria.cerrada,
            "cobertura_completa": True,
            "cobertura_evaluada_en": datetime.now(UTC) - timedelta(hours=2),
        },
    )
    lote_prueba.convocatoria = convocatoria_prueba
    resultado_convocatoria_prueba = ResultadoSemilla("convocatorias_prueba")
    resultado_convocatoria_prueba.contar(convocatoria_prueba_creada)

    emergencia_cobertura = Emergencia.query.filter_by(
        titulo=TITULO_EMERGENCIA_COBERTURA_INSUFICIENTE
    ).first()
    if emergencia_cobertura is None:
        raise ValueError("Emergencia de cobertura insuficiente no encontrada.")
    emergencia_cobertura.estado = EstadoEmergencia.activa

    lote_cobertura, lote_cobertura_creado = obtener_o_crear(
        LoteNecesidad,
        claves={
            "emergencia_id": emergencia_cobertura.id,
            "descripcion": DESCRIPCION_LOTE_COBERTURA_INSUFICIENTE,
        },
        valores={"estado": EstadoLote.en_convocatoria},
    )
    resultado_lote_cobertura = ResultadoSemilla("lotes_cobertura_insuficiente")
    resultado_lote_cobertura.contar(lote_cobertura_creado)

    item_agua = Item.query.filter_by(nombre="Agua potable envasada").first()
    if item_agua is None:
        raise ValueError("Item de prueba para cobertura insuficiente no encontrado.")
    _, item_cobertura_creado = obtener_o_crear(
        LoteItem,
        claves={"lote_id": lote_cobertura.id, "item_id": item_agua.id},
        valores={"cantidad_solicitada": 1000},
    )
    resultado_item_cobertura = ResultadoSemilla("lote_items_cobertura_insuficiente")
    resultado_item_cobertura.contar(item_cobertura_creado)

    convocatoria_cobertura, convocatoria_cobertura_creada = obtener_o_crear(
        Convocatoria,
        claves={
            "emergencia_id": emergencia_cobertura.id,
            "observaciones": MARCA_CONVOCATORIA_COBERTURA_INSUFICIENTE,
        },
        valores={
            "coordinador_id": coordinador.id,
            "fecha_inicio": datetime.now(UTC) - timedelta(days=3),
            "fecha_cierre": datetime.now(UTC) - timedelta(days=1),
            "resumen_situacion": emergencia_cobertura.descripcion,
            "estado": EstadoConvocatoria.cerrada,
            "cobertura_completa": False,
            "cobertura_evaluada_en": datetime.now(UTC) - timedelta(hours=2),
            "porcentaje_cobertura": 75,
            "decision_cobertura": DecisionCobertura.pendiente.value,
        },
    )
    lote_cobertura.convocatoria = convocatoria_cobertura
    resultado_convocatoria_cobertura = ResultadoSemilla("convocatorias_cobertura_insuficiente")
    resultado_convocatoria_cobertura.contar(convocatoria_cobertura_creada)

    return [
        resultado_lote,
        resultado_items,
        resultado_convocatoria,
        resultado_lote_prueba,
        resultado_convocatoria_prueba,
        resultado_lote_cobertura,
        resultado_item_cobertura,
        resultado_convocatoria_cobertura,
    ]
