"""Validaciones de los lotes de necesidad: cantidades e ítems repetidos."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errores import SolicitudInvalida
from app.extensiones import db
from app.modulos.emergencias.lotes.servicios import _parsear_cantidad, crear_lotes, editar_lote
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia, Item, LoteNecesidad


@pytest.mark.parametrize("valor", ["10", " 10 ", 10, "10.0", Decimal("10.00")])
def test_parsear_cantidad_devuelve_un_entero(valor):
    cantidad = _parsear_cantidad(valor)
    assert cantidad == 10
    assert isinstance(cantidad, int)


@pytest.mark.parametrize("valor", ["2.5", 0.5, "abc", "NaN", "Infinity", "0", "-3", "", None])
def test_parsear_cantidad_rechaza_valores_que_no_son_enteros_positivos(valor):
    with pytest.raises(SolicitudInvalida):
        _parsear_cantidad(valor)


# --- Un ítem va una sola vez por lote -----------------------------------------------------


def _emergencia_registrada(crear_emergencias) -> int:
    [emergencia_id] = crear_emergencias(
        (datetime(2025, 3, 1, tzinfo=UTC), EstadoEmergencia.registrada)
    )
    return emergencia_id


def _dos_items() -> tuple[int, int]:
    primero, segundo = db.session.scalars(select(Item.id).order_by(Item.id).limit(2)).all()
    return primero, segundo


def test_crear_lote_rechaza_un_item_repetido(app, crear_emergencias):
    emergencia_id = _emergencia_registrada(crear_emergencias)
    with app.app_context():
        item_id, _ = _dos_items()
        with pytest.raises(SolicitudInvalida) as error:
            crear_lotes(
                emergencia_id=emergencia_id,
                descripcion="Lote con un ítem repetido",
                items=[
                    {"item_id": str(item_id), "cantidad_solicitada": "5"},
                    {"item_id": str(item_id), "cantidad_solicitada": "3"},
                ],
            )

        assert "ya está en la fila 1" in error.value.mensaje
        assert error.value.detalle == {"campo": "items[1].item_id"}
        assert (
            db.session.scalars(select(LoteNecesidad).filter_by(emergencia_id=emergencia_id)).all()
            == []
        )
        assert db.session.get(Emergencia, emergencia_id).estado == EstadoEmergencia.registrada


def test_crear_lote_acepta_items_distintos(app, crear_emergencias):
    emergencia_id = _emergencia_registrada(crear_emergencias)
    with app.app_context():
        primero, segundo = _dos_items()
        [lote] = crear_lotes(
            emergencia_id=emergencia_id,
            descripcion=None,
            items=[
                {"item_id": str(primero), "cantidad_solicitada": "5"},
                {"item_id": str(segundo), "cantidad_solicitada": "3"},
            ],
        )

        assert sorted(fila.item_id for fila in lote.lote_items) == [primero, segundo]


def test_editar_lote_rechaza_un_item_repetido_y_no_toca_el_lote(app, crear_emergencias):
    emergencia_id = _emergencia_registrada(crear_emergencias)
    with app.app_context():
        primero, segundo = _dos_items()
        [lote] = crear_lotes(
            emergencia_id=emergencia_id,
            descripcion="Original",
            items=[{"item_id": str(primero), "cantidad_solicitada": "5"}],
        )

        with pytest.raises(SolicitudInvalida):
            editar_lote(
                lote_id=lote.id,
                descripcion="Con repetidos",
                items=[
                    {"item_id": str(segundo), "cantidad_solicitada": "1"},
                    {"item_id": str(primero), "cantidad_solicitada": "2"},
                    {"item_id": str(segundo), "cantidad_solicitada": "4"},
                ],
            )
        db.session.rollback()

        lote = db.session.get(LoteNecesidad, lote.id)
        assert lote.descripcion == "Original"
        assert [(fila.item_id, fila.cantidad_solicitada) for fila in lote.lote_items] == [
            (primero, 5)
        ]
