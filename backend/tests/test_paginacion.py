"""Paginacion de los listados: en la base, con los filtros conservados entre paginas."""

from __future__ import annotations

import math

import pytest

from app.core.interfaz.paginacion import POR_PAGINA_POR_DEFECTO, Pagina

from .conftest import EMAIL_ADMINISTRADOR

ORGANIZACIONES_EXTRA = 25


@pytest.fixture
def muchas_organizaciones(app, base_de_datos) -> int:
    """Suma ONGs de prueba y devuelve cuantas ONGs hay en total."""
    from app.modulos.organizaciones import servicios

    with app.app_context():
        for numero in range(ORGANIZACIONES_EXTRA):
            servicios.crear(
                nombre=f"ONG de prueba {numero:02d}",
                tipo="ong",
                zonas=[{"provincia": "Buenos Aires"}],
            )
        return len(servicios.listar(tipo="ong"))


def test_la_ventana_de_paginas_marca_los_saltos() -> None:
    pagina = Pagina(elementos=[], numero=5, por_pagina=10, total=100)

    assert pagina.ventana() == [1, None, 4, 5, 6, None, 10]


def test_la_ventana_sin_saltos_cuando_hay_pocas_paginas() -> None:
    assert Pagina([], 2, 10, 30).ventana() == [1, 2, 3]


def test_el_listado_json_trae_la_primera_pagina_y_sus_metadatos(
    cliente_sembrado, ingresar, muchas_organizaciones
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    cuerpo = cliente_sembrado.get("/organizaciones?tipo=ong").get_json()

    assert len(cuerpo["organizaciones"]) == POR_PAGINA_POR_DEFECTO
    assert cuerpo["paginacion"] == {
        "pagina": 1,
        "por_pagina": POR_PAGINA_POR_DEFECTO,
        "total": muchas_organizaciones,
        "paginas": math.ceil(muchas_organizaciones / POR_PAGINA_POR_DEFECTO),
    }


def test_las_paginas_siguientes_traen_el_resto_sin_repetir(
    cliente_sembrado, ingresar, muchas_organizaciones
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    paginas = math.ceil(muchas_organizaciones / POR_PAGINA_POR_DEFECTO)
    ids: list[int] = []
    for numero in range(1, paginas + 1):
        cuerpo = cliente_sembrado.get(f"/organizaciones?tipo=ong&pagina={numero}").get_json()
        ids.extend(una["id"] for una in cuerpo["organizaciones"])

    assert len(ids) == muchas_organizaciones
    assert len(set(ids)) == muchas_organizaciones


def test_una_pagina_fuera_de_rango_muestra_la_ultima(
    cliente_sembrado, ingresar, muchas_organizaciones
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    cuerpo = cliente_sembrado.get("/organizaciones?tipo=ong&pagina=99").get_json()

    assert cuerpo["paginacion"]["pagina"] == math.ceil(
        muchas_organizaciones / POR_PAGINA_POR_DEFECTO
    )


def test_el_tamano_de_pagina_tiene_tope(cliente_sembrado, ingresar, muchas_organizaciones) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    cuerpo = cliente_sembrado.get("/organizaciones?por_pagina=5000").get_json()

    assert cuerpo["paginacion"]["por_pagina"] == 100


def test_una_pagina_no_numerica_se_rechaza(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.get("/usuarios?pagina=dos")

    assert respuesta.status_code == 400
    assert "pagina" in respuesta.get_json()["error"]["detalle"]


def test_la_paginacion_de_la_pantalla_conserva_los_filtros(
    ingresar_por_formulario, navegar, muchas_organizaciones
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    cuerpo = navegar("/organizaciones?tipo=ong").get_data(as_text=True)

    assert f"Mostrando 1–{POR_PAGINA_POR_DEFECTO} de {muchas_organizaciones}" in cuerpo
    assert 'href="/organizaciones?tipo=ong&amp;pagina=2"' in cuerpo
    assert 'aria-current="page">1<' in cuerpo


def test_una_sola_pagina_no_muestra_controles(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    cuerpo = navegar("/usuarios").get_data(as_text=True)

    assert "Mostrando 1–" in cuerpo
    assert "paginacion-controles" not in cuerpo
