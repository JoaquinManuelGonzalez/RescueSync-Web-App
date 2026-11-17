"""Alta y edición de lotes por formulario, con las filas como las manda el navegador."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.extensiones import db
from app.modulos.emergencias.modelos import EstadoEmergencia, Item, LoteNecesidad

from .conftest import EMAIL_COORDINADOR


def _tres_items(app) -> list[int]:
    with app.app_context():
        return list(db.session.scalars(select(Item.id).order_by(Item.id).limit(3)))


def _filas(*filas: tuple[int, int, int]) -> dict[str, str]:
    """Campos del formulario para filas `(indice, item_id, cantidad)`."""
    datos = {}
    for indice, item_id, cantidad in filas:
        datos[f"items[{indice}][item_id]"] = str(item_id)
        datos[f"items[{indice}][cantidad_solicitada]"] = str(cantidad)
        datos[f"items[{indice}][observaciones]"] = ""
    return datos


def _items_del_lote(app, emergencia_id: int) -> list[tuple[int, int]]:
    with app.app_context():
        lote = db.session.scalars(
            select(LoteNecesidad).filter_by(emergencia_id=emergencia_id)
        ).one()
        return sorted((fila.item_id, fila.cantidad_solicitada) for fila in lote.lote_items)


def test_alta_de_lote_lee_las_filas_aunque_se_haya_quitado_la_primera(
    app, crear_emergencias, ingresar_por_formulario, enviar_formulario
) -> None:
    [emergencia_id] = crear_emergencias(
        (datetime(2025, 3, 1, tzinfo=UTC), EstadoEmergencia.registrada)
    )
    primero, segundo, tercero = _tres_items(app)
    ingresar_por_formulario(EMAIL_COORDINADOR)

    # La fila 0 se quitó en la pantalla: llegan items[1] e items[2].
    respuesta = enviar_formulario(
        f"/lotes/emergencias/{emergencia_id}/lotes/nuevo",
        {"descripcion": "Sin la primera fila", **_filas((1, segundo, 5), (2, tercero, 7))},
    )

    assert respuesta.status_code == 302
    assert _items_del_lote(app, emergencia_id) == [(segundo, 5), (tercero, 7)]


def test_alta_de_lote_no_pierde_las_filas_que_siguen_a_una_quitada(
    app, crear_emergencias, ingresar_por_formulario, enviar_formulario
) -> None:
    [emergencia_id] = crear_emergencias(
        (datetime(2025, 3, 1, tzinfo=UTC), EstadoEmergencia.registrada)
    )
    primero, segundo, tercero = _tres_items(app)
    ingresar_por_formulario(EMAIL_COORDINADOR)

    # Se quitó la fila del medio: llegan items[0] e items[2], y además en otro orden.
    respuesta = enviar_formulario(
        f"/lotes/emergencias/{emergencia_id}/lotes/nuevo",
        {"descripcion": "Sin la fila del medio", **_filas((2, tercero, 7), (0, primero, 3))},
    )

    assert respuesta.status_code == 302
    assert _items_del_lote(app, emergencia_id) == [(primero, 3), (tercero, 7)]


def test_el_error_de_fila_repetida_numera_las_filas_en_el_orden_de_la_pantalla(
    app, crear_emergencias, ingresar_por_formulario, enviar_formulario
) -> None:
    [emergencia_id] = crear_emergencias(
        (datetime(2025, 3, 1, tzinfo=UTC), EstadoEmergencia.registrada)
    )
    primero, _, _ = _tres_items(app)
    ingresar_por_formulario(EMAIL_COORDINADOR)

    respuesta = enviar_formulario(
        f"/lotes/emergencias/{emergencia_id}/lotes/nuevo",
        {"descripcion": "Repetido", **_filas((3, primero, 1), (10, primero, 2))},
    )

    # La pantalla de alta vuelve a mostrarse con el aviso (con 200, como el resto de sus errores).
    assert "ya está en la fila 1" in respuesta.get_data(as_text=True)
    with app.app_context():
        assert (
            db.session.scalars(select(LoteNecesidad).filter_by(emergencia_id=emergencia_id)).all()
            == []
        )
