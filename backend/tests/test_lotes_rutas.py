"""Alta y edición de lotes por formulario, con las filas como las manda el navegador."""

from __future__ import annotations

import re
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


# --- Al volver con un error, la pantalla conserva lo cargado --------------------------------


def _fila_renderizada(cuerpo: str, indice: int, item_id: int, cantidad: int) -> bool:
    """Si la fila `indice` vino renderizada con ese ítem elegido y esa cantidad."""
    select = re.search(
        rf'<select name="items\[{indice}\]\[item_id\]".*?</select>', cuerpo, flags=re.DOTALL
    )
    return (
        select is not None
        and re.search(rf'<option value="{item_id}"[^>]*\bselected\b', select.group(0)) is not None
        and re.search(
            rf'name="items\[{indice}\]\[cantidad_solicitada\]"[^>]*value="{cantidad}"', cuerpo
        )
        is not None
    )


def test_el_alta_con_error_vuelve_con_las_filas_cargadas(
    app, crear_emergencias, ingresar_por_formulario, enviar_formulario
) -> None:
    [emergencia_id] = crear_emergencias(
        (datetime(2025, 3, 1, tzinfo=UTC), EstadoEmergencia.registrada)
    )
    primero, segundo, _ = _tres_items(app)
    ingresar_por_formulario(EMAIL_COORDINADOR)

    respuesta = enviar_formulario(
        f"/lotes/emergencias/{emergencia_id}/lotes/nuevo",
        {
            "descripcion": "Con error",
            **_filas((0, primero, 5), (1, segundo, 3), (2, primero, 2)),
            "items[1][observaciones]": "aptas para celíacos",
        },
    )

    cuerpo = respuesta.get_data(as_text=True)
    assert "ya está en la fila 1" in cuerpo
    assert _fila_renderizada(cuerpo, 0, primero, 5)
    assert _fila_renderizada(cuerpo, 1, segundo, 3)
    assert _fila_renderizada(cuerpo, 2, primero, 2)
    assert 'value="aptas para celíacos"' in cuerpo
    assert 'value="Con error"' in cuerpo


def test_el_alta_sin_error_arranca_sin_filas_renderizadas(
    app, crear_emergencias, ingresar_por_formulario, navegar
) -> None:
    [emergencia_id] = crear_emergencias(
        (datetime(2025, 3, 1, tzinfo=UTC), EstadoEmergencia.registrada)
    )
    ingresar_por_formulario(EMAIL_COORDINADOR)

    cuerpo = navegar(f"/lotes/emergencias/{emergencia_id}/lotes/nuevo").get_data(as_text=True)

    # Solo está la fila modelo del <template>; la primera fila la agrega el script.
    assert 'name="items[0][item_id]"' not in cuerpo
    assert 'name="items[__INDEX__][item_id]"' in cuerpo


def test_la_edicion_con_error_vuelve_con_lo_que_cargo_el_usuario(
    app, crear_emergencias, ingresar_por_formulario, enviar_formulario
) -> None:
    [emergencia_id] = crear_emergencias(
        (datetime(2025, 3, 1, tzinfo=UTC), EstadoEmergencia.registrada)
    )
    primero, segundo, tercero = _tres_items(app)
    ingresar_por_formulario(EMAIL_COORDINADOR)
    enviar_formulario(
        f"/lotes/emergencias/{emergencia_id}/lotes/nuevo",
        {"descripcion": "Original", **_filas((0, primero, 5))},
    )
    with app.app_context():
        lote_id = db.session.scalars(
            select(LoteNecesidad.id).filter_by(emergencia_id=emergencia_id)
        ).one()

    respuesta = enviar_formulario(
        f"/lotes/emergencias/{emergencia_id}/lotes/{lote_id}/editar",
        {"descripcion": "Editado", **_filas((0, segundo, 9), (1, tercero, 4), (2, segundo, 1))},
    )

    cuerpo = respuesta.get_data(as_text=True)
    assert "ya está en la fila 1" in cuerpo
    assert _fila_renderizada(cuerpo, 0, segundo, 9)
    assert _fila_renderizada(cuerpo, 1, tercero, 4)
    assert _fila_renderizada(cuerpo, 2, segundo, 1)
    assert not _fila_renderizada(cuerpo, 0, primero, 5)
