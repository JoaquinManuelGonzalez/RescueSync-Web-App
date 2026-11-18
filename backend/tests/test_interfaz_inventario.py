"""La pantalla de inventario usa el inventario de la organizacion autenticada."""

from __future__ import annotations

import re

from .conftest import EMAIL_REPRESENTANTE

# Los ids son UUID: así aparecen en los atributos data-* de la pantalla.
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def test_la_pantalla_muestra_el_inventario_de_la_organizacion(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    respuesta = navegar("/organizaciones/inventario")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Raciones de alimento no perecedero" in cuerpo
    assert "600" in cuerpo


def test_el_formulario_no_ofrece_items_ya_cargados(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    respuesta = navegar("/organizaciones/inventario/nuevo")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Raciones de alimento no perecedero" not in cuerpo
    assert "Lentejas" in cuerpo


def test_el_inventario_filtra_por_categoria(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    respuesta = navegar("/organizaciones/inventario?categoria=alimentos")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Raciones de alimento no perecedero" in cuerpo
    assert "Botiquines de primeros auxilios" not in cuerpo


def test_el_inventario_busca_por_nombre(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    respuesta = navegar("/organizaciones/inventario?texto=Raciones")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Raciones de alimento no perecedero" in cuerpo
    assert "Botiquines de primeros auxilios" not in cuerpo


def test_el_inventario_actualiza_la_cantidad_de_un_item(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)
    cuerpo = navegar("/organizaciones/inventario").get_data(as_text=True)
    coincidencia = re.search(
        rf'data-inventario-item-id="({UUID})"\s+data-item-id="({UUID})"', cuerpo
    )
    inventario_item_id, item_id = coincidencia.groups()

    respuesta = enviar_formulario(
        f"/organizaciones/inventario/{inventario_item_id}/editar",
        {"item_id": item_id, "cantidad_disponible": 725},
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/organizaciones/inventario")
    cuerpo = navegar("/organizaciones/inventario").get_data(as_text=True)
    assert "725" in cuerpo


def test_el_inventario_rechaza_cantidad_cero(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)
    cuerpo = navegar("/organizaciones/inventario").get_data(as_text=True)
    coincidencia = re.search(
        rf'data-inventario-item-id="({UUID})"\s+data-item-id="({UUID})"', cuerpo
    )
    inventario_item_id, item_id = coincidencia.groups()

    respuesta = enviar_formulario(
        f"/organizaciones/inventario/{inventario_item_id}/editar",
        {"item_id": item_id, "cantidad_disponible": 0},
    )

    assert respuesta.status_code == 400


def test_el_inventario_elimina_un_item(ingresar_por_formulario, enviar_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)
    cuerpo = navegar("/organizaciones/inventario").get_data(as_text=True)
    item_id = re.search(rf'data-inventario-item-id="({UUID})"', cuerpo).group(1)

    respuesta = enviar_formulario(f"/organizaciones/inventario/{item_id}/eliminar")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/organizaciones/inventario")
    cuerpo = navegar("/organizaciones/inventario").get_data(as_text=True)
    assert f'data-inventario-item-id="{item_id}"' not in cuerpo
